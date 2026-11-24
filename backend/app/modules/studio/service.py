import re
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import case, delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.art_styles.service import resolve_art_style_prompt
from app.modules.catalog.models import AiModel
from app.modules.jobs.models import Job
from app.modules.jobs.schemas import JobOut
from app.modules.llm_engine.schema import (
    Asset,
    AssetResult,
    EpisodeDraft,
    Outline,
    ProjectSettings,
    Scene,
    ScriptResult,
    StoryboardResult,
)
from app.modules.llm_engine.schema import (
    Episode as LlmEpisode,
)
from app.modules.llm_engine.timing import episode_seconds, render_script
from app.modules.studio.models import Episode, Project, ProjectAsset, StoryboardClip
from app.modules.studio.schemas import (
    AssetCreateRequest,
    AssetUpdateRequest,
    ClipCreateRequest,
    ClipUpdateRequest,
    EpisodeOut,
    MediaHistoryItemOut,
    ProjectAssetOut,
    ProjectDetailOut,
    ProjectSummaryOut,
    StoryboardClipOut,
    UpdateProjectRequest,
)

_SCRIPT_CODE_RE = re.compile(r"^[CSP]\d+$")
MAX_STUDIO_MEDIA_HISTORY = 20
MediaHistorySource = Literal["ai", "upload", "rescue"]


def _now_iso_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _append_media_history(
    existing: list[dict[str, Any]] | None,
    entry: dict[str, Any],
) -> list[dict[str, Any]]:
    url = str(entry.get("url") or "").strip()
    if not url:
        return list(existing or [])
    job_id = entry.get("jobId")
    items = [
        item
        for item in (existing or [])
        if isinstance(item, dict)
        and item.get("url") != url
        and (not job_id or item.get("jobId") != job_id)
    ]
    items.append(entry)
    return items[-MAX_STUDIO_MEDIA_HISTORY:]


def append_asset_image_history(
    asset: ProjectAsset,
    *,
    url: str,
    key: str | None = None,
    source: MediaHistorySource = "ai",
    job_id: UUID | str | None = None,
    model_id: str | None = None,
    tier: str | None = None,
    ratio: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    job_id_str = str(job_id) if job_id is not None else None
    entry: dict[str, Any] = {
        "id": job_id_str or str(uuid4()),
        "url": url,
        "key": key,
        "source": source,
        "jobId": job_id_str,
        "modelId": model_id,
        "tier": tier,
        "resolution": None,
        "ratio": ratio,
        "duration": None,
        "createdAt": created_at or _now_iso_utc(),
    }
    asset.image_history = _append_media_history(asset.image_history, entry)
    return entry


def append_clip_video_history(
    clip: StoryboardClip,
    *,
    url: str,
    key: str | None = None,
    source: MediaHistorySource = "ai",
    job_id: UUID | str | None = None,
    model_id: str | None = None,
    resolution: str | None = None,
    ratio: str | None = None,
    duration: float | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    job_id_str = str(job_id) if job_id is not None else None
    entry: dict[str, Any] = {
        "id": job_id_str or str(uuid4()),
        "url": url,
        "key": key,
        "source": source,
        "jobId": job_id_str,
        "modelId": model_id,
        "tier": None,
        "resolution": resolution,
        "ratio": ratio,
        "duration": float(duration) if duration is not None else None,
        "createdAt": created_at or _now_iso_utc(),
    }
    clip.video_history = _append_media_history(clip.video_history, entry)
    return entry


def _parse_history_items(raw: list[dict[str, Any]] | None) -> list[MediaHistoryItemOut]:
    items: list[MediaHistoryItemOut] = []
    for entry in raw or []:
        if not isinstance(entry, dict) or not entry.get("url"):
            continue
        items.append(MediaHistoryItemOut.model_validate(entry))
    return items


async def load_jobs_by_id(session: AsyncSession, job_ids: set[UUID]) -> dict[UUID, Job]:
    if not job_ids:
        return {}
    rows = list(await session.scalars(select(Job).where(Job.id.in_(job_ids))))
    return {row.id: row for row in rows}


def serialize_asset_out(asset: ProjectAsset, last_job: Job | None = None) -> ProjectAssetOut:
    return ProjectAssetOut(
        id=asset.id,
        asset_code=asset.asset_code,
        kind=asset.kind,
        name=asset.name,
        description=asset.description,
        prompt=asset.prompt,
        voice=asset.voice,
        episode_numbers=list(asset.episode_numbers or []),
        parent_asset_id=asset.parent_asset_id,
        variant_label=asset.variant_label or "",
        image_url=asset.image_url,
        image_model_id=asset.image_model_id,
        image_tier=asset.image_tier,
        image_status=asset.image_status,
        image_history=_parse_history_items(asset.image_history),
        last_job_id=asset.last_job_id,
        last_job_status=last_job.status if last_job is not None else None,
        last_job_error=last_job.error_message if last_job is not None else None,
    )


def serialize_clip_out(clip: StoryboardClip, last_job: Job | None = None) -> StoryboardClipOut:
    return StoryboardClipOut(
        id=clip.id,
        episode_id=clip.episode_id,
        clip_index=clip.clip_index,
        duration_seconds=clip.duration_seconds,
        prompt=clip.prompt,
        prompt_customized=clip.prompt_customized,
        references=list(clip.references or []),
        beats=clip.beats,
        blocking=clip.blocking,
        cuts=clip.cuts,
        preview_url=clip.preview_url,
        video_url=clip.video_url,
        video_model_id=clip.video_model_id,
        video_status=clip.video_status,
        video_history=_parse_history_items(clip.video_history),
        last_job_id=clip.last_job_id,
        last_job_status=last_job.status if last_job is not None else None,
        last_job_error=last_job.error_message if last_job is not None else None,
    )


async def get_owned_project(session: AsyncSession, *, project_id: UUID, user_id: int) -> Project:
    project = await session.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == user_id,
            Project.status == "active",
        )
    )
    if project is None:
        raise AppError(404, "project_not_found", "短剧项目不存在")
    return project


async def list_user_projects(session: AsyncSession, *, user_id: int) -> list[ProjectSummaryOut]:
    projects = list(
        await session.scalars(
            select(Project)
            .where(Project.user_id == user_id, Project.status == "active")
            .order_by(desc(Project.updated_at), desc(Project.id))
        )
    )
    if not projects:
        return []
    project_ids = [p.id for p in projects]

    ep_stats = {
        row[0]: (int(row[1]), int(row[2] or 0))
        for row in (
            await session.execute(
                select(
                    Episode.project_id,
                    func.count(Episode.id),
                    func.sum(
                        case(
                            (
                                Episode.composed_video_url.is_not(None)
                                & (Episode.composed_video_url != ""),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                )
                .where(Episode.project_id.in_(project_ids))
                .group_by(Episode.project_id)
            )
        ).all()
    }

    asset_stats = {
        row[0]: (int(row[1]), int(row[2] or 0))
        for row in (
            await session.execute(
                select(
                    ProjectAsset.project_id,
                    func.count(ProjectAsset.id),
                    func.sum(
                        case(
                            (
                                ProjectAsset.image_url.is_not(None)
                                & (ProjectAsset.image_url != ""),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                )
                .where(ProjectAsset.project_id.in_(project_ids))
                .group_by(ProjectAsset.project_id)
            )
        ).all()
    }

    clip_stats = {
        row[0]: (int(row[1]), int(row[2]), int(row[3] or 0))
        for row in (
            await session.execute(
                select(
                    StoryboardClip.project_id,
                    func.count(func.distinct(StoryboardClip.episode_id)),
                    func.count(StoryboardClip.id),
                    func.sum(
                        case(
                            (
                                StoryboardClip.video_url.is_not(None)
                                & (StoryboardClip.video_url != ""),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                )
                .where(StoryboardClip.project_id.in_(project_ids))
                .group_by(StoryboardClip.project_id)
            )
        ).all()
    }

    auto_covers: dict[UUID, str] = {}
    asset_cover_rows = (
        await session.execute(
            select(ProjectAsset.project_id, ProjectAsset.image_url)
            .where(
                ProjectAsset.project_id.in_(project_ids),
                ProjectAsset.image_url.is_not(None),
                ProjectAsset.image_url != "",
            )
            .order_by(
                ProjectAsset.project_id,
                case((ProjectAsset.parent_asset_id.is_(None), 0), else_=1),
                case(
                    (ProjectAsset.kind == "scene", 0),
                    (ProjectAsset.kind == "character", 1),
                    else_=2,
                ),
                ProjectAsset.created_at,
                ProjectAsset.id,
            )
        )
    ).all()
    for pid, image_url in asset_cover_rows:
        if pid not in auto_covers and image_url:
            auto_covers[pid] = image_url

    missing_cover_ids = [pid for pid in project_ids if pid not in auto_covers]
    if missing_cover_ids:
        clip_cover_rows = (
            await session.execute(
                select(StoryboardClip.project_id, StoryboardClip.preview_url)
                .where(
                    StoryboardClip.project_id.in_(missing_cover_ids),
                    StoryboardClip.preview_url.is_not(None),
                    StoryboardClip.preview_url != "",
                )
                .order_by(
                    StoryboardClip.project_id,
                    StoryboardClip.created_at,
                    StoryboardClip.clip_index,
                    StoryboardClip.id,
                )
            )
        ).all()
        for pid, preview_url in clip_cover_rows:
            if pid not in auto_covers and preview_url:
                auto_covers[pid] = preview_url

    summaries: list[ProjectSummaryOut] = []
    for p in projects:
        ep_count, composed_count = ep_stats.get(p.id, (0, 0))
        asset_count, asset_ready_count = asset_stats.get(p.id, (0, 0))
        sb_ep_count, clip_count, clip_video_ready = clip_stats.get(p.id, (0, 0, 0))
        raw_planned = p.settings.get("episodeCount") if isinstance(p.settings, dict) else 0
        try:
            planned_ep = max(int(raw_planned or 0), ep_count)
        except (TypeError, ValueError):
            planned_ep = ep_count

        summaries.append(
            ProjectSummaryOut(
                id=p.id,
                name=p.name,
                mode=p.mode,
                settings=p.settings,
                cover_url=p.cover_url,
                cover_key=p.cover_key,
                auto_cover_url=auto_covers.get(p.id),
                script_confirmed=p.script_confirmed,
                episode_count=ep_count,
                planned_episode_count=planned_ep,
                asset_count=asset_count,
                asset_image_ready_count=asset_ready_count,
                storyboard_episode_count=sb_ep_count,
                clip_count=clip_count,
                clip_video_ready_count=clip_video_ready,
                composed_episode_count=composed_count,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
        )
    return summaries


async def update_project_meta(
    session: AsyncSession,
    *,
    project: Project,
    body: UpdateProjectRequest,
) -> Project:
    fields = body.model_fields_set
    next_settings: dict[str, Any] = dict(project.settings or {})

    if "name" in fields and body.name is not None:
        project.name = body.name
        next_settings["name"] = body.name

    if "ratio" in fields and body.ratio is not None:
        next_settings["ratio"] = body.ratio

    if "visual_style" in fields and body.visual_style is not None:
        next_settings["visualStyle"] = body.visual_style
        if "visual_style_label" not in fields:
            resolved_prompt = await resolve_art_style_prompt(session, body.visual_style)
            if resolved_prompt:
                next_settings["visualStyleLabel"] = resolved_prompt

    if "visual_style_label" in fields:
        if body.visual_style_label:
            next_settings["visualStyleLabel"] = body.visual_style_label
        else:
            next_settings.pop("visualStyleLabel", None)

    if "max_segment_duration" in fields and body.max_segment_duration is not None:
        next_settings["maxSegmentDuration"] = body.max_segment_duration

    if "background_music" in fields and body.background_music is not None:
        next_settings["backgroundMusic"] = body.background_music

    if "image_model_id" in fields:
        if body.image_model_id:
            image_model = await session.scalar(
                select(AiModel).where(
                    AiModel.id == body.image_model_id,
                    AiModel.media_type == "image",
                    AiModel.enabled.is_(True),
                )
            )
            if image_model is None:
                raise AppError(400, "image_model_invalid", "所选默认图片模型不存在或未启用")
            next_settings["imageModelId"] = image_model.id
        else:
            next_settings.pop("imageModelId", None)

    if "image_tier" in fields:
        if body.image_tier:
            next_settings["imageTier"] = body.image_tier
        else:
            next_settings.pop("imageTier", None)

    effective_cap = int(next_settings.get("maxSegmentDuration") or 15)
    video_model_row: AiModel | None = None
    if "video_model_id" in fields:
        if body.video_model_id:
            video_model_row = await session.scalar(
                select(AiModel).where(
                    AiModel.id == body.video_model_id,
                    AiModel.media_type == "video",
                    AiModel.enabled.is_(True),
                )
            )
            if video_model_row is None:
                raise AppError(400, "video_model_invalid", "所选默认视频模型不存在或未启用")
            next_settings["videoModelId"] = video_model_row.id
        else:
            next_settings.pop("videoModelId", None)
    elif "max_segment_duration" in fields and next_settings.get("videoModelId"):
        existing_vid_id = str(next_settings["videoModelId"])
        video_model_row = await session.scalar(
            select(AiModel).where(AiModel.id == existing_vid_id, AiModel.media_type == "video")
        )

    if effective_cap >= 30 and video_model_row is not None:
        raw_max = (video_model_row.capabilities or {}).get("maxDuration")
        try:
            max_dur = int(raw_max) if raw_max is not None else 15
        except (TypeError, ValueError):
            max_dur = 15
        if max_dur < 30:
            if "video_model_id" in fields:
                raise AppError(
                    400,
                    "video_model_duration_incompatible",
                    (
                        f"模型「{video_model_row.display_name}」最长支持 {max_dur} 秒，"
                        "无法作为 30 秒单段上限的默认视频模型"
                    ),
                )
            # 仅切换单段上限至 30 秒且未显式指定视频模型时，清空不兼容旧默认，交由系统 30s 默认模型接管。
            next_settings.pop("videoModelId", None)

    if "cover_url" in fields:
        project.cover_url = body.cover_url
        if body.cover_url is None and "cover_key" not in fields:
            project.cover_key = None

    if "cover_key" in fields:
        project.cover_key = body.cover_key

    project.settings = next_settings
    await session.flush()
    return project


async def get_project_detail(session: AsyncSession, *, project_id: UUID, user_id: int) -> ProjectDetailOut:
    project = await get_owned_project(session, project_id=project_id, user_id=user_id)
    episodes = list(
        await session.scalars(
            select(Episode).where(Episode.project_id == project.id).order_by(Episode.number)
        )
    )
    assets = list(
        await session.scalars(
            select(ProjectAsset)
            .where(ProjectAsset.project_id == project.id)
            .order_by(ProjectAsset.created_at, ProjectAsset.asset_code)
        )
    )
    clips = list(
        await session.scalars(
            select(StoryboardClip)
            .where(StoryboardClip.project_id == project.id)
            .order_by(StoryboardClip.clip_index)
        )
    )
    active_jobs = list(
        await session.scalars(
            select(Job)
            .where(Job.project_id == project.id, Job.status.in_(("queued", "running", "polling")))
            .order_by(desc(Job.created_at))
        )
    )

    last_job_ids: set[UUID] = set()
    for asset in assets:
        if asset.last_job_id is not None:
            last_job_ids.add(asset.last_job_id)
    for clip in clips:
        if clip.last_job_id is not None:
            last_job_ids.add(clip.last_job_id)
    jobs_by_id = await load_jobs_by_id(session, last_job_ids)

    ep_num_by_id = {ep.id: ep.number for ep in episodes}
    storyboards: dict[int, list[StoryboardClipOut]] = {}
    for clip in clips:
        ep_num = ep_num_by_id.get(clip.episode_id)
        if ep_num is not None:
            last_job = jobs_by_id.get(clip.last_job_id) if clip.last_job_id else None
            storyboards.setdefault(ep_num, []).append(serialize_clip_out(clip, last_job))

    return ProjectDetailOut(
        id=project.id,
        name=project.name,
        mode=project.mode,
        source_text=project.source_text,
        settings=project.settings,
        cover_url=project.cover_url,
        cover_key=project.cover_key,
        outline=project.outline,
        script_confirmed=project.script_confirmed,
        episodes=[EpisodeOut.model_validate(ep) for ep in episodes],
        assets=[
            serialize_asset_out(a, jobs_by_id.get(a.last_job_id) if a.last_job_id else None)
            for a in assets
        ],
        storyboards=storyboards,
        active_jobs=[JobOut.model_validate(j) for j in active_jobs],
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


async def build_script_result_from_db(session: AsyncSession, project: Project) -> ScriptResult:
    if not project.outline:
        raise AppError(400, "script_not_generated", "该项目尚未生成结构化剧本")
    episodes = list(
        await session.scalars(
            select(Episode).where(Episode.project_id == project.id).order_by(Episode.number)
        )
    )
    return ScriptResult(
        settings=ProjectSettings.model_validate(project.settings),
        outline=Outline.model_validate(project.outline),
        episodes=[
            LlmEpisode(
                number=ep.number,
                title=ep.title,
                summary=ep.summary,
                hook=ep.hook or "开场钩子",
                cliff=ep.cliff or "结尾悬念",
                hookBeat=(ep.hook_beat[0], ep.hook_beat[1]) if len(ep.hook_beat) == 2 else (1, 1),
                scenes=[Scene.model_validate(scene) for scene in ep.scenes],
                targetSeconds=ep.target_seconds,
                seconds=ep.seconds,
                script=ep.script,
                warnings=list(ep.warnings or []),
            )
            for ep in episodes
        ],
    )


async def build_asset_result_from_db(
    session: AsyncSession,
    project: Project,
    *,
    include_variants: bool = False,
) -> AssetResult:
    stmt = (
        select(ProjectAsset)
        .where(ProjectAsset.project_id == project.id)
        .order_by(ProjectAsset.created_at, ProjectAsset.asset_code)
    )
    if not include_variants:
        stmt = stmt.where(ProjectAsset.parent_asset_id.is_(None))
    rows = list(await session.scalars(stmt))
    code_by_uuid = {row.id: row.asset_code for row in rows}
    roots = [row for row in rows if row.parent_asset_id is None]
    variants = [
        row
        for row in rows
        if row.parent_asset_id is not None and row.parent_asset_id in code_by_uuid
    ]
    ordered_rows = [*roots, *variants] if include_variants else roots
    return AssetResult(
        settings=ProjectSettings.model_validate(project.settings),
        assets=[
            Asset(
                id=a.asset_code,
                kind=a.kind,  # type: ignore[arg-type]
                name=a.name,
                description=a.description or a.name,
                prompt=a.prompt or a.name,
                episodeNumbers=[n for n in (a.episode_numbers or []) if isinstance(n, int) and n >= 1],
                voice=a.voice or "",
                parentId=code_by_uuid.get(a.parent_asset_id) if a.parent_asset_id else None,
                variantLabel=(a.variant_label or "") if a.parent_asset_id else "",
            )
            for a in ordered_rows
        ],
    )


async def persist_project_outline(
    session: AsyncSession,
    project: Project,
    settings: ProjectSettings,
    outline: Outline,
    *,
    reset_downstream: bool = False,
) -> None:
    """大纲规划完成后立即落库；若为全剧重生成则清空下游资产/分镜，并清理旧分集准备逐集写入。"""
    project.name = settings.name
    project.settings = settings.model_dump()
    project.outline = outline.model_dump()
    project.script_confirmed = False

    if reset_downstream:
        await session.execute(delete(StoryboardClip).where(StoryboardClip.project_id == project.id))
        await session.execute(delete(ProjectAsset).where(ProjectAsset.project_id == project.id))
    await session.execute(delete(Episode).where(Episode.project_id == project.id))
    await session.flush()


async def persist_single_episode(
    session: AsyncSession,
    project: Project,
    ep_data: LlmEpisode,
) -> Episode:
    """逐集增量落库：每写完一集立即持久化，避免长剧后半程异常导致已完成分集白跑。"""
    ep = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == ep_data.number)
    )
    if ep is None:
        ep = Episode(project_id=project.id, number=ep_data.number, title=ep_data.title)
        session.add(ep)
    ep.title = ep_data.title
    ep.summary = ep_data.summary
    ep.target_seconds = ep_data.targetSeconds
    ep.seconds = ep_data.seconds
    ep.hook = ep_data.hook
    ep.cliff = ep_data.cliff
    ep.hook_beat = list(ep_data.hookBeat)
    ep.scenes = [scene.model_dump() for scene in ep_data.scenes]
    ep.script = ep_data.script
    ep.warnings = list(ep_data.warnings)
    project.script_confirmed = False
    await session.flush()
    return ep


async def persist_script_result(
    session: AsyncSession,
    project: Project,
    result: ScriptResult,
    *,
    reset_downstream: bool = False,
) -> None:
    project.name = result.settings.name
    project.settings = result.settings.model_dump()
    project.outline = result.outline.model_dump()
    project.script_confirmed = False

    if reset_downstream:
        await session.execute(delete(StoryboardClip).where(StoryboardClip.project_id == project.id))
        await session.execute(delete(ProjectAsset).where(ProjectAsset.project_id == project.id))
    await session.execute(delete(Episode).where(Episode.project_id == project.id))
    await session.flush()

    for ep in result.episodes:
        session.add(
            Episode(
                project_id=project.id,
                number=ep.number,
                title=ep.title,
                summary=ep.summary,
                target_seconds=ep.targetSeconds,
                seconds=ep.seconds,
                hook=ep.hook,
                cliff=ep.cliff,
                hook_beat=list(ep.hookBeat),
                scenes=[scene.model_dump() for scene in ep.scenes],
                script=ep.script,
                warnings=list(ep.warnings),
            )
        )
    await session.flush()


async def persist_rewritten_episode(
    session: AsyncSession,
    project: Project,
    rewritten: LlmEpisode,
) -> Episode:
    ep = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == rewritten.number)
    )
    if ep is None:
        ep = Episode(project_id=project.id, number=rewritten.number, title=rewritten.title)
        session.add(ep)
    ep.title = rewritten.title
    ep.summary = rewritten.summary
    ep.target_seconds = rewritten.targetSeconds
    ep.seconds = rewritten.seconds
    ep.hook = rewritten.hook
    ep.cliff = rewritten.cliff
    ep.hook_beat = list(rewritten.hookBeat)
    ep.scenes = [scene.model_dump() for scene in rewritten.scenes]
    ep.script = rewritten.script
    ep.warnings = list(rewritten.warnings)
    ep.composed_video_key = None
    ep.composed_video_url = None
    ep.composed_duration = None
    project.script_confirmed = False
    await session.flush()
    await session.execute(delete(StoryboardClip).where(StoryboardClip.episode_id == ep.id))
    await session.flush()
    return ep


async def persist_appended_episode(
    session: AsyncSession,
    project: Project,
    updated: ScriptResult,
) -> Episode:
    project.settings = updated.settings.model_dump()
    project.outline = updated.outline.model_dump()
    project.script_confirmed = False
    latest = max(updated.episodes, key=lambda item: item.number)
    ep = Episode(
        project_id=project.id,
        number=latest.number,
        title=latest.title,
        summary=latest.summary,
        target_seconds=latest.targetSeconds,
        seconds=latest.seconds,
        hook=latest.hook,
        cliff=latest.cliff,
        hook_beat=list(latest.hookBeat),
        scenes=[scene.model_dump() for scene in latest.scenes],
        script=latest.script,
        warnings=list(latest.warnings),
    )
    session.add(ep)
    await session.flush()
    return ep


async def _promote_children_and_delete_asset(
    session: AsyncSession, *, project_id: UUID, asset: ProjectAsset
) -> None:
    children = list(
        await session.scalars(
            select(ProjectAsset)
            .where(
                ProjectAsset.project_id == project_id,
                ProjectAsset.parent_asset_id == asset.id,
            )
            .order_by(ProjectAsset.created_at, ProjectAsset.id)
        )
    )
    if children:
        # 删除主资产时自动将最早创建的变体提升为新主资产并重挂兄弟变体，避免产生孤儿变体或丢失已生成图片。
        new_root = children[0]
        new_root.parent_asset_id = None
        for sibling in children[1:]:
            sibling.parent_asset_id = new_root.id
        await session.flush()
    await session.delete(asset)
    await session.flush()


async def persist_extracted_assets(
    session: AsyncSession,
    project: Project,
    result: AssetResult,
    *,
    preserve_edits: bool = False,
    prune_missing: bool = True,
) -> list[ProjectAsset]:
    existing_rows = list(
        await session.scalars(select(ProjectAsset).where(ProjectAsset.project_id == project.id))
    )
    by_code = {row.asset_code: row for row in existing_rows}
    root_items = [item for item in result.assets if not item.parentId]
    variant_items = [item for item in result.assets if item.parentId]
    result_root_codes = {item.id for item in root_items}

    # 删除已不在剧本中出现的旧脚本主资产（保留用户自定义资产与所有变体，并通过共享提拔逻辑防止孤儿变体）。
    if prune_missing:
        for row in existing_rows:
            if (
                row.parent_asset_id is None
                and row.asset_code not in result_root_codes
                and _SCRIPT_CODE_RE.match(row.asset_code)
            ):
                await _promote_children_and_delete_asset(session, project_id=project.id, asset=row)

    saved: list[ProjectAsset] = []
    root_by_code: dict[str, ProjectAsset] = {}
    for item in root_items:
        row = by_code.get(item.id)
        if row is None:
            row = ProjectAsset(
                project_id=project.id,
                asset_code=item.id,
                kind=item.kind,
                name=item.name,
                description=item.description,
                prompt=item.prompt,
                voice=item.voice if item.kind == "character" else "",
                episode_numbers=list(item.episodeNumbers),
            )
            session.add(row)
        else:
            row.episode_numbers = list(item.episodeNumbers)
            if not preserve_edits:
                row.kind = item.kind
                row.name = item.name
                row.description = item.description
                row.prompt = item.prompt
                row.voice = item.voice if item.kind == "character" else ""
            # 无论全量还是增量，始终保留已上传/已生成的 image_key / image_url。
        root_by_code[item.id] = row
        saved.append(row)

    # 先 flush 确保新建根资产拿到 UUID，供变体绑定 parent_asset_id。
    await session.flush()

    existing_by_parent_label: dict[tuple[UUID, str], ProjectAsset] = {
        (row.parent_asset_id, (row.variant_label or "").strip().lower()): row
        for row in existing_rows
        if row.parent_asset_id is not None and (row.variant_label or "").strip()
    }
    for item in variant_items:
        parent_row = root_by_code.get(item.parentId or "") or by_code.get(item.parentId or "")
        if parent_row is None or parent_row.id is None:
            continue
        clean_label = (item.variantLabel or "").strip()[:60]
        if not clean_label:
            continue
        row = by_code.get(item.id) or existing_by_parent_label.get(
            (parent_row.id, clean_label.lower())
        )
        if row is None:
            row = ProjectAsset(
                project_id=project.id,
                asset_code=item.id,
                kind=item.kind,
                name=item.name,
                description=item.description,
                prompt=item.prompt,
                voice="",
                episode_numbers=list(item.episodeNumbers),
                parent_asset_id=parent_row.id,
                variant_label=clean_label,
            )
            session.add(row)
            by_code[row.asset_code] = row
            existing_by_parent_label[(parent_row.id, clean_label.lower())] = row
        else:
            row.parent_asset_id = parent_row.id
            row.episode_numbers = list(item.episodeNumbers)
            if not preserve_edits:
                row.kind = item.kind
                row.name = item.name
                row.description = item.description
                row.prompt = item.prompt
                row.variant_label = clean_label
            # 始终保留变体已上传/已生成的 image_key / image_url。
        saved.append(row)

    await session.flush()
    return saved


def _build_storyboard_clip_row(
    *,
    project_id: UUID,
    episode_id: UUID,
    clip: Any,
    assets_by_code: dict[str, ProjectAsset],
) -> StoryboardClip:
    refs = []
    for ref in clip.references:
        matched = assets_by_code.get(ref.assetId)
        matched_name = (
            f"{matched.name} · {matched.variant_label}"
            if matched and matched.variant_label
            else (matched.name if matched else ref.name)
        )
        refs.append(
            {
                "index": ref.index,
                "assetId": str(matched.id) if matched else ref.assetId,
                "assetCode": ref.assetId,
                "name": matched_name,
                "kind": ref.kind,
            }
        )
    return StoryboardClip(
        project_id=project_id,
        episode_id=episode_id,
        clip_index=clip.id,
        duration_seconds=max(1, round(clip.durationSeconds)),
        prompt=clip.prompt,
        prompt_customized=False,
        references=refs,
        beats=list(clip.beats) if clip.beats else None,
        blocking=clip.blocking or None,
        cuts=[cut.model_dump() for cut in clip.cuts] if clip.cuts else None,
    )


async def persist_storyboard_batch(
    session: AsyncSession,
    project: Project,
    *,
    episode_number: int,
    clips: list[Any],
    replace_existing: bool = False,
) -> int:
    ep = await session.scalar(
        select(Episode).where(
            Episode.project_id == project.id,
            Episode.number == episode_number,
        )
    )
    if ep is None:
        return 0
    assets_by_code = {
        a.asset_code: a
        for a in await session.scalars(
            select(ProjectAsset).where(ProjectAsset.project_id == project.id)
        )
    }
    clip_indices = [clip.id for clip in clips]
    if replace_existing:
        await session.execute(delete(StoryboardClip).where(StoryboardClip.episode_id == ep.id))
        await session.flush()
    elif clip_indices:
        await session.execute(
            delete(StoryboardClip).where(
                StoryboardClip.episode_id == ep.id,
                StoryboardClip.clip_index.in_(clip_indices),
            )
        )
        await session.flush()
    for clip in clips:
        session.add(
            _build_storyboard_clip_row(
                project_id=project.id,
                episode_id=ep.id,
                clip=clip,
                assets_by_code=assets_by_code,
            )
        )
    await session.flush()
    return len(clips)


async def persist_storyboard_result(
    session: AsyncSession,
    project: Project,
    result: StoryboardResult,
) -> None:
    episodes = {
        ep.number: ep for ep in await session.scalars(select(Episode).where(Episode.project_id == project.id))
    }
    assets_by_code = {
        a.asset_code: a
        for a in await session.scalars(select(ProjectAsset).where(ProjectAsset.project_id == project.id))
    }
    for board in result.episodes:
        ep = episodes.get(board.number)
        if ep is None:
            continue
        await session.execute(delete(StoryboardClip).where(StoryboardClip.episode_id == ep.id))
        await session.flush()
        for clip in board.clips:
            session.add(
                _build_storyboard_clip_row(
                    project_id=project.id,
                    episode_id=ep.id,
                    clip=clip,
                    assets_by_code=assets_by_code,
                )
            )
    await session.flush()


async def save_structured_episode(
    session: AsyncSession,
    *,
    project: Project,
    episode_number: int,
    title: str,
    raw_scenes: list[dict],
) -> Episode:
    ep = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == episode_number)
    )
    if ep is None:
        raise AppError(404, "episode_not_found", f"第 {episode_number} 集不存在")
    if not project.outline:
        raise AppError(400, "outline_missing", "缺少大纲信息，无法保存结构化剧本")

    cleaned_scenes: list[Scene] = []
    for raw in raw_scenes:
        characters = list(raw.get("characters") or [])
        flow = []
        for beat in raw.get("flow") or []:
            if beat.get("action") is not None:
                text_val = str(beat["action"]).strip()
                if text_val:
                    flow.append({"action": text_val})
            else:
                line_val = str(beat.get("line") or "").strip()
                if not line_val:
                    continue
                speaker = str(beat.get("speaker") or "").strip() or "VO"
                delivery = str(beat.get("delivery") or "").strip()
                if speaker != "VO" and speaker not in characters:
                    characters.append(speaker)
                item = {"speaker": speaker, "line": line_val}
                if delivery:
                    item["delivery"] = delivery
                flow.append(item)
        if not flow or not any("action" in b for b in flow):
            raise AppError(400, "invalid_scene_flow", "每场至少需要保留一条动作节拍")
        cleaned_scenes.append(
            Scene.model_validate(
                {
                    "sceneId": raw["sceneId"],
                    "lighting": str(raw.get("lighting") or "").strip(),
                    "characters": characters,
                    "props": list(raw.get("props") or []),
                    "flow": flow,
                }
            )
        )

    outline = Outline.model_validate(project.outline)
    safe_scene = max(1, min(ep.hook_beat[0] if ep.hook_beat else 1, len(cleaned_scenes)))
    safe_beat = max(
        1,
        min(
            ep.hook_beat[1] if len(ep.hook_beat) > 1 else 1,
            len(cleaned_scenes[safe_scene - 1].flow),
        ),
    )
    draft = EpisodeDraft(
        number=ep.number,
        title=title.strip(),
        summary=ep.summary or title.strip(),
        hook=ep.hook or "开场钩子",
        cliff=ep.cliff or "结尾悬念",
        hookBeat=(safe_scene, safe_beat),
        scenes=cleaned_scenes,
    )
    ep.title = draft.title
    ep.scenes = [s.model_dump() for s in cleaned_scenes]
    ep.seconds = episode_seconds(draft)
    ep.script = render_script(draft, outline)
    ep.hook_beat = [safe_scene, safe_beat]
    project.script_confirmed = False
    await session.flush()
    return ep


async def create_project_asset(
    session: AsyncSession, *, project: Project, body: AssetCreateRequest
) -> ProjectAsset:
    variant_label = body.variant_label.strip()
    parent_asset_id = body.parent_asset_id
    if parent_asset_id is not None:
        parent = await session.scalar(
            select(ProjectAsset).where(
                ProjectAsset.id == parent_asset_id, ProjectAsset.project_id == project.id
            )
        )
        if parent is None:
            raise AppError(404, "parent_asset_not_found", "归属主资产不存在")
        if parent.parent_asset_id is not None:
            raise AppError(400, "nested_variant_not_allowed", "变体只能归属到主资产，不支持多级嵌套")
        if parent.kind != body.kind:
            raise AppError(400, "variant_kind_mismatch", "变体类型必须与主资产一致")
        if not variant_label:
            raise AppError(400, "variant_label_required", "请为变体填写状态标签（如 晚宴礼服、深夜、碎裂）")

    asset = ProjectAsset(
        project_id=project.id,
        parent_asset_id=parent_asset_id,
        variant_label=variant_label,
        asset_code=uuid4().hex[:12],
        kind=body.kind,
        name=body.name.strip(),
        description=body.description.strip(),
        prompt=body.prompt.strip(),
        voice=body.voice.strip() if body.kind == "character" else "",
        image_url=body.image_url,
        image_key=body.image_key,
        image_status="ready" if body.image_url else "none",
    )
    if body.image_url:
        append_asset_image_history(
            asset,
            url=body.image_url,
            key=body.image_key,
            source="upload",
        )
    session.add(asset)
    await session.flush()
    return asset


async def update_project_asset(
    session: AsyncSession, *, project: Project, asset_id: UUID, body: AssetUpdateRequest
) -> ProjectAsset:
    asset = await session.scalar(
        select(ProjectAsset).where(ProjectAsset.id == asset_id, ProjectAsset.project_id == project.id)
    )
    if asset is None:
        raise AppError(404, "asset_not_found", "资产不存在")
    if body.name is not None:
        asset.name = body.name.strip()
    if body.description is not None:
        asset.description = body.description.strip()
    if body.prompt is not None:
        asset.prompt = body.prompt.strip()
    if body.voice is not None:
        asset.voice = body.voice.strip() if asset.kind == "character" else ""
    if body.variant_label is not None:
        cleaned_label = body.variant_label.strip()
        if asset.parent_asset_id is not None and not cleaned_label:
            raise AppError(400, "variant_label_required", "变体的状态标签不能为空")
        asset.variant_label = cleaned_label
    if body.clear_image:
        asset.image_url = None
        asset.image_key = None
        asset.image_status = "none"
    elif body.image_url is not None:
        asset.image_url = body.image_url
        asset.image_key = body.image_key
        asset.image_status = "ready"
        append_asset_image_history(
            asset,
            url=body.image_url,
            key=body.image_key,
            source="upload",
        )
    await session.flush()
    return asset


async def select_asset_image_history(
    session: AsyncSession, *, project: Project, asset_id: UUID, history_id: str
) -> ProjectAsset:
    asset = await session.scalar(
        select(ProjectAsset).where(ProjectAsset.id == asset_id, ProjectAsset.project_id == project.id)
    )
    if asset is None:
        raise AppError(404, "asset_not_found", "资产不存在")
    if asset.image_status == "generating":
        raise AppError(409, "asset_image_in_progress", "资产正在生图中，请稍后再切换历史版本")
    history = list(asset.image_history or [])
    entry = next((item for item in history if isinstance(item, dict) and item.get("id") == history_id), None)
    if entry is None or not entry.get("url"):
        raise AppError(404, "history_item_not_found", "历史图片版本不存在")
    asset.image_url = str(entry["url"])
    asset.image_key = str(entry["key"]) if entry.get("key") else None
    asset.image_model_id = str(entry["modelId"]) if entry.get("modelId") else None
    asset.image_tier = str(entry["tier"]) if entry.get("tier") else None
    asset.image_status = "ready"
    await session.flush()
    return asset


async def delete_asset_image_history(
    session: AsyncSession, *, project: Project, asset_id: UUID, history_id: str
) -> ProjectAsset:
    asset = await session.scalar(
        select(ProjectAsset).where(ProjectAsset.id == asset_id, ProjectAsset.project_id == project.id)
    )
    if asset is None:
        raise AppError(404, "asset_not_found", "资产不存在")
    history = [item for item in (asset.image_history or []) if isinstance(item, dict)]
    entry = next((item for item in history if item.get("id") == history_id), None)
    if entry is None:
        raise AppError(404, "history_item_not_found", "历史图片版本不存在")
    if asset.image_url and entry.get("url") == asset.image_url:
        raise AppError(400, "cannot_delete_active_history", "当前正在使用的版本不可删除，请先切换其他版本")
    asset.image_history = [item for item in history if item.get("id") != history_id]
    await session.flush()
    return asset


async def delete_project_asset(session: AsyncSession, *, project: Project, asset_id: UUID) -> None:
    asset = await session.scalar(
        select(ProjectAsset).where(ProjectAsset.id == asset_id, ProjectAsset.project_id == project.id)
    )
    if asset is None:
        raise AppError(404, "asset_not_found", "资产不存在")
    await _promote_children_and_delete_asset(session, project_id=project.id, asset=asset)


async def _insert_clip_at_position(
    session: AsyncSession,
    *,
    project: Project,
    episode: Episode,
    insert_after_clip_id: UUID | None,
    duration_seconds: int,
    prompt: str,
    prompt_customized: bool,
    references: list[dict[str, Any]],
    blocking: str | None = None,
    cuts: list[dict[str, Any]] | None = None,
) -> StoryboardClip:
    existing = list(
        await session.scalars(
            select(StoryboardClip)
            .where(StoryboardClip.episode_id == episode.id)
            .order_by(StoryboardClip.clip_index)
        )
    )
    insert_pos = len(existing)
    if insert_after_clip_id is not None:
        anchor_idx = next(
            (idx for idx, row in enumerate(existing) if row.id == insert_after_clip_id),
            None,
        )
        if anchor_idx is not None:
            insert_pos = anchor_idx + 1

    # 先创建在末尾，若需插队则复用正偏移两阶段重排避免 (episode_id, clip_index) 唯一约束碰撞。
    highest = max((row.clip_index for row in existing), default=0)
    clip = StoryboardClip(
        project_id=project.id,
        episode_id=episode.id,
        clip_index=highest + 1,
        duration_seconds=duration_seconds,
        prompt=prompt,
        prompt_customized=prompt_customized,
        references=references,
        blocking=blocking,
        cuts=cuts,
    )
    session.add(clip)
    await session.flush()

    if insert_pos < len(existing):
        ordered = [*existing[:insert_pos], clip, *existing[insert_pos:]]
        offset = highest + 1000
        for idx, row in enumerate(ordered, 1):
            row.clip_index = offset + idx
        await session.flush()
        for idx, row in enumerate(ordered, 1):
            row.clip_index = idx
        await session.flush()
    return clip


async def create_clip(
    session: AsyncSession, *, project: Project, episode_number: int, body: ClipCreateRequest
) -> StoryboardClip:
    ep = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == episode_number)
    )
    if ep is None:
        raise AppError(404, "episode_not_found", f"第 {episode_number} 集不存在")
    return await _insert_clip_at_position(
        session,
        project=project,
        episode=ep,
        insert_after_clip_id=body.insert_after_clip_id,
        duration_seconds=body.duration_seconds,
        prompt=body.prompt,
        prompt_customized=bool(body.prompt.strip()),
        references=body.references,
    )


async def apply_regenerated_clip(
    session: AsyncSession,
    *,
    project: Project,
    clip_id: UUID,
    prompt_text: str,
    blocking: str,
    cuts: list[dict[str, Any]] | None,
    raw_references: list[dict[str, Any]] | None,
    refresh_references: bool,
) -> StoryboardClip:
    clip = await session.scalar(
        select(StoryboardClip).where(
            StoryboardClip.id == clip_id, StoryboardClip.project_id == project.id
        )
    )
    if clip is None:
        raise AppError(404, "clip_not_found", "片段不存在")
    clip.prompt = prompt_text
    clip.prompt_customized = False
    clip.blocking = blocking or None
    clip.cuts = cuts
    if refresh_references and raw_references is not None:
        assets_by_code = {
            a.asset_code: a
            for a in await session.scalars(
                select(ProjectAsset).where(ProjectAsset.project_id == project.id)
            )
        }
        refs: list[dict[str, Any]] = []
        for ref in raw_references:
            code = str(ref.get("assetId") or "").strip()
            matched = assets_by_code.get(code)
            matched_name = (
                f"{matched.name} · {matched.variant_label}"
                if matched and matched.variant_label
                else (matched.name if matched else str(ref.get("name") or code))
            )
            refs.append(
                {
                    "index": int(ref.get("index") or len(refs) + 1),
                    "assetId": str(matched.id) if matched else code,
                    "assetCode": code,
                    "name": matched_name,
                    "kind": str(ref.get("kind") or "character"),
                }
            )
        clip.references = refs
    # 始终保留已生成的视频与历史记录，绝不清空 video_url / video_history。
    await session.flush()
    return clip


async def persist_generated_new_clip(
    session: AsyncSession,
    *,
    project: Project,
    episode_number: int,
    duration_seconds: int,
    prompt_text: str,
    blocking: str,
    cuts: list[dict[str, Any]] | None,
    raw_references: list[dict[str, Any]],
    insert_after_clip_id: UUID | None = None,
) -> StoryboardClip:
    ep = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == episode_number)
    )
    if ep is None:
        raise AppError(404, "episode_not_found", f"第 {episode_number} 集不存在")
    assets_by_code = {
        a.asset_code: a
        for a in await session.scalars(
            select(ProjectAsset).where(ProjectAsset.project_id == project.id)
        )
    }
    refs: list[dict[str, Any]] = []
    for ref in raw_references:
        code = str(ref.get("assetId") or "").strip()
        matched = assets_by_code.get(code)
        matched_name = (
            f"{matched.name} · {matched.variant_label}"
            if matched and matched.variant_label
            else (matched.name if matched else str(ref.get("name") or code))
        )
        refs.append(
            {
                "index": int(ref.get("index") or len(refs) + 1),
                "assetId": str(matched.id) if matched else code,
                "assetCode": code,
                "name": matched_name,
                "kind": str(ref.get("kind") or "character"),
            }
        )
    return await _insert_clip_at_position(
        session,
        project=project,
        episode=ep,
        insert_after_clip_id=insert_after_clip_id,
        duration_seconds=duration_seconds,
        prompt=prompt_text,
        prompt_customized=False,
        references=refs,
        blocking=blocking or None,
        cuts=cuts,
    )


async def update_clip(
    session: AsyncSession, *, project: Project, clip_id: UUID, body: ClipUpdateRequest
) -> StoryboardClip:
    clip = await session.scalar(
        select(StoryboardClip).where(StoryboardClip.id == clip_id, StoryboardClip.project_id == project.id)
    )
    if clip is None:
        raise AppError(404, "clip_not_found", "片段不存在")
    if body.duration_seconds is not None:
        if clip.video_status == "generating":
            raise AppError(409, "clip_video_in_progress", "该片段正在生成视频中，暂不可修改时长")
        clip.duration_seconds = body.duration_seconds
    if body.prompt is not None and body.prompt != clip.prompt:
        clip.prompt = body.prompt
        clip.prompt_customized = True
    if body.references is not None:
        clip.references = body.references
    await session.flush()
    return clip


async def reorder_episode_clips(
    session: AsyncSession,
    *,
    project: Project,
    episode_number: int,
    clip_ids: list[UUID],
) -> list[StoryboardClip]:
    ep = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == episode_number)
    )
    if ep is None:
        raise AppError(404, "episode_not_found", f"第 {episode_number} 集不存在")
    clips = list(
        await session.scalars(
            select(StoryboardClip)
            .where(StoryboardClip.episode_id == ep.id)
            .order_by(StoryboardClip.clip_index)
        )
    )
    by_id = {c.id: c for c in clips}
    if len(clip_ids) != len(clips) or set(clip_ids) != set(by_id.keys()):
        raise AppError(400, "invalid_clip_order", "片段排序列表必须包含本集全部且不重复的片段")

    # 两阶段正偏移重排：满足 clip_index >= 1 约束同时避免唯一索引碰撞。
    offset = max((c.clip_index for c in clips), default=0) + 1000
    for idx, cid in enumerate(clip_ids, 1):
        by_id[cid].clip_index = offset + idx
    await session.flush()

    ordered: list[StoryboardClip] = []
    for idx, cid in enumerate(clip_ids, 1):
        row = by_id[cid]
        row.clip_index = idx
        ordered.append(row)
    await session.flush()
    return ordered


async def delete_clip(session: AsyncSession, *, project: Project, clip_id: UUID) -> None:
    clip = await session.scalar(
        select(StoryboardClip).where(StoryboardClip.id == clip_id, StoryboardClip.project_id == project.id)
    )
    if clip is None:
        raise AppError(404, "clip_not_found", "片段不存在")
    await session.delete(clip)
    await session.flush()


async def select_clip_video_history(
    session: AsyncSession,
    *,
    project: Project,
    episode_number: int,
    clip_id: UUID,
    history_id: str,
) -> StoryboardClip:
    ep = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == episode_number)
    )
    if ep is None:
        raise AppError(404, "episode_not_found", f"第 {episode_number} 集不存在")
    clip = await session.scalar(
        select(StoryboardClip).where(
            StoryboardClip.id == clip_id,
            StoryboardClip.project_id == project.id,
            StoryboardClip.episode_id == ep.id,
        )
    )
    if clip is None:
        raise AppError(404, "clip_not_found", "片段不存在")
    if clip.video_status == "generating":
        raise AppError(409, "clip_video_in_progress", "片段正在生成视频中，请稍后再切换历史版本")
    history = list(clip.video_history or [])
    entry = next((item for item in history if isinstance(item, dict) and item.get("id") == history_id), None)
    if entry is None or not entry.get("url"):
        raise AppError(404, "history_item_not_found", "历史视频版本不存在")
    clip.video_url = str(entry["url"])
    clip.video_key = str(entry["key"]) if entry.get("key") else None
    clip.video_model_id = str(entry["modelId"]) if entry.get("modelId") else None
    clip.video_status = "ready"
    await session.flush()
    return clip


async def delete_clip_video_history(
    session: AsyncSession,
    *,
    project: Project,
    episode_number: int,
    clip_id: UUID,
    history_id: str,
) -> StoryboardClip:
    ep = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == episode_number)
    )
    if ep is None:
        raise AppError(404, "episode_not_found", f"第 {episode_number} 集不存在")
    clip = await session.scalar(
        select(StoryboardClip).where(
            StoryboardClip.id == clip_id,
            StoryboardClip.project_id == project.id,
            StoryboardClip.episode_id == ep.id,
        )
    )
    if clip is None:
        raise AppError(404, "clip_not_found", "片段不存在")
    history = [item for item in (clip.video_history or []) if isinstance(item, dict)]
    entry = next((item for item in history if item.get("id") == history_id), None)
    if entry is None:
        raise AppError(404, "history_item_not_found", "历史视频版本不存在")
    if clip.video_url and entry.get("url") == clip.video_url:
        raise AppError(400, "cannot_delete_active_history", "当前正在使用的版本不可删除，请先切换其他版本")
    clip.video_history = [item for item in history if item.get("id") != history_id]
    await session.flush()
    return clip
