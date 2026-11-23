from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.config import Settings
from app.modules.jobs.models import Job
from app.modules.studio.models import Episode, Project, ProjectAsset, StoryboardClip
from app.modules.studio.service import reorder_episode_clips
from app.workers.sweeper import sweep_stale_jobs_once


class FakeSweeperRedis:
    def __init__(self, *, lock_available: bool = True) -> None:
        self.lock_available = lock_available
        self.published: list[str] = []

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        return self.lock_available

    async def publish(self, channel: str, payload: str) -> int:
        self.published.append(payload)
        return 1


class InMemorySweeperDB:
    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self.assets: dict[object, ProjectAsset] = {}
        self.clips: dict[object, StoryboardClip] = {}
        self.episodes: list[Episode] = []
        self.flushed_indices_history: list[list[int]] = []

    def session_factory(self):
        db = self

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def flush(self) -> None:
                # 模拟数据库唯一约束与 clip_index >= 1 校验
                vals = [c.clip_index for c in db.clips.values()]
                assert all(v >= 1 for v in vals), f"clip_index must be >= 1, got {vals}"
                assert len(vals) == len(set(vals)), f"duplicate clip_index: {vals}"
                db.flushed_indices_history.append(list(vals))

            async def commit(self) -> None:
                return None

            async def scalar(self, stmt):
                entity = stmt.column_descriptions[0]["entity"]
                params = list(stmt.compile().params.values())
                if entity is ProjectAsset:
                    return db.assets.get(params[0])
                if entity is StoryboardClip:
                    return db.clips.get(params[0])
                if entity is Episode:
                    return db.episodes[0] if db.episodes else None
                raise NotImplementedError(entity)

            async def scalars(self, stmt):
                entity = stmt.column_descriptions[0]["entity"]
                sql = str(stmt)
                if entity is StoryboardClip:
                    return sorted(db.clips.values(), key=lambda c: c.clip_index)
                if entity is Job:
                    if "lease_until <" in sql:
                        now = datetime.now(UTC)
                        return [
                            j
                            for j in db.jobs
                            if j.status in ("running", "polling")
                            and j.lease_until is not None
                            and j.lease_until < now
                        ]
                    cutoff = datetime.now(UTC) - timedelta(seconds=180)
                    now = datetime.now(UTC)
                    return [
                        j
                        for j in db.jobs
                        if j.status == "queued"
                        and j.created_at is not None
                        and j.created_at < cutoff
                        and (j.next_attempt_at is None or j.next_attempt_at <= now)
                    ]
                raise NotImplementedError(entity)

        return _Session()


async def test_sweeper_resumes_polling_media_reviews_unsubmitted_and_requeues_stale_queued():
    db = InMemorySweeperDB()
    now = datetime.now(UTC)
    past = now - timedelta(minutes=10)
    project_id = uuid4()

    asset_id = uuid4()
    db.assets[asset_id] = ProjectAsset(
        id=asset_id,
        project_id=project_id,
        asset_code="C01",
        kind="character",
        name="林晓",
        description="",
        prompt="p",
        voice="",
        episode_numbers=[1],
        image_url="https://cdn.example/old.png",
        image_status="generating",
    )

    # 1. Expired clip_video WITH provider_task_id -> resume polling (no duplicate submit)
    j_resume = Job(
        id=uuid4(),
        user_id=1,
        project_id=project_id,
        job_type="clip_video",
        target_id=str(uuid4()),
        status="polling",
        provider_task_id="cc-task-123",
        lease_token="tok1",
        lease_until=past,
        step_index=2,
        step_total=4,
        step_label="渲染中",
        progress=40,
        created_at=past,
    )
    # 2. Expired asset_image WITHOUT provider_task_id -> review (keep frozen, restore old image_status)
    j_review = Job(
        id=uuid4(),
        user_id=1,
        project_id=project_id,
        job_type="asset_image",
        target_id=str(asset_id),
        status="running",
        provider_task_id=None,
        lease_token="tok2",
        lease_until=past,
        step_index=1,
        step_total=4,
        step_label="提交中",
        progress=15,
        created_at=past,
    )
    # 3. Stale queued compose job -> requeued to media_broker
    j_queued = Job(
        id=uuid4(),
        user_id=1,
        project_id=project_id,
        job_type="episode_compose",
        target_id=str(uuid4()),
        status="queued",
        step_index=0,
        step_total=4,
        step_label="排队中",
        progress=0,
        created_at=past,
        next_attempt_at=past,
    )
    db.jobs.extend([j_resume, j_review, j_queued])

    dispatched: list[tuple[str, str]] = []

    async def fake_dispatch(job_type: str, job_id: str) -> None:
        dispatched.append((job_type, job_id))

    redis = FakeSweeperRedis(lock_available=True)
    counts = await sweep_stale_jobs_once(
        sessions=db.session_factory,
        redis=redis,
        settings=Settings(environment="test"),
        dispatcher=fake_dispatch,
        now=now,
    )
    assert counts["resumed"] == 1
    assert counts["reviewed"] == 1
    assert counts["requeued"] == 1
    assert j_resume.status == "queued"
    assert j_resume.lease_token is None
    assert j_review.status == "review"
    assert db.assets[asset_id].image_status == "ready"
    assert ("clip_video", str(j_resume.id)) in dispatched
    assert ("episode_compose", str(j_queued.id)) in dispatched
    assert all(jid != str(j_review.id) for _, jid in dispatched)

    # Lock contention skips cleanly
    skipped = await sweep_stale_jobs_once(
        sessions=db.session_factory,
        redis=FakeSweeperRedis(lock_available=False),
        settings=Settings(environment="test"),
        dispatcher=fake_dispatch,
        now=now,
    )
    assert skipped["skipped"] == 1


async def test_reorder_episode_clips_uses_positive_two_step_offset():
    db = InMemorySweeperDB()
    project = Project(id=uuid4(), user_id=1, name="测试")
    ep = Episode(id=uuid4(), project_id=project.id, number=1, title="第一集")
    db.episodes.append(ep)

    c1 = StoryboardClip(
        id=uuid4(), project_id=project.id, episode_id=ep.id, clip_index=1, duration_seconds=10, prompt="a"
    )
    c2 = StoryboardClip(
        id=uuid4(), project_id=project.id, episode_id=ep.id, clip_index=2, duration_seconds=12, prompt="b"
    )
    c3 = StoryboardClip(
        id=uuid4(), project_id=project.id, episode_id=ep.id, clip_index=3, duration_seconds=8, prompt="c"
    )
    db.clips = {c1.id: c1, c2.id: c2, c3.id: c3}

    async with db.session_factory() as session:
        ordered = await reorder_episode_clips(
            session, project=project, episode_number=1, clip_ids=[c3.id, c1.id, c2.id]
        )
    assert [c.id for c in ordered] == [c3.id, c1.id, c2.id]
    assert [c.clip_index for c in ordered] == [1, 2, 3]
    assert len(db.flushed_indices_history) == 2


async def test_resilient_broker_listen_survives_redis_connection_error(monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError

    from app.workers import broker as broker_mod

    observed_timeouts: list[int] = []
    outcomes: list[object] = [
        RedisConnectionError("[WinError 10054] connection reset"),
        None,
        (b"q:ai", b"hello-job"),
    ]

    class FakeRedisConn:
        def __init__(self, *, connection_pool):
            self.connection_pool = connection_pool

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def brpop(self, queue_name: str, timeout: int = 0):  # noqa: ASYNC109
            observed_timeouts.append(timeout)
            item = outcomes.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    monkeypatch.setattr(broker_mod, "Redis", FakeRedisConn)
    b = broker_mod.ResilientListQueueBroker(url="redis://127.0.0.1:6379/0", queue_name="q:ai")
    b.reconnect_backoff_seconds = 0.01

    gen = b.listen()
    payload = await gen.__anext__()
    await gen.aclose()

    assert payload == b"hello-job"
    assert observed_timeouts == [30, 30, 30]


async def test_heartbeat_job_lease_survives_transient_db_error():
    import asyncio
    from contextlib import asynccontextmanager

    from app.modules.jobs.service import heartbeat_job_lease

    attempts = 0
    succeeded = asyncio.Event()

    class FakeSession:
        async def execute(self, stmt):
            return None

        async def commit(self):
            succeeded.set()

    @asynccontextmanager
    async def flaky_sessions():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient db error")
        yield FakeSession()

    task = asyncio.create_task(
        heartbeat_job_lease(flaky_sessions, uuid4(), "tok", interval_seconds=0, lease_seconds=300)
    )
    try:
        await asyncio.wait_for(succeeded.wait(), timeout=2.0)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert attempts >= 2

