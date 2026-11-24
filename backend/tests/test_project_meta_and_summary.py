from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.errors import AppError
from app.modules.studio.models import Project
from app.modules.studio.schemas import UpdateProjectRequest
from app.modules.studio.service import list_user_projects, update_project_meta


class _StubResult:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def all(self) -> list[tuple]:
        return list(self._rows)


class _StubListSession:
    def __init__(
        self,
        *,
        projects: list[Project],
        execute_results: list[list[tuple]],
    ) -> None:
        self._projects = projects
        self._execute_results = list(execute_results)

    async def scalars(self, _stmt):
        return self._projects

    async def execute(self, _stmt):
        rows = self._execute_results.pop(0) if self._execute_results else []
        return _StubResult(rows)


class _StubMetaSession:
    def __init__(self, models_by_id: dict[str, SimpleNamespace] | None = None) -> None:
        self._models = models_by_id or {}
        self.flushed = False
        self._scalar_queue: list[SimpleNamespace | None] = []

    def queue_scalars(self, *values: SimpleNamespace | None) -> None:
        self._scalar_queue.extend(values)

    async def scalar(self, _stmt):
        if self._scalar_queue:
            return self._scalar_queue.pop(0)
        return None

    async def flush(self) -> None:
        self.flushed = True


def _make_project(**overrides) -> Project:
    now = datetime.now(UTC)
    defaults = {
        "id": uuid4(),
        "user_id": 1,
        "name": "旧项目名",
        "mode": "story",
        "source_text": "一段故事",
        "settings": {
            "name": "旧项目名",
            "ratio": "16:9",
            "language": "zh-CN",
            "visualStyle": "live-action",
            "episodeCount": 5,
            "maxSegmentDuration": 15,
            "secondsPerEpisode": 120,
            "backgroundMusic": True,
        },
        "outline": None,
        "cover_key": None,
        "cover_url": None,
        "script_confirmed": True,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return Project(**defaults)


def test_update_project_request_validation():
    req = UpdateProjectRequest.model_validate(
        {
            "name": "  新名字  ",
            "ratio": "9:16",
            "visualStyle": "cinematic-2d",
            "visualStyleLabel": "二次元电影感",
            "maxSegmentDuration": 30,
            "backgroundMusic": False,
            "imageModelId": "gpt-image-2",
            "imageTier": "2k",
            "videoModelId": "vid-30s",
            "coverUrl": "https://cdn.example.com/cover.png",
            "coverKey": "framedrama/1/images/cover.png",
        }
    )
    assert req.name == "新名字"
    assert req.ratio == "9:16"
    assert req.max_segment_duration == 30
    assert req.cover_url == "https://cdn.example.com/cover.png"

    with pytest.raises(ValidationError):
        UpdateProjectRequest.model_validate({"name": "   "})

    with pytest.raises(ValidationError):
        UpdateProjectRequest.model_validate({"coverUrl": "blob:http://localhost:5173/abc"})


@pytest.mark.asyncio
async def test_update_project_meta_updates_settings_and_cover():
    project = _make_project()
    session = _StubMetaSession()
    session.queue_scalars(
        SimpleNamespace(id="gpt-image-2", display_name="GPT Image 2", media_type="image"),
        SimpleNamespace(
            id="vid-30s",
            display_name="Seedance 30s",
            media_type="video",
            capabilities={"maxDuration": 30},
        ),
    )

    body = UpdateProjectRequest.model_validate(
        {
            "name": "都市悬疑",
            "ratio": "9:16",
            "visualStyle": "noir-comic",
            "visualStyleLabel": "暗黑漫画风",
            "maxSegmentDuration": 30,
            "backgroundMusic": False,
            "imageModelId": "gpt-image-2",
            "imageTier": "2k",
            "videoModelId": "vid-30s",
            "coverUrl": "https://cdn.example.com/p1.png",
            "coverKey": "framedrama/1/images/p1.png",
        }
    )
    updated = await update_project_meta(session, project=project, body=body)  # type: ignore[arg-type]

    assert session.flushed is True
    assert updated.name == "都市悬疑"
    assert updated.settings["name"] == "都市悬疑"
    assert updated.settings["ratio"] == "9:16"
    assert updated.settings["visualStyle"] == "noir-comic"
    assert updated.settings["visualStyleLabel"] == "暗黑漫画风"
    assert updated.settings["maxSegmentDuration"] == 30
    assert updated.settings["backgroundMusic"] is False
    assert updated.settings["imageModelId"] == "gpt-image-2"
    assert updated.settings["imageTier"] == "2k"
    assert updated.settings["videoModelId"] == "vid-30s"
    assert updated.cover_url == "https://cdn.example.com/p1.png"
    assert updated.cover_key == "framedrama/1/images/p1.png"

    clear_body = UpdateProjectRequest.model_validate({"coverUrl": None, "imageModelId": None})
    await update_project_meta(session, project=updated, body=clear_body)  # type: ignore[arg-type]
    assert updated.cover_url is None
    assert updated.cover_key is None
    assert "imageModelId" not in updated.settings


@pytest.mark.asyncio
async def test_update_project_meta_rejects_incompatible_30s_video_model():
    project = _make_project()
    session = _StubMetaSession()
    session.queue_scalars(
        SimpleNamespace(
            id="vid-15s",
            display_name="Fast 15s",
            media_type="video",
            capabilities={"maxDuration": 15},
        )
    )

    body = UpdateProjectRequest.model_validate(
        {"maxSegmentDuration": 30, "videoModelId": "vid-15s"}
    )
    with pytest.raises(AppError) as exc_info:
        await update_project_meta(session, project=project, body=body)  # type: ignore[arg-type]
    assert exc_info.value.code == "video_model_duration_incompatible"


@pytest.mark.asyncio
async def test_update_project_meta_clears_old_15s_model_when_switching_to_30s():
    project = _make_project(
        settings={
            "name": "旧项目名",
            "ratio": "16:9",
            "language": "zh-CN",
            "visualStyle": "live-action",
            "episodeCount": 5,
            "maxSegmentDuration": 15,
            "videoModelId": "vid-15s",
        }
    )
    session = _StubMetaSession()
    session.queue_scalars(
        SimpleNamespace(
            id="vid-15s",
            display_name="Fast 15s",
            media_type="video",
            capabilities={"maxDuration": 15},
        )
    )

    body = UpdateProjectRequest.model_validate({"maxSegmentDuration": 30})
    updated = await update_project_meta(session, project=project, body=body)  # type: ignore[arg-type]
    assert updated.settings["maxSegmentDuration"] == 30
    assert "videoModelId" not in updated.settings


@pytest.mark.asyncio
async def test_list_user_projects_aggregates_progress_and_auto_covers():
    p1 = _make_project(name="项目一", cover_url="https://cdn.example.com/custom.png")
    p2 = _make_project(name="项目二", settings={"name": "项目二", "episodeCount": 4})

    session = _StubListSession(
        projects=[p1, p2],
        execute_results=[
            # Episode counts & composed counts
            [(p1.id, 5, 3), (p2.id, 4, 0)],
            # Asset counts & ready image counts
            [(p1.id, 10, 8), (p2.id, 6, 0)],
            # Clip stats: (project_id, storyboard_ep_count, clip_count, clip_video_ready_count)
            [(p1.id, 4, 20, 16), (p2.id, 2, 8, 2)],
            # Asset auto covers (p1 has scene image; p2 has none)
            [(p1.id, "https://cdn.example.com/scene1.png")],
            # Fallback clip preview covers for missing projects (p2)
            [(p2.id, "https://cdn.example.com/clip-preview.png")],
        ],
    )

    items = await list_user_projects(session, user_id=1)  # type: ignore[arg-type]
    assert len(items) == 2

    first, second = items
    assert first.cover_url == "https://cdn.example.com/custom.png"
    assert first.auto_cover_url == "https://cdn.example.com/scene1.png"
    assert first.planned_episode_count == 5
    assert first.asset_image_ready_count == 8
    assert first.storyboard_episode_count == 4
    assert first.clip_count == 20
    assert first.clip_video_ready_count == 16
    assert first.composed_episode_count == 3

    assert second.cover_url is None
    assert second.auto_cover_url == "https://cdn.example.com/clip-preview.png"
    assert second.planned_episode_count == 4
    assert second.storyboard_episode_count == 2
    assert second.clip_video_ready_count == 2
    assert second.composed_episode_count == 0
