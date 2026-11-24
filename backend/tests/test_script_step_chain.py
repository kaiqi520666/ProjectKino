import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.test import TestModel

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.credits.models import CreditLedger
from app.modules.jobs.models import Job
from app.modules.jobs.schemas import JobOut
from app.modules.jobs.service import claim_job_lease
from app.modules.llm_engine.schema import (
    Asset,
    AssetResult,
    Beat,
    Character,
    Episode,
    EpisodePlan,
    Outline,
    ProjectSettings,
    Scene,
    SceneCard,
    ScriptResult,
)
from app.modules.llm_engine.schema import (
    StoryboardClip as LlmStoryboardClip,
)
from app.modules.studio.models import (
    Episode as DbEpisode,
)
from app.modules.studio.models import (
    Project,
)
from app.modules.studio.models import (
    StoryboardClip as DbStoryboardClip,
)
from app.workers import ai_tasks
from app.workers.llm_limiter import (
    acquire_llm_slot,
    is_retryable_llm_error,
    retry_backoff_seconds,
)
from app.workers.sweeper import sweep_stale_jobs_once


def _sample_settings(episode_count: int = 2) -> ProjectSettings:
    return ProjectSettings(
        name="长剧压力测试",
        ratio="16:9",
        language="zh-CN",
        visualStyle="live-action",
        episodeCount=episode_count,
        maxSegmentDuration=15,
        secondsPerEpisode=120,
    )


def _sample_outline(episode_count: int = 2) -> Outline:
    return Outline(
        continuity="连贯悬疑主线",
        characters=[Character(id="C01", name="陈默", role="司机")],
        scenes=[SceneCard(id="S01", name="出租车内", kind="内景", time="夜")],
        props=[],
        episodes=[
            EpisodePlan(
                number=i,
                title=f"第{i}集标题",
                summary=f"第{i}集梗概",
                hook=f"第{i}集钩子",
                suspense=f"第{i}集中段悬念",
                ending=f"第{i}集结尾",
                characterIds=["C01"],
                sceneIds=["S01"],
            )
            for i in range(1, episode_count + 1)
        ],
    )


def _sample_episode(num: int) -> Episode:
    return Episode(
        number=num,
        title=f"第{num}集标题",
        summary=f"第{num}集梗概",
        hook=f"第{num}集钩子",
        cliff=f"第{num}集悬念",
        hookBeat=(1, 1),
        targetSeconds=120,
        seconds=118.5,
        scenes=[
            Scene(
                sceneId="S01",
                lighting="冷色夜灯",
                characters=["C01"],
                props=[],
                flow=[Beat(action="雨刷左右摆动。"), Beat(speaker="C01", line="上车吧。")],
            )
        ],
        script=f"第一场\n内景 · 出租车内 · 夜\n第{num}集正文",
        warnings=[],
    )


class FakeStepChainDB:
    def __init__(self, project: Project, job: Job) -> None:
        self.project = project
        self.job = job
        self.outline: Outline | None = None
        self.episodes: dict[int, Episode] = {}
        self.active_sessions = 0
        self.published: list[tuple[str, str]] = []
        self.ledgers: dict[str, CreditLedger] = {}

    def session_factory(self):
        db = self

        class _Session:
            async def __aenter__(self):
                db.active_sessions += 1
                return self

            async def __aexit__(self, *args):
                db.active_sessions -= 1
                return None

            async def scalar(self, stmt):
                entity = stmt.column_descriptions[0]["entity"]
                if entity is Job:
                    return db.job
                if entity is Project:
                    return db.project
                raise NotImplementedError(entity)

            async def execute(self, stmt):
                return None

            async def commit(self) -> None:
                return None

            async def refresh(self, obj) -> None:
                return None

        return _Session()


class FakeEventRedis:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def publish(self, channel: str, payload: str) -> int:
        self.events.append(payload)
        return 1


async def test_script_step_chain_advances_outline_then_each_episode_and_accumulates_billing(
    monkeypatch,
):
    proj_settings = _sample_settings(episode_count=2)
    project = Project(
        id=uuid4(),
        user_id=1,
        name=proj_settings.name,
        mode="story",
        source_text="雨夜出租车司机接到一名神秘乘客。",
        settings=proj_settings.model_dump(),
    )
    now = datetime.now(UTC)
    job = Job(
        id=uuid4(),
        user_id=1,
        project_id=project.id,
        job_type="script_generate",
        status="queued",
        step_index=0,
        step_total=4,
        step_label="排队中",
        progress=0,
        input_payload={"feedback": ""},
        created_at=now,
        dispatch_after=now,
        next_attempt_at=now,
    )
    db = FakeStepChainDB(project, job)
    redis = FakeEventRedis()
    settings = Settings(environment="test", llm_max_concurrency=5)
    queued_next: list[str] = []
    observed_active_sessions_during_llm: list[int] = []

    async def fake_enqueue(job_id_str: str) -> None:
        queued_next.append(job_id_str)

    async def fake_build_script(session, proj):
        assert db.outline is not None
        return ScriptResult(
            settings=proj_settings,
            outline=db.outline,
            episodes=[db.episodes[k] for k in sorted(db.episodes)],
        )

    async def fake_persist_outline(session, proj, st, outline_obj, *, reset_downstream=False):
        db.outline = outline_obj

    async def fake_persist_ep(session, proj, ep_obj):
        db.episodes[ep_obj.number] = ep_obj

    async def fake_plan_outline(model, st, source, *, feedback="", usage=None, on_progress=None):
        observed_active_sessions_during_llm.append(db.active_sessions)
        if usage is not None:
            usage.input_tokens += 100
            usage.output_tokens += 50
        return _sample_outline(2)

    async def fake_write_ep(
        model,
        *,
        settings,
        outline,
        plan,
        source,
        previous=None,
        feedback="",
        usage=None,
        on_progress=None,
    ):
        observed_active_sessions_during_llm.append(db.active_sessions)
        if plan.number == 2:
            assert previous is not None and previous.number == 1
        if usage is not None:
            usage.input_tokens += 200
            usage.output_tokens += 120
        return _sample_episode(plan.number)

    async def fake_charge(
        session,
        *,
        user_id,
        model_id,
        job_id,
        input_tokens,
        cache_read_tokens,
        output_tokens,
        idempotency_key,
        reason,
    ):
        if idempotency_key in db.ledgers:
            return db.ledgers[idempotency_key]
        cost = Decimal("0.1000")
        ledger = CreditLedger(
            user_id=user_id,
            job_id=job_id,
            idempotency_key=idempotency_key,
            operation="llm_consume",
            balance_change=-cost,
            frozen_change=Decimal("0"),
            balance_before=Decimal("10"),
            balance_after=Decimal("9.9"),
            frozen_before=Decimal("0"),
            frozen_after=Decimal("0"),
            token_usage={
                "modelId": model_id,
                "inputTokens": input_tokens,
                "cacheReadTokens": cache_read_tokens,
                "outputTokens": output_tokens,
                "cost": str(cost),
            },
            reason=reason,
        )
        db.ledgers[idempotency_key] = ledger
        return ledger

    monkeypatch.setattr(ai_tasks, "build_script_result_from_db", fake_build_script)
    monkeypatch.setattr(ai_tasks, "persist_project_outline", fake_persist_outline)
    monkeypatch.setattr(ai_tasks, "persist_single_episode", fake_persist_ep)
    monkeypatch.setattr(ai_tasks, "plan_script_outline", fake_plan_outline)
    monkeypatch.setattr(ai_tasks, "write_single_script_episode", fake_write_ep)
    monkeypatch.setattr(ai_tasks, "charge_llm_usage", fake_charge)

    # Step 0: outline
    await ai_tasks.run_llm_job_core(
        sessions=db.session_factory,
        redis=redis,
        settings=settings,
        job_id=job.id,
        model_override=(TestModel(), "test-model"),
        enqueue_next=fake_enqueue,
    )
    assert db.outline is not None
    assert job.status == "queued"
    assert job.input_payload["outlineReady"] is True
    assert len(queued_next) == 1

    # Step 1: EP 1
    await ai_tasks.run_llm_job_core(
        sessions=db.session_factory,
        redis=redis,
        settings=settings,
        job_id=job.id,
        model_override=(TestModel(), "test-model"),
        enqueue_next=fake_enqueue,
    )
    assert 1 in db.episodes and 2 not in db.episodes
    assert job.status == "queued"
    assert len(queued_next) == 2

    # Step 2: EP 2 -> terminal succeeded
    await ai_tasks.run_llm_job_core(
        sessions=db.session_factory,
        redis=redis,
        settings=settings,
        job_id=job.id,
        model_override=(TestModel(), "test-model"),
        enqueue_next=fake_enqueue,
    )
    assert sorted(db.episodes.keys()) == [1, 2]
    assert job.status == "succeeded"
    assert job.progress == 100
    assert job.result_payload == {"projectId": str(project.id), "episodeCount": 2}
    assert len(queued_next) == 2  # No further enqueue after completion

    # Zero DB connections held during every single LLM step!
    assert observed_active_sessions_during_llm == [0, 0, 0]

    # Per-step idempotent billing + cumulative usage_summary on Job!
    assert len(db.ledgers) == 3
    assert job.usage_summary is not None
    assert job.usage_summary["inputTokens"] == 100 + 200 + 200
    assert job.usage_summary["outputTokens"] == 50 + 120 + 120
    assert job.usage_summary["cost"] == "0.3000"


async def test_script_step_chain_auto_retries_429_with_backoff_and_fails_on_401(monkeypatch):
    proj_settings = _sample_settings(episode_count=1)
    project = Project(
        id=uuid4(),
        user_id=1,
        name=proj_settings.name,
        mode="story",
        source_text="故事梗概",
        settings=proj_settings.model_dump(),
    )
    now = datetime.now(UTC)
    job = Job(
        id=uuid4(),
        user_id=1,
        project_id=project.id,
        job_type="script_generate",
        status="queued",
        step_index=1,
        step_total=3,
        step_label="大纲已保存",
        progress=18,
        input_payload={"outlineReady": True, "stepAttempts": 0},
        created_at=now,
        dispatch_after=now,
        next_attempt_at=now,
    )
    db = FakeStepChainDB(project, job)
    db.outline = _sample_outline(1)
    redis = FakeEventRedis()
    settings = Settings(environment="test", script_step_max_retries=3)
    queued_next: list[str] = []

    async def fake_enqueue(job_id_str: str) -> None:
        queued_next.append(job_id_str)

    async def fake_build_script(session, proj):
        return ScriptResult(
            settings=proj_settings,
            outline=db.outline,
            episodes=[db.episodes[k] for k in sorted(db.episodes)],
        )

    async def fake_persist_ep(session, proj, ep_obj):
        db.episodes[ep_obj.number] = ep_obj

    call_count = 0

    async def flaky_write_ep(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ModelHTTPError(status_code=429, model_name="test-model", body="rate limited")
        raise ModelHTTPError(status_code=401, model_name="test-model", body="invalid api key")

    monkeypatch.setattr(ai_tasks, "build_script_result_from_db", fake_build_script)
    monkeypatch.setattr(ai_tasks, "persist_single_episode", fake_persist_ep)
    monkeypatch.setattr(ai_tasks, "write_single_script_episode", flaky_write_ep)

    # Attempt 1: 429 -> stays queued with backoff, NOT failed, NOT immediately re-enqueued
    await ai_tasks.run_llm_job_core(
        sessions=db.session_factory,
        redis=redis,
        settings=settings,
        job_id=job.id,
        model_override=(TestModel(), "test-model"),
        enqueue_next=fake_enqueue,
    )
    assert job.status == "queued"
    assert job.input_payload["stepAttempts"] == 1
    assert job.dispatch_after is not None and job.dispatch_after > now
    assert "自动重试（第 1/3 次）" in job.step_label
    assert queued_next == []

    # Before dispatch_after elapses, claim_job_lease refuses early claim
    early_claim = await claim_job_lease(db.session_factory, job.id)
    assert early_claim is None

    # Fast-forward dispatch_after; Attempt 2 hits non-retryable 401 -> immediately fails
    job.dispatch_after = datetime.now(UTC) - timedelta(seconds=1)
    await ai_tasks.run_llm_job_core(
        sessions=db.session_factory,
        redis=redis,
        settings=settings,
        job_id=job.id,
        model_override=(TestModel(), "test-model"),
        enqueue_next=fake_enqueue,
    )
    assert job.status == "failed"
    assert job.finished_at is not None


async def test_sweeper_auto_recovers_expired_script_step_job_up_to_limit():
    from tests.test_sweeper import FakeSweeperRedis, InMemorySweeperDB

    db = InMemorySweeperDB()
    now = datetime.now(UTC)
    past = now - timedelta(minutes=10)
    project_id = uuid4()

    j_recover = Job(
        id=uuid4(),
        user_id=1,
        project_id=project_id,
        job_type="script_generate",
        status="running",
        lease_token="tok-rec",
        lease_until=past,
        step_index=3,
        step_total=8,
        step_label="正在撰写第 2/6 集",
        progress=35,
        input_payload={"outlineReady": True, "crashRecoveries": 0},
        created_at=past,
    )
    j_exhausted = Job(
        id=uuid4(),
        user_id=1,
        project_id=project_id,
        job_type="script_regenerate",
        status="running",
        lease_token="tok-exh",
        lease_until=past,
        step_index=3,
        step_total=8,
        step_label="正在撰写第 2/6 集",
        progress=35,
        input_payload={"outlineReady": True, "crashRecoveries": 2},
        created_at=past,
    )
    db.jobs.extend([j_recover, j_exhausted])

    dispatched: list[tuple[str, str]] = []

    async def fake_dispatch(job_type: str, job_id: str) -> None:
        dispatched.append((job_type, job_id))

    counts = await sweep_stale_jobs_once(
        sessions=db.session_factory,
        redis=FakeSweeperRedis(lock_available=True),
        settings=Settings(environment="test", script_crash_max_recoveries=2),
        dispatcher=fake_dispatch,
        now=now,
    )
    assert counts["resumed"] == 1
    assert counts["failed"] == 1
    assert j_recover.status == "queued"
    assert j_recover.input_payload["crashRecoveries"] == 1
    assert ("script_generate", str(j_recover.id)) in dispatched
    assert j_exhausted.status == "failed"
    assert j_exhausted.error_code == "worker_lease_expired"


async def test_redis_llm_limiter_enforces_concurrency_cap_and_releases_cleanly():
    class FakeZSetRedis:
        def __init__(self) -> None:
            self.zsets: dict[str, dict[str, float]] = {}

        async def eval(self, script: str, numkeys: int, key: str, *args: Any) -> int:
            zset = self.zsets.setdefault(key, {})
            if "ZCARD" in script:
                now = float(args[0])
                expires_at = float(args[1])
                limit = int(args[2])
                token = str(args[3])
                for member in [m for m, score in zset.items() if score <= now]:
                    del zset[member]
                if len(zset) < limit:
                    zset[token] = expires_at
                    return 1
                return 0
            # Renew script
            expires_at = float(args[0])
            token = str(args[1])
            if token in zset:
                zset[token] = expires_at
                return 1
            return 0

        async def zrem(self, key: str, token: str) -> int:
            zset = self.zsets.get(key, {})
            return 1 if zset.pop(token, None) is not None else 0

    fake_redis = FakeZSetRedis()
    settings = Settings(environment="test", llm_max_concurrency=2, llm_slot_ttl_seconds=60)
    in_flight = 0
    peak = 0

    async def worker() -> None:
        nonlocal in_flight, peak
        async with acquire_llm_slot(fake_redis, settings, "deepseek", poll_interval=0.01):
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.03)
            in_flight -= 1

    await asyncio.gather(*(worker() for _ in range(5)))
    assert peak == 2
    assert all(len(members) == 0 for members in fake_redis.zsets.values())


def test_retry_classification_and_backoff():
    assert is_retryable_llm_error(ModelHTTPError(status_code=429, model_name="m")) is True
    assert is_retryable_llm_error(ModelHTTPError(status_code=502, model_name="m")) is True
    assert is_retryable_llm_error(ModelHTTPError(status_code=503, model_name="m")) is True
    assert is_retryable_llm_error(httpx.ReadTimeout("timeout")) is True
    assert is_retryable_llm_error(ConnectionResetError("WinError 10054")) is True

    assert is_retryable_llm_error(ModelHTTPError(status_code=401, model_name="m")) is False
    assert is_retryable_llm_error(ModelHTTPError(status_code=400, model_name="m")) is False
    assert is_retryable_llm_error(AppError(402, "insufficient_credits", "余额不足")) is False
    assert is_retryable_llm_error(ValueError("bad schema")) is False

    assert retry_backoff_seconds(1) == 5
    assert retry_backoff_seconds(2) == 15
    assert retry_backoff_seconds(3) == 30
    assert retry_backoff_seconds(4) == 30


async def test_assets_extract_streams_per_kind_with_zero_db_hold_and_retries(monkeypatch):
    from app.modules.llm_engine.schema import Asset, AssetResult

    proj_settings = _sample_settings(episode_count=1)
    project = Project(
        id=uuid4(),
        user_id=1,
        name=proj_settings.name,
        mode="story",
        source_text="故事梗概",
        settings=proj_settings.model_dump(),
    )
    now = datetime.now(UTC)
    job = Job(
        id=uuid4(),
        user_id=1,
        project_id=project.id,
        job_type="assets_extract",
        status="queued",
        step_index=0,
        step_total=4,
        step_label="排队中",
        progress=0,
        input_payload={"mode": "full"},
        created_at=now,
        dispatch_after=now,
        next_attempt_at=now,
    )
    db = FakeStepChainDB(project, job)
    db.outline = _sample_outline(1)
    db.episodes[1] = _sample_episode(1)
    redis = FakeEventRedis()
    settings = Settings(environment="test", script_step_max_retries=2)
    persist_calls: list[tuple[bool, list[str]]] = []
    active_sessions_during_llm: list[int] = []

    async def fake_build_script(session, proj):
        return ScriptResult(settings=proj_settings, outline=db.outline, episodes=[db.episodes[1]])

    async def fake_build_assets(session, proj, *, include_variants=True):
        return AssetResult(settings=proj_settings, assets=[])

    async def fake_persist_assets(session, proj, res, *, preserve_edits=False, prune_missing=True):
        persist_calls.append((prune_missing, [a.id for a in res.assets]))
        return res.assets

    attempts = 0

    async def fake_analyze(
        model, script, *, existing=(), usage=None, on_progress=None, on_kind_ready=None
    ):
        nonlocal attempts
        attempts += 1
        active_sessions_during_llm.append(db.active_sessions)
        char_asset = Asset(
            id="C01", kind="character", name="陈默", description="司机", prompt="p1", episodeNumbers=[1]
        )
        scene_asset = Asset(
            id="S01", kind="scene", name="出租车", description="车内", prompt="p2", episodeNumbers=[1]
        )
        if attempts == 1:
            if on_kind_ready is not None:
                await on_kind_ready("character", [char_asset])
            raise ModelHTTPError(status_code=429, model_name="test-model", body="rate limit")

        if on_kind_ready is not None:
            await on_kind_ready("scene", [scene_asset])
        return AssetResult(settings=proj_settings, assets=[char_asset, scene_asset])

    monkeypatch.setattr(ai_tasks, "build_script_result_from_db", fake_build_script)
    monkeypatch.setattr(ai_tasks, "build_asset_result_from_db", fake_build_assets)
    monkeypatch.setattr(ai_tasks, "persist_extracted_assets", fake_persist_assets)
    monkeypatch.setattr(ai_tasks, "analyze_assets", fake_analyze)

    # Attempt 1: character saves incrementally, then 429 triggers backoff retry
    await ai_tasks.run_llm_job_core(
        sessions=db.session_factory,
        redis=redis,
        settings=settings,
        job_id=job.id,
        model_override=(TestModel(), "test-model"),
    )
    assert job.status == "queued"
    assert job.input_payload["stepAttempts"] == 1
    assert "character" in job.input_payload["completedKinds"]
    assert persist_calls == [(False, ["C01"])]

    # Attempt 2: fast-forward backoff, succeeds and runs final prune_missing=True
    job.dispatch_after = datetime.now(UTC) - timedelta(seconds=1)
    await ai_tasks.run_llm_job_core(
        sessions=db.session_factory,
        redis=redis,
        settings=settings,
        job_id=job.id,
        model_override=(TestModel(), "test-model"),
    )
    assert job.status == "succeeded"
    assert job.progress == 100
    assert active_sessions_during_llm == [0, 0]
    assert persist_calls == [
        (False, ["C01"]),
        (False, ["S01"]),
        (True, ["C01", "S01"]),
    ]


def test_job_meta_property_exposes_only_safe_routing_fields() -> None:
    now = datetime.now(UTC)
    job = Job(
        id=uuid4(),
        user_id=1,
        project_id=uuid4(),
        job_type="storyboard_generate",
        target_id="2",
        status="running",
        step_index=2,
        step_total=4,
        step_label="第 2 集已落库 1/3 批",
        progress=40,
        input_payload={
            "action": "episode",
            "episodeNumber": 2,
            "completedBatches": 1,
            "totalBatches": 3,
            "segmentCount": 10,
            "feedback": "绝不能暴露给列表轮询的用户修改意见",
            "lastBlocking": {"segmentId": 4, "blocking": "内部调度状态"},
        },
        created_at=now,
    )
    assert job.job_meta == {
        "action": "episode",
        "episodeNumber": 2,
        "completedBatches": 1,
        "totalBatches": 3,
        "segmentCount": 10,
    }
    dumped = JobOut.model_validate(job).model_dump(by_alias=True)
    assert dumped["jobMeta"] == job.job_meta
    assert "feedback" not in dumped["jobMeta"]
    assert "lastBlocking" not in dumped["jobMeta"]


async def test_storyboard_job_streams_batches_with_zero_db_hold_and_resumes_from_checkpoint(
    monkeypatch,
):
    proj_settings = _sample_settings(episode_count=1)
    project = Project(
        id=uuid4(),
        user_id=1,
        name=proj_settings.name,
        mode="story",
        source_text="雨夜出租车。",
        settings=proj_settings.model_dump(),
    )
    ep_row = DbEpisode(
        id=uuid4(),
        project_id=project.id,
        number=1,
        title="第1集标题",
        summary="第1集梗概",
        script="第一场",
        target_seconds=120,
        seconds=120.0,
    )
    now = datetime.now(UTC)
    job = Job(
        id=uuid4(),
        user_id=1,
        project_id=project.id,
        job_type="storyboard_generate",
        target_id="1",
        status="queued",
        step_index=0,
        step_total=3,
        step_label="第 1 集分镜任务已排队",
        progress=0,
        input_payload={"action": "episode", "episodeNumber": 1},
        created_at=now,
        dispatch_after=now,
        next_attempt_at=now,
    )

    saved_clip_indices: set[int] = set()

    class _StoryboardFakeDB(FakeStepChainDB):
        def session_factory(self):
            db = self

            class _Session:
                async def __aenter__(self):
                    db.active_sessions += 1
                    return self

                async def __aexit__(self, *args):
                    db.active_sessions -= 1
                    return None

                async def scalar(self, stmt):
                    desc = stmt.column_descriptions[0]
                    expr_name = str(desc.get("name") or "")
                    if expr_name == "count" or str(desc.get("expr")).lower().startswith("count("):
                        return len(saved_clip_indices)
                    entity = desc.get("entity")
                    if entity is Job:
                        return db.job
                    if entity is Project:
                        return db.project
                    if entity is DbEpisode:
                        return ep_row
                    if entity is DbStoryboardClip:
                        return None
                    return len(saved_clip_indices)

                async def execute(self, stmt):
                    return None

                async def commit(self) -> None:
                    return None

                async def refresh(self, obj) -> None:
                    return None

            return _Session()

    db = _StoryboardFakeDB(project, job)
    db.outline = _sample_outline(1)
    db.episodes[1] = _sample_episode(1)
    redis = FakeEventRedis()
    settings = Settings(environment="test", script_step_max_retries=2)
    persist_calls: list[tuple[bool, int, list[int]]] = []
    resume_args: list[tuple[int, dict[str, Any] | None]] = []
    active_sessions_during_llm: list[int] = []

    def _dummy_clip(idx: int) -> LlmStoryboardClip:
        return LlmStoryboardClip(
            id=idx,
            durationSeconds=10.0,
            prompt=f"镜头 {idx} 提示词",
            assetIds=["C01"],
            references=[],
            beats=(idx, idx),
            blocking=f"blocking-{idx}",
            cuts=[],
        )

    async def fake_build_script(session, proj):
        return ScriptResult(settings=proj_settings, outline=db.outline, episodes=[db.episodes[1]])

    async def fake_build_assets(session, proj, *, include_variants=True):
        return AssetResult(
            settings=proj_settings,
            assets=[
                Asset(
                    id="C01",
                    kind="character",
                    name="陈默",
                    description="司机",
                    prompt="p1",
                    episodeNumbers=[1],
                )
            ],
        )

    async def fake_persist_batch(
        session, proj, *, episode_number, clips, replace_existing=False
    ):
        if replace_existing:
            saved_clip_indices.clear()
        for clip in clips:
            saved_clip_indices.add(clip.id)
        persist_calls.append((replace_existing, episode_number, [c.id for c in clips]))
        return len(clips)

    attempts = 0

    async def fake_storyboard_episode(
        model,
        episode,
        script,
        assets,
        *,
        feedback="",
        initial_blocking=None,
        start_batch_index=1,
        usage=None,
        on_progress=None,
        on_batch_ready=None,
    ):
        nonlocal attempts
        attempts += 1
        active_sessions_during_llm.append(db.active_sessions)
        resume_args.append((start_batch_index, initial_blocking))
        if attempts == 1:
            assert start_batch_index == 1
            assert initial_blocking is None
            if on_batch_ready is not None:
                await on_batch_ready(
                    1,
                    2,
                    [_dummy_clip(i) for i in range(1, 5)],
                    {"segmentId": 4, "blocking": "b1"},
                )
            raise ModelHTTPError(status_code=429, model_name="test-model", body="rate limit")

        assert start_batch_index == 2
        assert initial_blocking == {"segmentId": 4, "blocking": "b1"}
        if on_batch_ready is not None:
            await on_batch_ready(
                2,
                2,
                [_dummy_clip(5), _dummy_clip(6)],
                {"segmentId": 6, "blocking": "b2"},
            )
        return None

    monkeypatch.setattr(ai_tasks, "build_script_result_from_db", fake_build_script)
    monkeypatch.setattr(ai_tasks, "build_asset_result_from_db", fake_build_assets)
    monkeypatch.setattr(ai_tasks, "persist_storyboard_batch", fake_persist_batch)
    monkeypatch.setattr(ai_tasks, "split_episode", lambda ep, cap: list(range(6)))
    monkeypatch.setattr(ai_tasks, "storyboard_episode", fake_storyboard_episode)

    # Attempt 1: batch 1 commits atomically then 429 schedules auto-retry with checkpoint
    await ai_tasks.run_llm_job_core(
        sessions=db.session_factory,
        redis=redis,
        settings=settings,
        job_id=job.id,
        model_override=(TestModel(), "test-model"),
    )
    assert job.status == "queued"
    assert job.input_payload["stepAttempts"] == 1
    assert job.input_payload["completedBatches"] == 1
    assert job.input_payload["totalBatches"] == 2
    assert job.input_payload["segmentCount"] == 6
    assert job.input_payload["lastBlocking"] == {"segmentId": 4, "blocking": "b1"}
    assert persist_calls == [(True, 1, [1, 2, 3, 4])]

    # Attempt 2: resumes at batch 2 using lastBlocking, completes cleanly
    job.dispatch_after = datetime.now(UTC) - timedelta(seconds=1)
    await ai_tasks.run_llm_job_core(
        sessions=db.session_factory,
        redis=redis,
        settings=settings,
        job_id=job.id,
        model_override=(TestModel(), "test-model"),
    )
    assert job.status == "succeeded"
    assert job.progress == 100
    assert active_sessions_during_llm == [0, 0]
    assert resume_args == [(1, None), (2, {"segmentId": 4, "blocking": "b1"})]
    assert "lastBlocking" not in job.input_payload
    assert job.input_payload["completedBatches"] == 2
    assert job.result_payload == {
        "projectId": str(project.id),
        "episodeNumber": 1,
        "episodes": [1],
        "clipCount": 6,
    }
    assert persist_calls == [
        (True, 1, [1, 2, 3, 4]),
        (False, 1, [5, 6]),
    ]


