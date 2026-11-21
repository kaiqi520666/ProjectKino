import base64
import json
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.auth.models import User
from app.modules.catalog.models import AiModel, AiProvider
from app.modules.credits.models import CreditLedger, CreditReservation
from app.modules.jobs.models import Job
from app.modules.media_providers.cangyuan_image import (
    CangyuanImageAdapter,
    ImageProviderResult,
    MediaProviderError,
    asset_aspect_ratio,
)
from app.modules.media_providers.cc_video import CcVideoAdapter, VideoProviderResult
from app.modules.storage.media import detect_image_format
from app.modules.storage.oss import OssConfig, OssStorage, parse_oss_config
from app.modules.studio.models import Episode, ProjectAsset, StoryboardClip
from app.workers.ai_tasks import run_asset_image_job_core, run_clip_video_job_core
from app.workers.media_tasks import run_episode_compose_job_core

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class FakePubSubRedis:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(self, channel: str, payload: str) -> int:
        self.events.append({"channel": channel, "data": json.loads(payload)})
        return 1


class FakeOssStorage(OssStorage):
    def __init__(self) -> None:
        super().__init__(
            OssConfig(
                endpoint="https://oss-cn-hangzhou.aliyuncs.com",
                bucket="demo-bucket",
                access_key_id="ak-id",
                access_key_secret="ak-secret",
                public_domain="https://cdn.example.com",
                prefix="framedrama",
            )
        )
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put_bytes(self, key: str, body: bytes, mime_type: str) -> None:
        self.objects[key] = (body, mime_type)

    def put_file(self, key: str, path: str, mime_type: str) -> None:
        self.objects[key] = (Path(path).read_bytes(), mime_type)

    def download_file(self, key: str, path: str, max_bytes: int = 500 * 1024 * 1024) -> int:
        body, _ = self.objects[key]
        Path(path).write_bytes(body)
        return len(body)


class InMemoryMediaDB:
    def __init__(self) -> None:
        self.users: dict[int, User] = {}
        self.providers: dict[int, AiProvider] = {}
        self.models: dict[str, AiModel] = {}
        self.jobs: dict[UUID, Job] = {}
        self.assets: dict[UUID, ProjectAsset] = {}
        self.clips: dict[UUID, StoryboardClip] = {}
        self.episodes: dict[UUID, Episode] = {}
        self.reservations: dict[UUID, CreditReservation] = {}
        self.ledgers: list[CreditLedger] = []

    def session_factory(self):
        db = self

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            def add(self, obj) -> None:
                if isinstance(obj, CreditLedger):
                    if obj.id is None:
                        obj.id = uuid4()
                    db.ledgers.append(obj)
                elif isinstance(obj, CreditReservation):
                    if obj.id is None:
                        obj.id = uuid4()
                    db.reservations[obj.id] = obj

            async def flush(self) -> None:
                return None

            async def commit(self) -> None:
                return None

            async def refresh(self, obj) -> None:
                return None

            async def execute(self, stmt):
                return None

            async def scalars(self, stmt):
                entity = stmt.column_descriptions[0]["entity"]
                params = list(stmt.compile().params.values())
                if entity is StoryboardClip:
                    ep_id = params[0]
                    rows = [c for c in db.clips.values() if c.episode_id == ep_id]
                    return sorted(rows, key=lambda item: item.clip_index)
                raise NotImplementedError(f"Unsupported scalars entity {entity}")

            async def scalar(self, stmt):
                entity = stmt.column_descriptions[0]["entity"]
                params = list(stmt.compile().params.values())
                if entity is User:
                    return db.users.get(params[0])
                if entity is Job:
                    return db.jobs.get(params[0])
                if entity is ProjectAsset:
                    return db.assets.get(params[0])
                if entity is StoryboardClip:
                    return db.clips.get(params[0])
                if entity is Episode:
                    return db.episodes.get(params[0])
                if entity is AiModel:
                    return db.models.get(params[0])
                if entity is AiProvider:
                    return db.providers.get(params[0])
                if entity is CreditReservation:
                    if len(params) == 1:
                        return db.reservations.get(params[0])
                    btype, bid = params[0], params[1]
                    return next(
                        (
                            r
                            for r in db.reservations.values()
                            if r.business_type == btype and r.business_id == bid
                        ),
                        None,
                    )
                if entity is CreditLedger:
                    key = params[0]
                    return next((row for row in db.ledgers if row.idempotency_key == key), None)
                raise NotImplementedError(f"Unsupported entity {entity}")

        return _Session()


def test_oss_config_and_upload_policy_support_moonflow_keys_and_isolated_prefix():
    cfg = parse_oss_config(
        {
            "endpoint": "https://my-bucket.oss-cn-shanghai.aliyuncs.com",
            "bucket": "my-bucket",
            "accessKeyId": "ak-123",
            "accessKeySecret": "sk-456",
            "publicDomain": "cdn.framedrama.ai",
        }
    )
    assert cfg.endpoint == "https://oss-cn-shanghai.aliyuncs.com"
    assert cfg.public_domain == "https://cdn.framedrama.ai"
    assert cfg.prefix == "framedrama"

    storage = OssStorage(cfg)
    policy = storage.upload_policy(
        user_id=7,
        kind="image",
        file_name="hero.PNG",
        mime_type="image/png",
        size=1024,
    )
    assert policy["host"] == "https://my-bucket.oss-cn-shanghai.aliyuncs.com"
    assert policy["key"].startswith("framedrama/7/images/")
    assert policy["key"].endswith(".png")
    assert policy["url"].startswith("https://cdn.framedrama.ai/framedrama/7/images/")
    decoded = json.loads(base64.b64decode(policy["fields"]["policy"]).decode("utf-8"))
    assert ["content-length-range", 1024, 1024] in decoded["conditions"]

    with pytest.raises(AppError):
        parse_oss_config({"endpoint": "", "bucket": ""})


def test_detect_image_format_and_aspect_ratio_rules():
    assert detect_image_format(_PNG_BYTES) == ("png", "image/png")
    assert detect_image_format(b"\xff\xd8\xff\xe0abc") == ("jpg", "image/jpeg")
    assert detect_image_format(b"RIFF1234WEBPdata") == ("webp", "image/webp")
    with pytest.raises(ValueError):
        detect_image_format(b"not-an-image")

    assert asset_aspect_ratio("character") == "16:9"
    assert asset_aspect_ratio("scene") == "16:9"
    assert asset_aspect_ratio("prop") == "1:1"


def test_cangyuan_and_cc_adapters_payload_and_parse():
    cy = CangyuanImageAdapter()
    payload_web, ep = cy.build_payload(
        upstream_model_id="gpt-image-2", prompt="测试提示词", tier="web", ratio="16:9"
    )
    assert ep == "generations"
    assert "quality" not in payload_web
    assert payload_web["async"] is True

    payload_2k, _ = cy.build_payload(
        upstream_model_id="gpt-image-2.5", prompt="道具图", tier="2k", ratio="1:1"
    )
    assert payload_2k["quality"] == "high"
    assert payload_2k["size"] == "1:1"

    assert cy.parse({"data": {"task_id": "t1", "status": "queued"}}).status == "pending"
    done = cy.parse({"data": {"id": "t1", "data": [{"url": "https://img.example/a.png"}]}})
    assert done.status == "completed" and done.url == "https://img.example/a.png"
    assert cy.parse({"status": "failed", "message": "敏感内容"}).status == "failed"

    cc = CcVideoAdapter()
    v_payload = cc.build_payload(
        upstream_model_id="seedance-2.5",
        prompt="图片1人物推门",
        reference_urls=["https://cdn.example/1.png", "https://cdn.example/2.png"],
        ratio="16:9",
        resolution="1080p",
        duration=25,
    )
    assert v_payload["input"]["media"] == [
        {"type": "reference_image", "url": "https://cdn.example/1.png"},
        {"type": "reference_image", "url": "https://cdn.example/2.png"},
    ]
    assert v_payload["parameters"] == {"ratio": "16:9", "resolution": "1080p", "duration": 25}

    v_pending = cc.parse({"id": "vid-1", "status": "RUNNING", "progress": 64})
    assert v_pending.status == "pending" and v_pending.progress == 64
    v_done = cc.parse({"id": "vid-1", "status": "SUCCEEDED", "object": "https://cc.example/out.mp4"})
    assert v_done.status == "completed" and v_done.url == "https://cc.example/out.mp4"
    assert cc.parse({"id": "vid-1", "status": "FAILED:NSFW"}).status == "failed"


def _seed_image_fixture(db: InMemoryMediaDB, *, existing_url: str | None = None) -> tuple[UUID, UUID, UUID]:
    user = User(
        id=1,
        email="u@test.local",
        password_hash="scrypt:a:b",
        nickname="tester",
        role="user",
        status="active",
        balance=Decimal("98.0000"),
        frozen=Decimal("2.0000"),
        usage_multiplier=Decimal("1.0000"),
    )
    provider = AiProvider(
        id=10,
        key="cangyuan",
        display_name="沧元图片",
        base_url="https://cy.example",
        api_key="secret-cy",
        adapter="cangyuanImageV1",
        auth_type="bearer",
        enabled=True,
        configuration={"timeoutMs": 15000},
    )
    model = AiModel(
        id="gpt-image-2",
        provider_id=10,
        media_type="image",
        display_name="GPT Image 2",
        upstream_model_id="gpt-image-2",
        enabled=True,
        is_default=True,
        sort=10,
        capabilities={"tiers": ["web", "1k", "2k", "4k"]},
        defaults={"tier": "1k"},
        parameter_bindings={},
        configuration={},
    )
    project_id = uuid4()
    asset_id = uuid4()
    job_id = uuid4()
    asset = ProjectAsset(
        id=asset_id,
        project_id=project_id,
        asset_code="C01",
        kind="character",
        name="林晚",
        description="主角",
        prompt="电影写实角色三视图",
        voice="",
        episode_numbers=[1],
        image_url=existing_url,
        image_status="generating",
    )
    job = Job(
        id=job_id,
        user_id=1,
        project_id=project_id,
        job_type="asset_image",
        target_id=str(asset_id),
        status="queued",
        step_index=0,
        step_total=4,
        step_label="排队中",
        progress=0,
        input_payload={"assetId": str(asset_id), "modelId": "gpt-image-2", "tier": "1k", "ratio": "16:9"},
    )
    res_id = uuid4()
    reservation = CreditReservation(
        id=res_id,
        user_id=1,
        business_type="image",
        business_id=job_id,
        model_id="gpt-image-2",
        amount=Decimal("2.0000"),
        consumed=None,
        status="frozen",
        rate_snapshot={"tier": "1k"},
    )
    db.users[1] = user
    db.providers[10] = provider
    db.models["gpt-image-2"] = model
    db.assets[asset_id] = asset
    db.jobs[job_id] = job
    db.reservations[res_id] = reservation
    return job_id, asset_id, res_id


async def test_asset_image_worker_settles_on_success():
    db = InMemoryMediaDB()
    job_id, asset_id, res_id = _seed_image_fixture(db)
    storage = FakeOssStorage()
    redis = FakePubSubRedis()

    class StubCyAdapter(CangyuanImageAdapter):
        def __init__(self) -> None:
            self.queries = 0

        async def submit(self, **kwargs) -> ImageProviderResult:
            return ImageProviderResult(task_id="cy-task-1", status="pending")

        async def query(self, **kwargs) -> ImageProviderResult:
            self.queries += 1
            if self.queries == 1:
                return ImageProviderResult(task_id="cy-task-1", status="pending")
            return ImageProviderResult(
                task_id="cy-task-1", status="completed", url="https://upstream.example/out.png"
            )

    async def fake_download(_url: str) -> bytes:
        return _PNG_BYTES

    await run_asset_image_job_core(
        sessions=db.session_factory,
        redis=redis,
        settings=Settings(environment="test"),
        job_id=job_id,
        adapter=StubCyAdapter(),
        storage_loader=lambda _s: _async_return(storage),
        downloader=fake_download,
        poll_interval_seconds=0.0,
    )

    assert db.jobs[job_id].status == "succeeded"
    assert db.jobs[job_id].provider_task_id == "cy-task-1"
    assert db.assets[asset_id].image_status == "ready"
    assert db.assets[asset_id].image_url == f"https://cdn.example.com/framedrama/1/images/{job_id}.png"
    assert db.reservations[res_id].status == "settled"
    assert db.users[1].frozen == Decimal("0.0000")
    assert db.users[1].balance == Decimal("98.0000")


async def test_asset_image_worker_releases_on_rejection_and_reviews_on_uncertain():
    # Case 1: Definitive rejection -> release credits & keep old image intact
    db1 = InMemoryMediaDB()
    job1, asset1, res1 = _seed_image_fixture(db1, existing_url="https://cdn.example.com/old.png")

    class RejectAdapter(CangyuanImageAdapter):
        async def submit(self, **kwargs) -> ImageProviderResult:
            raise MediaProviderError("providerRejected", "提示词违规", rejected=True)

    await run_asset_image_job_core(
        sessions=db1.session_factory,
        redis=FakePubSubRedis(),
        settings=Settings(environment="test"),
        job_id=job1,
        adapter=RejectAdapter(),
        storage_loader=lambda _s: _async_return(FakeOssStorage()),
        poll_interval_seconds=0.0,
    )
    assert db1.jobs[job1].status == "failed"
    assert db1.reservations[res1].status == "released"
    assert db1.users[1].balance == Decimal("100.0000")
    assert db1.users[1].frozen == Decimal("0.0000")
    assert db1.assets[asset1].image_status == "ready"
    assert db1.assets[asset1].image_url == "https://cdn.example.com/old.png"

    # Case 2: Uncertain timeout -> status=review, reservation stays frozen
    db2 = InMemoryMediaDB()
    job2, _asset2, res2 = _seed_image_fixture(db2)

    class TimeoutAdapter(CangyuanImageAdapter):
        async def submit(self, **kwargs) -> ImageProviderResult:
            raise MediaProviderError("submissionUnknown", "网络超时状态不明", uncertain=True)

    await run_asset_image_job_core(
        sessions=db2.session_factory,
        redis=FakePubSubRedis(),
        settings=Settings(environment="test"),
        job_id=job2,
        adapter=TimeoutAdapter(),
        storage_loader=lambda _s: _async_return(FakeOssStorage()),
        poll_interval_seconds=0.0,
    )
    assert db2.jobs[job2].status == "review"
    assert db2.reservations[res2].status == "frozen"
    assert db2.users[1].frozen == Decimal("2.0000")


async def test_clip_video_and_free_episode_compose_workers():
    db = InMemoryMediaDB()
    storage = FakeOssStorage()
    redis = FakePubSubRedis()
    project_id = uuid4()
    episode_id = uuid4()
    clip_id = uuid4()
    vid_job_id = uuid4()
    res_id = uuid4()

    db.users[1] = User(
        id=1,
        email="v@test.local",
        password_hash="scrypt:a:b",
        nickname="v",
        role="user",
        status="active",
        balance=Decimal("70.0000"),
        frozen=Decimal("30.0000"),
        usage_multiplier=Decimal("1.0000"),
    )
    db.providers[20] = AiProvider(
        id=20,
        key="cc",
        display_name="CC 视频",
        base_url="https://cc.example",
        api_key="secret-cc",
        adapter="ccVideoV1",
        auth_type="bearer",
        enabled=True,
        configuration={"timeoutMs": 15000},
    )
    db.models["seedance-2.0"] = AiModel(
        id="seedance-2.0",
        provider_id=20,
        media_type="video",
        display_name="Seedance 2.0",
        upstream_model_id="seedance-2.0",
        enabled=True,
        is_default=True,
        sort=10,
        capabilities={"maxDuration": 15, "resolutions": ["720p", "1080p"]},
        defaults={"resolution": "720p", "duration": 15},
        parameter_bindings={},
        configuration={},
    )
    db.episodes[episode_id] = Episode(
        id=episode_id, project_id=project_id, number=1, title="第一集"
    )
    db.clips[clip_id] = StoryboardClip(
        id=clip_id,
        project_id=project_id,
        episode_id=episode_id,
        clip_index=1,
        duration_seconds=15,
        prompt="图片1人物推开卧室门",
        references=[],
        video_status="generating",
    )
    db.jobs[vid_job_id] = Job(
        id=vid_job_id,
        user_id=1,
        project_id=project_id,
        job_type="clip_video",
        target_id=str(clip_id),
        status="queued",
        step_index=0,
        step_total=4,
        step_label="排队中",
        progress=0,
        input_payload={
            "clipId": str(clip_id),
            "modelId": "seedance-2.0",
            "resolution": "720p",
            "ratio": "16:9",
            "durationSeconds": 15,
            "prompt": "图片1人物推开卧室门",
            "referenceUrls": ["https://cdn.example.com/ref1.png"],
        },
    )
    db.reservations[res_id] = CreditReservation(
        id=res_id,
        user_id=1,
        business_type="video",
        business_id=vid_job_id,
        model_id="seedance-2.0",
        amount=Decimal("30.0000"),
        consumed=None,
        status="frozen",
        rate_snapshot={"durationSeconds": 15},
    )

    class StubCcAdapter(CcVideoAdapter):
        def __init__(self) -> None:
            self.polls = 0

        async def submit(self, **kwargs) -> VideoProviderResult:
            return VideoProviderResult(task_id="cc-job-99", status="pending", progress=10)

        async def query(self, **kwargs) -> VideoProviderResult:
            self.polls += 1
            if self.polls == 1:
                return VideoProviderResult(task_id="cc-job-99", status="pending", progress=55)
            return VideoProviderResult(
                task_id="cc-job-99",
                status="completed",
                progress=100,
                url="https://cc.example/clip1.mp4",
            )

    async def fake_download_file(_url: str, dest: Path) -> int:
        dest.write_bytes(b"fake-mp4-bytes")  # noqa: ASYNC240
        return 14

    async def fake_probe(_path: Path, **_kwargs) -> float:
        return 14.92

    await run_clip_video_job_core(
        sessions=db.session_factory,
        redis=redis,
        settings=Settings(environment="test"),
        job_id=vid_job_id,
        adapter=StubCcAdapter(),
        storage_loader=lambda _s: _async_return(storage),
        file_downloader=fake_download_file,
        duration_prober=fake_probe,
        poll_interval_seconds=0.0,
        enforce_min_interval=False,
    )

    assert db.jobs[vid_job_id].status == "succeeded"
    assert db.clips[clip_id].video_status == "ready"
    assert db.clips[clip_id].video_key == f"framedrama/1/videos/{vid_job_id}.mp4"
    assert db.reservations[res_id].status == "settled"
    assert db.users[1].frozen == Decimal("0.0000")
    assert db.users[1].balance == Decimal("70.0000")

    # Now run free FFmpeg compose job on the completed clip
    compose_job_id = uuid4()
    db.jobs[compose_job_id] = Job(
        id=compose_job_id,
        user_id=1,
        project_id=project_id,
        job_type="episode_compose",
        target_id=str(episode_id),
        status="queued",
        step_index=0,
        step_total=4,
        step_label="合成排队中",
        progress=0,
        input_payload={"episodeId": str(episode_id), "episodeNumber": 1, "clipCount": 1},
    )

    async def fake_compose(clip_paths: list[Path], output_path: Path, **_kwargs) -> float:
        assert len(clip_paths) == 1
        assert clip_paths[0].read_bytes() == b"fake-mp4-bytes"  # noqa: ASYNC240
        output_path.write_bytes(b"composed-mp4")  # noqa: ASYNC240
        return 14.92

    await run_episode_compose_job_core(
        sessions=db.session_factory,
        redis=redis,
        settings=Settings(environment="test"),
        job_id=compose_job_id,
        storage_loader=lambda _s: _async_return(storage),
        composer=fake_compose,
    )

    assert db.jobs[compose_job_id].status == "succeeded"
    assert db.episodes[episode_id].composed_duration == 14.92
    assert db.episodes[episode_id].composed_video_url == (
        f"https://cdn.example.com/framedrama/1/episodes/{episode_id}/{compose_job_id}.mp4"
    )
    # Free compose must not alter user credits
    assert db.users[1].balance == Decimal("70.0000")
    assert db.users[1].frozen == Decimal("0.0000")


async def test_asset_image_worker_enforces_concurrency_semaphore():
    import asyncio

    db = InMemoryMediaDB()
    storage = FakeOssStorage()
    redis = FakePubSubRedis()
    job_ids: list[UUID] = []

    # Seed 1 shared user/provider/model + 6 independent image jobs
    first_job, _, _ = _seed_image_fixture(db)
    db.users[1].balance = Decimal("88.0000")
    db.users[1].frozen = Decimal("12.0000")
    job_ids.append(first_job)
    project_id = db.jobs[first_job].project_id
    for idx in range(2, 7):
        aid = uuid4()
        jid = uuid4()
        rid = uuid4()
        db.assets[aid] = ProjectAsset(
            id=aid,
            project_id=project_id,
            asset_code=f"C0{idx}",
            kind="character",
            name=f"角色{idx}",
            description="d",
            prompt="测试提示词",
            voice="",
            episode_numbers=[1],
            image_status="generating",
        )
        db.jobs[jid] = Job(
            id=jid,
            user_id=1,
            project_id=project_id,
            job_type="asset_image",
            target_id=str(aid),
            status="queued",
            step_index=0,
            step_total=4,
            step_label="排队",
            progress=0,
            input_payload={"assetId": str(aid), "modelId": "gpt-image-2", "tier": "1k", "ratio": "16:9"},
        )
        db.reservations[rid] = CreditReservation(
            id=rid,
            user_id=1,
            business_type="image",
            business_id=jid,
            model_id="gpt-image-2",
            amount=Decimal("2.0000"),
            consumed=None,
            status="frozen",
            rate_snapshot={"tier": "1k"},
        )
        job_ids.append(jid)

    in_flight = 0
    peak = 0

    class SlowStubAdapter(CangyuanImageAdapter):
        async def submit(self, **kwargs) -> ImageProviderResult:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.03)
            in_flight -= 1
            return ImageProviderResult(
                task_id=f"t-{uuid4().hex[:6]}",
                status="completed",
                url="https://upstream.example/out.png",
            )

    async def fake_download(_url: str) -> bytes:
        return _PNG_BYTES

    sem = asyncio.Semaphore(2)
    await asyncio.gather(
        *(
            run_asset_image_job_core(
                sessions=db.session_factory,
                redis=redis,
                settings=Settings(environment="test", image_concurrency=2),
                job_id=jid,
                adapter=SlowStubAdapter(),
                storage_loader=lambda _s: _async_return(storage),
                downloader=fake_download,
                poll_interval_seconds=0.0,
                concurrency_semaphore=sem,
            )
            for jid in job_ids
        )
    )
    assert peak == 2
    assert all(db.jobs[jid].status == "succeeded" for jid in job_ids)
    assert db.users[1].frozen == Decimal("0.0000")


async def test_clip_video_worker_enforces_concurrency_semaphore():
    import asyncio

    db = InMemoryMediaDB()
    storage = FakeOssStorage()
    redis = FakePubSubRedis()
    project_id = uuid4()
    episode_id = uuid4()

    db.users[1] = User(
        id=1,
        email="bv@test.local",
        password_hash="scrypt:a:b",
        nickname="bv",
        role="user",
        status="active",
        balance=Decimal("50.0000"),
        frozen=Decimal("50.0000"),
        usage_multiplier=Decimal("1.0000"),
    )
    db.providers[20] = AiProvider(
        id=20,
        key="cc",
        display_name="CC 视频",
        base_url="https://cc.example",
        api_key="secret-cc",
        adapter="ccVideoV1",
        auth_type="bearer",
        enabled=True,
        configuration={"timeoutMs": 15000},
    )
    db.models["seedance-2.0"] = AiModel(
        id="seedance-2.0",
        provider_id=20,
        media_type="video",
        display_name="Seedance 2.0",
        upstream_model_id="sd-2-c4",
        enabled=True,
        is_default=True,
        sort=10,
        capabilities={"maxDuration": 15, "resolutions": ["720p"]},
        defaults={"resolution": "720p", "duration": 15},
        parameter_bindings={},
        configuration={},
    )
    db.episodes[episode_id] = Episode(id=episode_id, project_id=project_id, number=1, title="第一集")

    job_ids: list[UUID] = []
    for idx in range(1, 6):
        cid = uuid4()
        jid = uuid4()
        rid = uuid4()
        db.clips[cid] = StoryboardClip(
            id=cid,
            project_id=project_id,
            episode_id=episode_id,
            clip_index=idx,
            duration_seconds=5,
            prompt=f"片段 {idx} 提示词",
            references=[],
            video_status="generating",
        )
        db.jobs[jid] = Job(
            id=jid,
            user_id=1,
            project_id=project_id,
            job_type="clip_video",
            target_id=str(cid),
            status="queued",
            step_index=0,
            step_total=4,
            step_label="排队",
            progress=0,
            input_payload={
                "clipId": str(cid),
                "modelId": "seedance-2.0",
                "resolution": "720p",
                "ratio": "16:9",
                "durationSeconds": 5,
                "prompt": f"片段 {idx} 提示词",
                "referenceUrls": [],
            },
        )
        db.reservations[rid] = CreditReservation(
            id=rid,
            user_id=1,
            business_type="video",
            business_id=jid,
            model_id="seedance-2.0",
            amount=Decimal("10.0000"),
            consumed=None,
            status="frozen",
            rate_snapshot={"durationSeconds": 5},
        )
        job_ids.append(jid)

    in_flight = 0
    peak = 0

    class SlowCcAdapter(CcVideoAdapter):
        async def submit(self, **kwargs) -> VideoProviderResult:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.03)
            in_flight -= 1
            return VideoProviderResult(
                task_id=f"cc-{uuid4().hex[:6]}",
                status="completed",
                progress=100,
                url="https://cc.example/out.mp4",
            )

    async def fake_download(_url: str, dest: Path) -> int:
        dest.write_bytes(b"mp4")  # noqa: ASYNC240
        return 3

    async def fake_probe(_path: Path, **_kwargs) -> float:
        return 5.0

    sem = asyncio.Semaphore(2)
    await asyncio.gather(
        *(
            run_clip_video_job_core(
                sessions=db.session_factory,
                redis=redis,
                settings=Settings(environment="test", video_concurrency=2),
                job_id=jid,
                adapter=SlowCcAdapter(),
                storage_loader=lambda _s: _async_return(storage),
                file_downloader=fake_download,
                duration_prober=fake_probe,
                poll_interval_seconds=0.0,
                enforce_min_interval=False,
                concurrency_semaphore=sem,
            )
            for jid in job_ids
        )
    )
    assert peak == 2
    assert all(db.jobs[jid].status == "succeeded" for jid in job_ids)
    assert db.users[1].frozen == Decimal("0.0000")


async def _async_return(value):
    return value
