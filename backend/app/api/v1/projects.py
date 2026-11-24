from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header
from pydantic_ai import RunUsage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.core.errors import AppError
from app.core.schemas import ApiResponse
from app.db.session import get_session
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.canvas.generation import find_removed_prompt_refs
from app.modules.catalog.models import AiModel, AiProvider
from app.modules.catalog.service import quote_image_price, quote_video_price
from app.modules.credits.service import (
    assert_llm_balance_positive,
    charge_llm_usage,
    freeze_media_credits,
)
from app.modules.jobs.models import Job
from app.modules.jobs.schemas import JobOut
from app.modules.jobs.service import create_job
from app.modules.llm_engine.asset_gen import suggest_variant_prompt
from app.modules.llm_engine.provider import resolve_text_model
from app.modules.media_providers.cangyuan_image import asset_aspect_ratio
from app.modules.storage.oss import load_storage
from app.modules.studio.models import Episode, Project, ProjectAsset, StoryboardClip
from app.modules.studio.schemas import (
    AppendEpisodeRequest,
    AssetCreateRequest,
    AssetUpdateRequest,
    BatchAssetImageAcceptedOut,
    BatchClipVideoAcceptedOut,
    BatchGenerateAssetImagesRequest,
    BatchGenerateClipVideosRequest,
    BatchSkippedAssetOut,
    BatchSkippedClipOut,
    ClipCreateRequest,
    ClipReorderRequest,
    ClipUpdateRequest,
    EpisodeOut,
    ExtractAssetsRequest,
    GenerateAssetImageRequest,
    GenerateClipGridRequest,
    GenerateClipVideoRequest,
    GenerateNewClipRequest,
    GenerateProjectRequest,
    GenerateStoryboardRequest,
    ProjectAssetOut,
    ProjectDetailOut,
    ProjectJobAcceptedOut,
    ProjectMetaOut,
    ProjectSummaryOut,
    RegenerateClipRequest,
    RegenerateStoryRequest,
    RewriteEpisodeRequest,
    SelectMediaHistoryRequest,
    StoryboardClipOut,
    StructuredEpisodeSaveRequest,
    SuggestVariantPromptOut,
    SuggestVariantPromptRequest,
    UpdateProjectRequest,
)
from app.modules.studio.service import (
    create_clip,
    create_project_asset,
    delete_asset_image_history,
    delete_clip,
    delete_clip_video_history,
    delete_project_asset,
    get_owned_project,
    get_project_detail,
    list_user_projects,
    load_jobs_by_id,
    reorder_episode_clips,
    save_structured_episode,
    select_asset_image_history,
    select_clip_video_history,
    serialize_asset_out,
    serialize_clip_out,
    update_clip,
    update_project_asset,
    update_project_meta,
)
from app.workers.ai_tasks import (
    execute_asset_image_job,
    execute_clip_video_job,
    execute_llm_job,
)
from app.workers.media_tasks import execute_episode_compose_job

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ApiResponse[list[ProjectSummaryOut]])
async def list_projects(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[ProjectSummaryOut]]:
    return ApiResponse(data=await list_user_projects(session, user_id=user.id))


@router.get("/{project_id}", response_model=ApiResponse[ProjectDetailOut])
async def get_project(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectDetailOut]:
    return ApiResponse(data=await get_project_detail(session, project_id=project_id, user_id=user.id))


@router.patch("/{project_id}", response_model=ApiResponse[ProjectMetaOut])
async def update_project(
    project_id: UUID,
    body: UpdateProjectRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectMetaOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    updated = await update_project_meta(session, project=project, body=body)
    await session.commit()
    await session.refresh(updated)
    return ApiResponse(
        data=ProjectMetaOut(
            id=updated.id,
            name=updated.name,
            settings=updated.settings,
            cover_url=updated.cover_url,
            cover_key=updated.cover_key,
            updated_at=updated.updated_at,
        )
    )


@router.delete("/{project_id}", response_model=ApiResponse[dict])
async def archive_project(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    active_job = await session.scalar(
        select(Job.id).where(
            Job.project_id == project.id,
            Job.status.in_(("queued", "running", "polling")),
        )
    )
    if active_job is not None:
        raise AppError(
            409,
            "project_has_active_jobs",
            "该项目存在正在进行中的生成任务，请等待任务完成后再删除",
        )
    project.status = "archived"
    await session.commit()
    return ApiResponse(data={"id": str(project.id), "archived": True})


@router.post("/generate", response_model=ApiResponse[ProjectJobAcceptedOut], status_code=202)
async def create_and_generate_project(
    body: GenerateProjectRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectJobAcceptedOut]:
    await assert_llm_balance_positive(session, user.id)
    settings_dict = body.settings.model_dump(by_alias=True)
    project = Project(
        user_id=user.id,
        name=body.settings.name.strip(),
        mode=body.mode,
        source_text=body.text,
        settings=settings_dict,
    )
    session.add(project)
    await session.flush()

    job = await create_job(
        session,
        user_id=user.id,
        project_id=project.id,
        job_type="script_generate",
        input_payload={"feedback": body.feedback},
        step_total=body.settings.episode_count + 2,
        step_label="剧本生成任务已排队",
        idempotency_key=f"script_gen:{user.id}:{idempotency_key}" if idempotency_key else None,
    )
    await session.commit()
    await execute_llm_job.kiq(str(job.id))
    return ApiResponse(data=ProjectJobAcceptedOut(project_id=project.id, job=JobOut.model_validate(job)))


@router.post("/{project_id}/regenerate", response_model=ApiResponse[ProjectJobAcceptedOut], status_code=202)
async def regenerate_project_script(
    project_id: UUID,
    body: RegenerateStoryRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectJobAcceptedOut]:
    await assert_llm_balance_positive(session, user.id)
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    if not project.source_text.strip():
        raise AppError(400, "source_text_missing", "该项目缺少原始故事内容，无法重生成全剧")
    ep_count = int(project.settings.get("episodeCount", 1))
    job = await create_job(
        session,
        user_id=user.id,
        project_id=project.id,
        job_type="script_regenerate",
        input_payload={"feedback": body.feedback},
        step_total=ep_count + 2,
        step_label="全剧重生成任务已排队",
    )
    await session.commit()
    await execute_llm_job.kiq(str(job.id))
    return ApiResponse(data=ProjectJobAcceptedOut(project_id=project.id, job=JobOut.model_validate(job)))


@router.post(
    "/{project_id}/episodes/resume", response_model=ApiResponse[ProjectJobAcceptedOut], status_code=202
)
async def resume_project_episodes(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectJobAcceptedOut]:
    await assert_llm_balance_positive(session, user.id)
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    if not project.outline:
        raise AppError(400, "outline_missing", "该项目尚未生成分集大纲，请使用重生成全剧")
    if not project.source_text.strip():
        raise AppError(400, "source_text_missing", "该项目缺少原始故事内容，无法继续生成")
    planned_eps = project.outline.get("episodes") if isinstance(project.outline, dict) else []
    planned_numbers = {int(item["number"]) for item in (planned_eps or []) if isinstance(item, dict)}
    existing_numbers = set(
        await session.scalars(select(Episode.number).where(Episode.project_id == project.id))
    )
    missing_count = len(planned_numbers - existing_numbers)
    if missing_count <= 0:
        raise AppError(400, "episodes_already_complete", "全部分集均已生成完成，无需继续补写")
    job = await create_job(
        session,
        user_id=user.id,
        project_id=project.id,
        job_type="script_generate",
        input_payload={"resume": True},
        step_total=missing_count + 2,
        step_label=f"继续生成剩余 {missing_count} 集任务已排队",
    )
    await session.commit()
    await execute_llm_job.kiq(str(job.id))
    return ApiResponse(data=ProjectJobAcceptedOut(project_id=project.id, job=JobOut.model_validate(job)))


@router.post(
    "/{project_id}/episodes/append", response_model=ApiResponse[ProjectJobAcceptedOut], status_code=202
)
async def append_project_episode(
    project_id: UUID,
    body: AppendEpisodeRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectJobAcceptedOut]:
    await assert_llm_balance_positive(session, user.id)
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    job = await create_job(
        session,
        user_id=user.id,
        project_id=project.id,
        job_type="episode_append",
        input_payload={"feedback": body.feedback},
        step_total=3,
        step_label="续写新分集任务已排队",
    )
    await session.commit()
    await execute_llm_job.kiq(str(job.id))
    return ApiResponse(data=ProjectJobAcceptedOut(project_id=project.id, job=JobOut.model_validate(job)))


@router.post(
    "/{project_id}/episodes/{episode_number}/rewrite",
    response_model=ApiResponse[ProjectJobAcceptedOut],
    status_code=202,
)
async def rewrite_project_episode(
    project_id: UUID,
    episode_number: int,
    body: RewriteEpisodeRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectJobAcceptedOut]:
    await assert_llm_balance_positive(session, user.id)
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    job = await create_job(
        session,
        user_id=user.id,
        project_id=project.id,
        job_type="episode_rewrite",
        target_id=str(episode_number),
        input_payload={"episodeNumber": episode_number, "feedback": body.feedback},
        step_total=2,
        step_label=f"重写第 {episode_number} 集任务已排队",
    )
    await session.commit()
    await execute_llm_job.kiq(str(job.id))
    return ApiResponse(data=ProjectJobAcceptedOut(project_id=project.id, job=JobOut.model_validate(job)))


@router.put("/{project_id}/episodes/{episode_number}", response_model=ApiResponse[EpisodeOut])
async def update_episode_structured(
    project_id: UUID,
    episode_number: int,
    body: StructuredEpisodeSaveRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[EpisodeOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    ep = await save_structured_episode(
        session,
        project=project,
        episode_number=episode_number,
        title=body.title,
        raw_scenes=body.scenes,
    )
    await session.commit()
    await session.refresh(ep)
    return ApiResponse(data=EpisodeOut.model_validate(ep))


@router.post("/{project_id}/confirm-script", response_model=ApiResponse[dict])
async def confirm_project_script(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    project.script_confirmed = True
    await session.commit()
    return ApiResponse(data={"projectId": str(project.id), "scriptConfirmed": True})


@router.post(
    "/{project_id}/assets/extract", response_model=ApiResponse[ProjectJobAcceptedOut], status_code=202
)
async def extract_project_assets(
    project_id: UUID,
    body: ExtractAssetsRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectJobAcceptedOut]:
    await assert_llm_balance_positive(session, user.id)
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    job = await create_job(
        session,
        user_id=user.id,
        project_id=project.id,
        job_type="assets_extract",
        input_payload={"mode": body.mode},
        step_total=3,
        step_label="资产识别任务已排队",
    )
    await session.commit()
    await execute_llm_job.kiq(str(job.id))
    return ApiResponse(data=ProjectJobAcceptedOut(project_id=project.id, job=JobOut.model_validate(job)))


async def _serialize_single_asset(session: AsyncSession, asset: ProjectAsset) -> ProjectAssetOut:
    last_job = None
    if asset.last_job_id is not None:
        jobs = await load_jobs_by_id(session, {asset.last_job_id})
        last_job = jobs.get(asset.last_job_id)
    return serialize_asset_out(asset, last_job)


async def _serialize_single_clip(session: AsyncSession, clip: StoryboardClip) -> StoryboardClipOut:
    last_job = None
    if clip.last_job_id is not None:
        jobs = await load_jobs_by_id(session, {clip.last_job_id})
        last_job = jobs.get(clip.last_job_id)
    return serialize_clip_out(clip, last_job)


@router.post("/{project_id}/assets", response_model=ApiResponse[ProjectAssetOut], status_code=201)
async def add_project_asset(
    project_id: UUID,
    body: AssetCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectAssetOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    asset = await create_project_asset(session, project=project, body=body)
    await session.commit()
    await session.refresh(asset)
    return ApiResponse(data=await _serialize_single_asset(session, asset))


@router.patch("/{project_id}/assets/{asset_id}", response_model=ApiResponse[ProjectAssetOut])
async def edit_project_asset(
    project_id: UUID,
    asset_id: UUID,
    body: AssetUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectAssetOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    asset = await update_project_asset(session, project=project, asset_id=asset_id, body=body)
    await session.commit()
    await session.refresh(asset)
    return ApiResponse(data=await _serialize_single_asset(session, asset))


@router.post(
    "/{project_id}/assets/{asset_id}/history/select",
    response_model=ApiResponse[ProjectAssetOut],
)
async def select_project_asset_history(
    project_id: UUID,
    asset_id: UUID,
    body: SelectMediaHistoryRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectAssetOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    asset = await select_asset_image_history(
        session, project=project, asset_id=asset_id, history_id=body.history_id
    )
    await session.commit()
    await session.refresh(asset)
    return ApiResponse(data=await _serialize_single_asset(session, asset))


@router.delete(
    "/{project_id}/assets/{asset_id}/history/{history_id}",
    response_model=ApiResponse[ProjectAssetOut],
)
async def remove_project_asset_history(
    project_id: UUID,
    asset_id: UUID,
    history_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectAssetOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    asset = await delete_asset_image_history(
        session, project=project, asset_id=asset_id, history_id=history_id
    )
    await session.commit()
    await session.refresh(asset)
    return ApiResponse(data=await _serialize_single_asset(session, asset))


@router.delete("/{project_id}/assets/{asset_id}", response_model=ApiResponse[dict])
async def remove_project_asset(
    project_id: UUID,
    asset_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    await delete_project_asset(session, project=project, asset_id=asset_id)
    await session.commit()
    return ApiResponse(data={"deleted": True})


async def _assert_no_active_episode_board_or_compose_job(
    session: AsyncSession,
    *,
    project_id: UUID,
    episode: Episode,
) -> None:
    active_jobs = list(
        await session.scalars(
            select(Job).where(
                Job.project_id == project_id,
                Job.status.in_(("queued", "running")),
                Job.job_type.in_(("storyboard_generate", "episode_compose")),
            )
        )
    )
    if not active_jobs:
        return
    episode_clip_ids: set[str] | None = None
    for active in active_jobs:
        payload = active.input_payload if isinstance(active.input_payload, dict) else {}
        payload_ep = payload.get("episodeNumber")
        matches_episode = payload_ep == episode.number
        if not matches_episode and active.job_type == "episode_compose":
            matches_episode = active.target_id == str(episode.id) or payload.get("episodeId") == str(
                episode.id
            )
        if (
            not matches_episode
            and active.job_type == "storyboard_generate"
            and payload.get("action") == "clip_regenerate"
            and payload_ep is None
        ):
            if episode_clip_ids is None:
                episode_clip_ids = {
                    str(cid)
                    for cid in await session.scalars(
                        select(StoryboardClip.id).where(StoryboardClip.episode_id == episode.id)
                    )
                }
            matches_episode = (
                active.target_id in episode_clip_ids
                or payload.get("clipId") in episode_clip_ids
            )
        if matches_episode:
            if active.job_type == "episode_compose":
                raise AppError(
                    409,
                    "episode_compose_in_progress",
                    f"第 {episode.number} 集正在合成视频，请等待当前任务完成后再试",
                )
            raise AppError(
                409,
                "episode_storyboard_in_progress",
                f"第 {episode.number} 集已有分镜任务正在执行，请等待当前任务完成后再试",
            )


@router.post(
    "/{project_id}/episodes/{episode_number}/storyboard/generate",
    response_model=ApiResponse[ProjectJobAcceptedOut],
    status_code=202,
)
async def generate_episode_storyboard(
    project_id: UUID,
    episode_number: int,
    body: GenerateStoryboardRequest | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectJobAcceptedOut]:
    await assert_llm_balance_positive(session, user.id)
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    ep = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == episode_number)
    )
    if ep is None:
        raise AppError(404, "episode_not_found", f"第 {episode_number} 集不存在")
    await _assert_no_active_episode_board_or_compose_job(
        session, project_id=project.id, episode=ep
    )
    feedback = body.feedback.strip() if body else ""
    job = await create_job(
        session,
        user_id=user.id,
        project_id=project.id,
        job_type="storyboard_generate",
        target_id=str(episode_number),
        input_payload={
            "action": "episode",
            "episodeNumber": episode_number,
            **({"feedback": feedback} if feedback else {}),
        },
        step_total=3,
        step_label=f"第 {episode_number} 集分镜任务已排队",
    )
    await session.commit()
    await execute_llm_job.kiq(str(job.id))
    return ApiResponse(data=ProjectJobAcceptedOut(project_id=project.id, job=JobOut.model_validate(job)))


@router.post(
    "/{project_id}/clips/{clip_id}/regenerate",
    response_model=ApiResponse[ProjectJobAcceptedOut],
    status_code=202,
)
async def regenerate_episode_clip(
    project_id: UUID,
    clip_id: UUID,
    body: RegenerateClipRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectJobAcceptedOut]:
    await assert_llm_balance_positive(session, user.id)
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    clip = await session.scalar(
        select(StoryboardClip).where(
            StoryboardClip.id == clip_id, StoryboardClip.project_id == project.id
        )
    )
    if clip is None:
        raise AppError(404, "clip_not_found", "片段不存在")
    ep = await session.scalar(select(Episode).where(Episode.id == clip.episode_id))
    if ep is None:
        raise AppError(404, "episode_not_found", "所属分集不存在")
    await _assert_no_active_episode_board_or_compose_job(
        session, project_id=project.id, episode=ep
    )
    feedback = body.feedback.strip()
    job = await create_job(
        session,
        user_id=user.id,
        project_id=project.id,
        job_type="storyboard_generate",
        target_id=str(clip.id),
        input_payload={
            "action": "clip_regenerate",
            "episodeNumber": ep.number,
            "clipId": str(clip.id),
            "refreshReferences": body.refresh_references,
            **({"feedback": feedback} if feedback else {}),
        },
        step_total=2,
        step_label=f"片段 {clip.clip_index} 分镜重生成已排队",
    )
    await session.commit()
    await execute_llm_job.kiq(str(job.id))
    return ApiResponse(data=ProjectJobAcceptedOut(project_id=project.id, job=JobOut.model_validate(job)))


@router.post(
    "/{project_id}/episodes/{episode_number}/clips/generate",
    response_model=ApiResponse[ProjectJobAcceptedOut],
    status_code=202,
)
async def generate_new_episode_clip(
    project_id: UUID,
    episode_number: int,
    body: GenerateNewClipRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectJobAcceptedOut]:
    await assert_llm_balance_positive(session, user.id)
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    ep = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == episode_number)
    )
    if ep is None:
        raise AppError(404, "episode_not_found", f"第 {episode_number} 集不存在")
    await _assert_no_active_episode_board_or_compose_job(
        session, project_id=project.id, episode=ep
    )
    cap = int((project.settings or {}).get("maxSegmentDuration") or 15)
    if body.duration_seconds > cap:
        raise AppError(
            400,
            "duration_exceeds_project_cap",
            f"当前项目单片段时长上限为 {cap} 秒，请将目标时长调整至 {cap} 秒以内",
        )
    feedback = body.feedback.strip()
    job = await create_job(
        session,
        user_id=user.id,
        project_id=project.id,
        job_type="storyboard_generate",
        target_id=str(episode_number),
        input_payload={
            "action": "clip_create",
            "episodeNumber": episode_number,
            "durationSeconds": body.duration_seconds,
            **(
                {"insertAfterClipId": str(body.insert_after_clip_id)}
                if body.insert_after_clip_id
                else {}
            ),
            **({"feedback": feedback} if feedback else {}),
        },
        step_total=2,
        step_label=f"第 {episode_number} 集新增片段任务已排队",
    )
    await session.commit()
    await execute_llm_job.kiq(str(job.id))
    return ApiResponse(data=ProjectJobAcceptedOut(project_id=project.id, job=JobOut.model_validate(job)))


@router.post(
    "/{project_id}/episodes/{episode_number}/clips",
    response_model=ApiResponse[StoryboardClipOut],
    status_code=201,
)
async def add_episode_clip(
    project_id: UUID,
    episode_number: int,
    body: ClipCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[StoryboardClipOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    clip = await create_clip(session, project=project, episode_number=episode_number, body=body)
    await session.commit()
    await session.refresh(clip)
    return ApiResponse(data=StoryboardClipOut.model_validate(clip))


@router.put(
    "/{project_id}/episodes/{episode_number}/clips/reorder",
    response_model=ApiResponse[list[StoryboardClipOut]],
)
async def reorder_clips(
    project_id: UUID,
    episode_number: int,
    body: ClipReorderRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[StoryboardClipOut]]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    ordered = await reorder_episode_clips(
        session, project=project, episode_number=episode_number, clip_ids=body.clip_ids
    )
    await session.commit()
    return ApiResponse(data=[StoryboardClipOut.model_validate(item) for item in ordered])


@router.patch("/{project_id}/clips/{clip_id}", response_model=ApiResponse[StoryboardClipOut])
async def edit_episode_clip(
    project_id: UUID,
    clip_id: UUID,
    body: ClipUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[StoryboardClipOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    clip = await update_clip(session, project=project, clip_id=clip_id, body=body)
    await session.commit()
    await session.refresh(clip)
    return ApiResponse(data=await _serialize_single_clip(session, clip))


@router.post(
    "/{project_id}/episodes/{episode_number}/clips/{clip_id}/history/select",
    response_model=ApiResponse[StoryboardClipOut],
)
async def select_episode_clip_history(
    project_id: UUID,
    episode_number: int,
    clip_id: UUID,
    body: SelectMediaHistoryRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[StoryboardClipOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    clip = await select_clip_video_history(
        session,
        project=project,
        episode_number=episode_number,
        clip_id=clip_id,
        history_id=body.history_id,
    )
    await session.commit()
    await session.refresh(clip)
    return ApiResponse(data=await _serialize_single_clip(session, clip))


@router.delete(
    "/{project_id}/episodes/{episode_number}/clips/{clip_id}/history/{history_id}",
    response_model=ApiResponse[StoryboardClipOut],
)
async def remove_episode_clip_history(
    project_id: UUID,
    episode_number: int,
    clip_id: UUID,
    history_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[StoryboardClipOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    clip = await delete_clip_video_history(
        session,
        project=project,
        episode_number=episode_number,
        clip_id=clip_id,
        history_id=history_id,
    )
    await session.commit()
    await session.refresh(clip)
    return ApiResponse(data=await _serialize_single_clip(session, clip))


@router.delete("/{project_id}/clips/{clip_id}", response_model=ApiResponse[dict])
async def remove_episode_clip(
    project_id: UUID,
    clip_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    await delete_clip(session, project=project, clip_id=clip_id)
    await session.commit()
    return ApiResponse(data={"deleted": True})


async def _validate_image_model_and_infra(
    session: AsyncSession,
    *,
    model_id: str,
    tier: str,
    ratio: str | None = None,
) -> AiModel:
    model = await session.scalar(
        select(AiModel).where(
            AiModel.id == model_id,
            AiModel.media_type == "image",
            AiModel.enabled.is_(True),
        )
    )
    if model is None:
        raise AppError(400, "image_model_unavailable", f"图片模型 {model_id} 不存在或未启用")
    allowed_tiers = model.capabilities.get("tiers") or ["web", "1k", "2k", "4k"]
    if tier not in allowed_tiers:
        raise AppError(400, "invalid_image_tier", f"模型 {model.display_name} 不支持 {tier} 档位")
    allowed_ratios = model.capabilities.get("ratios") or []
    if ratio and allowed_ratios and ratio not in allowed_ratios:
        raise AppError(
            400,
            "invalid_image_ratio",
            f"模型 {model.display_name} 不支持 {ratio} 画面比例",
        )

    provider = await session.scalar(
        select(AiProvider)
        .options(undefer(AiProvider.api_key))
        .where(AiProvider.id == model.provider_id, AiProvider.enabled.is_(True))
    )
    if provider is None or not provider.api_key.strip():
        raise AppError(
            503,
            "provider_not_configured",
            "尚未配置沧元图片供应商 API Key，请先配置或从 Moonflow 导入",
        )

    # 预先校验阿里云 OSS 已配置，避免生图成功扣费后无法转存。
    await load_storage(session)
    return model


@router.post(
    "/{project_id}/assets/{asset_id}/suggest-variant-prompt",
    response_model=ApiResponse[SuggestVariantPromptOut],
)
async def suggest_asset_variant_prompt_endpoint(
    project_id: UUID,
    asset_id: UUID,
    body: SuggestVariantPromptRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[SuggestVariantPromptOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    target = await session.scalar(
        select(ProjectAsset).where(
            ProjectAsset.id == asset_id,
            ProjectAsset.project_id == project.id,
        )
    )
    if target is None:
        raise AppError(404, "asset_not_found", "资产不存在")
    parent = target
    if target.parent_asset_id is not None:
        root = await session.scalar(
            select(ProjectAsset).where(
                ProjectAsset.id == target.parent_asset_id,
                ProjectAsset.project_id == project.id,
            )
        )
        if root is not None:
            parent = root

    await assert_llm_balance_positive(session, user.id)
    model, model_id = await resolve_text_model(session)
    usage = RunUsage()
    settings_payload = dict(project.settings or {})
    if isinstance(project.outline, dict) and project.outline.get("world"):
        settings_payload["world"] = project.outline["world"]

    suggestion = await suggest_variant_prompt(
        model,
        kind=parent.kind,  # type: ignore[arg-type]
        name=parent.name,
        parent_description=parent.description or parent.name,
        parent_prompt=parent.prompt or parent.name,
        variant_label=body.variant_label,
        note=body.note,
        settings_payload=settings_payload,
        usage=usage,
    )
    await charge_llm_usage(
        session,
        user_id=user.id,
        model_id=model_id,
        job_id=None,
        input_tokens=usage.input_tokens or 0,
        cache_read_tokens=usage.cache_read_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        idempotency_key=f"suggest_variant:{uuid4().hex}",
        reason=f"AI 生成变体提示词 ({parent.name} · {body.variant_label.strip()})",
    )
    await session.commit()
    return ApiResponse(
        data=SuggestVariantPromptOut(
            description=suggestion.description,
            prompt=suggestion.prompt,
        )
    )


@router.post(
    "/{project_id}/assets/batch-generate-image",
    response_model=ApiResponse[BatchAssetImageAcceptedOut],
    status_code=202,
)
async def batch_generate_asset_images(
    project_id: UUID,
    body: BatchGenerateAssetImagesRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BatchAssetImageAcceptedOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    override_ratio = (body.ratio or "").strip() or None
    model = await _validate_image_model_and_infra(
        session, model_id=body.model_id, tier=body.tier, ratio=override_ratio
    )

    # 去重并保持用户选择顺序
    unique_ids = list(dict.fromkeys(body.asset_ids))
    rows = list(
        await session.scalars(
            select(ProjectAsset).where(
                ProjectAsset.project_id == project.id,
                ProjectAsset.id.in_(unique_ids),
            )
        )
    )
    assets_by_id = {row.id: row for row in rows}
    active_target_ids = set(
        await session.scalars(
            select(Job.target_id).where(
                Job.project_id == project.id,
                Job.job_type == "asset_image",
                Job.status.in_(("queued", "running", "polling")),
                Job.target_id.is_not(None),
            )
        )
    )

    eligible: list[ProjectAsset] = []
    skipped: list[BatchSkippedAssetOut] = []
    for aid in unique_ids:
        asset = assets_by_id.get(aid)
        if asset is None:
            skipped.append(BatchSkippedAssetOut(asset_id=aid, name="未知资产", reason="资产不存在"))
            continue
        if str(asset.id) in active_target_ids:
            skipped.append(BatchSkippedAssetOut(asset_id=asset.id, name=asset.name, reason="正在生图中"))
            continue
        if not (asset.prompt or "").strip():
            skipped.append(
                BatchSkippedAssetOut(asset_id=asset.id, name=asset.name, reason="缺少文生图提示词")
            )
            continue
        eligible.append(asset)

    if not eligible:
        raise AppError(
            400,
            "no_eligible_assets",
            "所选资产当前均不可生图（可能正在生图中或缺少文生图提示词）",
        )

    unit_price, rate_snapshot = await quote_image_price(
        session,
        model_id=model.id,
        tier=body.tier,
        usage_multiplier=user.usage_multiplier,
    )
    total_cost = (unit_price * Decimal(len(eligible))).quantize(Decimal("0.0001"))

    # 一次性锁用户行校验总余额，避免扣到一半失败
    locked_user = await session.scalar(select(User).where(User.id == user.id).with_for_update())
    if locked_user is None:
        raise AppError(404, "user_not_found", "用户不存在")
    if locked_user.balance < total_cost:
        raise AppError(
            402,
            "insufficient_credits",
            (
                f"积分不足：本次共 {len(eligible)} 张需预冻结 {total_cost} 积分，"
                f"当前可用 {locked_user.balance} 积分"
            ),
        )

    parent_ids_needed = {
        a.parent_asset_id
        for a in eligible
        if body.use_parent_reference
        and a.parent_asset_id is not None
        and a.parent_asset_id not in assets_by_id
    }
    if parent_ids_needed:
        parent_rows = list(
            await session.scalars(
                select(ProjectAsset).where(
                    ProjectAsset.project_id == project.id,
                    ProjectAsset.id.in_(parent_ids_needed),
                )
            )
        )
        for prow in parent_rows:
            assets_by_id[prow.id] = prow

    batch_id = uuid4().hex[:16]
    created_jobs: list[Job] = []
    for asset in eligible:
        ratio = override_ratio or asset_aspect_ratio(asset.kind)
        ref_urls: list[str] = []
        if body.use_parent_reference and asset.parent_asset_id is not None:
            parent_row = assets_by_id.get(asset.parent_asset_id)
            parent_url = (parent_row.image_url or "").strip() if parent_row is not None else ""
            if parent_url.startswith(("http://", "https://")):
                ref_urls = [parent_url]
        job = await create_job(
            session,
            user_id=user.id,
            project_id=project.id,
            job_type="asset_image",
            target_id=str(asset.id),
            input_payload={
                "assetId": str(asset.id),
                "batchId": batch_id,
                "modelId": model.id,
                "tier": body.tier,
                "ratio": ratio,
                "prompt": asset.prompt.strip(),
                **({"referenceUrls": ref_urls} if ref_urls else {}),
            },
            step_total=4,
            step_label=f"资产「{asset.name}」批量生图已排队",
        )
        await freeze_media_credits(
            session,
            user_id=user.id,
            business_type="image",
            business_id=job.id,
            model_id=model.id,
            amount=unit_price,
            rate_snapshot=rate_snapshot,
            reason=f"批量资产生图预冻结 ({asset.name} · {model.id}/{body.tier})",
        )
        asset.image_status = "generating"
        asset.image_model_id = model.id
        asset.image_tier = body.tier
        asset.last_job_id = job.id
        created_jobs.append(job)

    await session.commit()
    for job in created_jobs:
        await execute_asset_image_job.kiq(str(job.id))

    return ApiResponse(
        data=BatchAssetImageAcceptedOut(
            project_id=project.id,
            batch_id=batch_id,
            accepted_count=len(created_jobs),
            total_frozen_credits=total_cost,
            jobs=[JobOut.model_validate(j) for j in created_jobs],
            skipped=skipped,
        )
    )


@router.post(
    "/{project_id}/assets/{asset_id}/generate-image",
    response_model=ApiResponse[ProjectJobAcceptedOut],
    status_code=202,
)
async def generate_asset_image(
    project_id: UUID,
    asset_id: UUID,
    body: GenerateAssetImageRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectJobAcceptedOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    asset = await session.scalar(
        select(ProjectAsset).where(ProjectAsset.id == asset_id, ProjectAsset.project_id == project.id)
    )
    if asset is None:
        raise AppError(404, "asset_not_found", "资产不存在")
    prompt = (asset.prompt or "").strip()
    if not prompt:
        raise AppError(400, "prompt_missing", "请先填写资产的视觉描述/生图提示词")

    existing_active = await session.scalar(
        select(Job.id).where(
            Job.project_id == project.id,
            Job.job_type == "asset_image",
            Job.target_id == str(asset.id),
            Job.status.in_(("queued", "running", "polling")),
        )
    )
    if existing_active is not None:
        raise AppError(409, "asset_image_in_progress", f"资产「{asset.name}」正在生图中，请等待当前任务完成")

    override_ratio = (body.ratio or "").strip() or None
    model = await _validate_image_model_and_infra(
        session, model_id=body.model_id, tier=body.tier, ratio=override_ratio
    )
    cleaned_ref_urls: list[str] = []
    for raw_url in body.reference_urls:
        u = raw_url.strip()
        if not u:
            continue
        if not u.startswith(("http://", "https://")):
            raise AppError(400, "invalid_reference_url", "参考图地址必须为可访问的 HTTP/HTTPS 链接")
        cleaned_ref_urls.append(u)
    max_ref_images = int(model.capabilities.get("maxReferenceImages") or 9)
    if len(cleaned_ref_urls) > max_ref_images:
        raise AppError(
            400,
            "reference_images_exceed_limit",
            f"{model.display_name} 最多支持 {max_ref_images} 张参考图，当前传入了 {len(cleaned_ref_urls)} 张",
        )

    ratio = override_ratio or asset_aspect_ratio(asset.kind)
    amount, rate_snapshot = await quote_image_price(
        session,
        model_id=model.id,
        tier=body.tier,
        usage_multiplier=user.usage_multiplier,
    )
    job = await create_job(
        session,
        user_id=user.id,
        project_id=project.id,
        job_type="asset_image",
        target_id=str(asset.id),
        input_payload={
            "assetId": str(asset.id),
            "modelId": model.id,
            "tier": body.tier,
            "ratio": ratio,
            "prompt": prompt,
            **({"referenceUrls": cleaned_ref_urls} if cleaned_ref_urls else {}),
        },
        step_total=4,
        step_label=f"资产「{asset.name}」生图任务已排队",
        idempotency_key=f"asset_img:{user.id}:{idempotency_key}" if idempotency_key else None,
    )
    await freeze_media_credits(
        session,
        user_id=user.id,
        business_type="image",
        business_id=job.id,
        model_id=model.id,
        amount=amount,
        rate_snapshot=rate_snapshot,
        reason=f"资产生图预冻结 ({asset.name} · {model.id}/{body.tier})",
    )
    asset.image_status = "generating"
    asset.image_model_id = model.id
    asset.image_tier = body.tier
    asset.last_job_id = job.id
    await session.commit()
    await execute_asset_image_job.kiq(str(job.id))
    return ApiResponse(data=ProjectJobAcceptedOut(project_id=project.id, job=JobOut.model_validate(job)))


async def _validate_video_model_and_infra(
    session: AsyncSession,
    *,
    model_id: str,
    resolution: str,
    ratio: str | None = None,
) -> tuple[AiModel, dict[str, int]]:
    model = await session.scalar(
        select(AiModel).where(
            AiModel.id == model_id,
            AiModel.media_type == "video",
            AiModel.enabled.is_(True),
        )
    )
    if model is None:
        raise AppError(400, "video_model_unavailable", f"视频模型 {model_id} 不存在或未启用")
    if not model.upstream_available:
        raise AppError(
            400,
            "video_model_upstream_offline",
            f"视频模型 {model.display_name} 当前上游已下架，请切换其他可用模型",
        )

    caps = model.capabilities or {}
    min_duration = int(caps.get("minDuration") or 4)
    max_duration = int(caps.get("maxDuration") or 15)
    max_prompt_chars = int(caps.get("maxPromptChars") or 5000)
    raw_max_images = caps.get("maxReferenceImages")
    raw_max_videos = caps.get("maxReferenceVideos")
    raw_max_audios = caps.get("maxReferenceAudios")
    max_ref_images = int(raw_max_images) if raw_max_images is not None else 9
    max_ref_videos = int(raw_max_videos) if raw_max_videos is not None else 0
    max_ref_audios = int(raw_max_audios) if raw_max_audios is not None else 0

    allowed_resolutions = caps.get("resolutions") or ["720p", "1080p"]
    if resolution not in allowed_resolutions:
        raise AppError(
            400,
            "invalid_video_resolution",
            f"模型 {model.display_name} 不支持 {resolution} 分辨率",
        )

    allowed_ratios = caps.get("ratios") or []
    if ratio and allowed_ratios and ratio not in allowed_ratios:
        raise AppError(
            400,
            "invalid_video_ratio",
            f"模型 {model.display_name} 不支持 {ratio} 画面比例（仅支持 {' / '.join(allowed_ratios)}）",
        )

    provider = await session.scalar(
        select(AiProvider)
        .options(undefer(AiProvider.api_key))
        .where(AiProvider.id == model.provider_id, AiProvider.enabled.is_(True))
    )
    if provider is None or not provider.api_key.strip():
        raise AppError(
            503,
            "provider_not_configured",
            "尚未配置 CC 视频供应商 API Key，请先配置或从 Moonflow 导入",
        )

    await load_storage(session)
    return model, {
        "minDuration": min_duration,
        "maxDuration": max_duration,
        "maxPromptChars": max_prompt_chars,
        "maxReferenceImages": max_ref_images,
        "maxReferenceVideos": max_ref_videos,
        "maxReferenceAudios": max_ref_audios,
    }


def _resolve_clip_references(
    clip: StoryboardClip,
    *,
    by_uuid: dict[str, ProjectAsset],
    by_code: dict[str, ProjectAsset],
) -> tuple[list[str], list[str], list[str], str | None]:
    ordered_refs = sorted(
        list(clip.references or []),
        key=lambda item: int(item.get("index", 999)) if isinstance(item, dict) else 999,
    )
    image_urls: list[str] = []
    video_urls: list[str] = []
    audio_urls: list[str] = []
    for ref in ordered_refs:
        if not isinstance(ref, dict):
            continue
        ref_id = str(ref.get("assetId") or "").strip()
        ref_code = str(ref.get("assetCode") or "").strip()
        matched = by_uuid.get(ref_id) or by_code.get(ref_code) or by_code.get(ref_id)
        if matched is not None:
            ref_name = (matched.name or ref_id or "参考素材").strip()
            img_url = (matched.image_url or "").strip()
            if not img_url.startswith(("http://", "https://")):
                return [], [], [], ref_name
            image_urls.append(img_url)
            continue

        direct_url = str(ref.get("mediaUrl") or "").strip()
        ref_name = str(ref.get("name") or ref_id or "参考素材").strip()
        if not direct_url.startswith(("http://", "https://")):
            return [], [], [], ref_name
        media_kind = str(ref.get("mediaKind") or "image").strip().lower()
        if media_kind == "video":
            video_urls.append(direct_url)
        elif media_kind == "audio":
            audio_urls.append(direct_url)
        else:
            image_urls.append(direct_url)
    return image_urls, video_urls, audio_urls, None


def _check_video_ref_limits(
    *,
    model_name: str,
    image_count: int,
    video_count: int,
    audio_count: int,
    limits: dict[str, int],
) -> tuple[str, str] | None:
    max_images = limits["maxReferenceImages"]
    max_videos = limits["maxReferenceVideos"]
    max_audios = limits["maxReferenceAudios"]
    if image_count > max_images:
        return (
            "reference_images_exceed_limit",
            f"{model_name} 最多支持 {max_images} 张参考图，当前引用了 {image_count} 张",
        )
    if video_count > max_videos:
        if max_videos <= 0:
            return (
                "reference_videos_not_supported",
                f"{model_name} 不支持参考视频，请移除视频素材或切换支持视频参考的模型",
            )
        return (
            "reference_videos_exceed_limit",
            f"{model_name} 最多支持 {max_videos} 个参考视频，当前引用了 {video_count} 个",
        )
    if audio_count > max_audios:
        if max_audios <= 0:
            return (
                "reference_audios_not_supported",
                f"{model_name} 不支持参考音频，请移除音频素材或切换支持音频参考的模型",
            )
        return (
            "reference_audios_exceed_limit",
            f"{model_name} 最多支持 {max_audios} 个参考音频，当前引用了 {audio_count} 个",
        )
    return None


@router.post(
    "/{project_id}/episodes/{episode_number}/clips/batch-generate-video",
    response_model=ApiResponse[BatchClipVideoAcceptedOut],
    status_code=202,
)
async def batch_generate_clip_videos(
    project_id: UUID,
    episode_number: int,
    body: BatchGenerateClipVideosRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BatchClipVideoAcceptedOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    episode = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == episode_number)
    )
    if episode is None:
        raise AppError(404, "episode_not_found", f"第 {episode_number} 集不存在")
    await _assert_no_active_episode_board_or_compose_job(
        session, project_id=project.id, episode=episode
    )

    ratio = (body.ratio or "").strip() or str(project.settings.get("ratio") or "16:9")
    model, limits = await _validate_video_model_and_infra(
        session, model_id=body.model_id, resolution=body.resolution, ratio=ratio
    )
    min_duration = limits["minDuration"]
    max_duration = limits["maxDuration"]
    max_prompt_chars = limits["maxPromptChars"]

    if body.duration_seconds is not None and (
        body.duration_seconds < min_duration or body.duration_seconds > max_duration
    ):
        raise AppError(
            400,
            "duration_exceeds_model_limit",
            (
                f"{model.display_name} 支持 {min_duration}–{max_duration} 秒，"
                f"当前指定时长为 {body.duration_seconds} 秒"
            ),
        )

    unique_ids = list(dict.fromkeys(body.clip_ids))
    rows = list(
        await session.scalars(
            select(StoryboardClip).where(
                StoryboardClip.project_id == project.id,
                StoryboardClip.episode_id == episode.id,
                StoryboardClip.id.in_(unique_ids),
            )
        )
    )
    clips_by_id = {row.id: row for row in rows}
    active_target_ids = set(
        await session.scalars(
            select(Job.target_id).where(
                Job.project_id == project.id,
                Job.job_type == "clip_video",
                Job.status.in_(("queued", "running", "polling")),
                Job.target_id.is_not(None),
            )
        )
    )
    project_assets = list(
        await session.scalars(select(ProjectAsset).where(ProjectAsset.project_id == project.id))
    )
    by_uuid = {str(a.id): a for a in project_assets}
    by_code = {a.asset_code: a for a in project_assets}

    eligible: list[tuple[StoryboardClip, list[str], list[str], list[str], Decimal, dict]] = []
    skipped: list[BatchSkippedClipOut] = []
    for cid in unique_ids:
        clip = clips_by_id.get(cid)
        if clip is None:
            skipped.append(BatchSkippedClipOut(clip_id=cid, reason="片段不存在"))
            continue
        if str(clip.id) in active_target_ids:
            skipped.append(
                BatchSkippedClipOut(clip_id=clip.id, clip_index=clip.clip_index, reason="正在生成视频中")
            )
            continue
        prompt_text = (clip.prompt or "").strip()
        if not prompt_text:
            skipped.append(
                BatchSkippedClipOut(clip_id=clip.id, clip_index=clip.clip_index, reason="缺少视频提示词")
            )
            continue
        removed_refs = find_removed_prompt_refs(prompt_text)
        if removed_refs:
            labels = "、".join(removed_refs[:3])
            skipped.append(
                BatchSkippedClipOut(
                    clip_id=clip.id,
                    clip_index=clip.clip_index,
                    reason=f"提示词包含已移除的引用（{labels}），请先清理后再生成",
                )
            )
            continue
        if len(prompt_text) > max_prompt_chars:
            skipped.append(
                BatchSkippedClipOut(
                    clip_id=clip.id,
                    clip_index=clip.clip_index,
                    reason=f"提示词 {len(prompt_text)} 字超过模型上限 {max_prompt_chars} 字",
                )
            )
            continue
        effective_duration = (
            body.duration_seconds
            if body.duration_seconds is not None
            else clip.duration_seconds
        )
        if effective_duration < min_duration or effective_duration > max_duration:
            skipped.append(
                BatchSkippedClipOut(
                    clip_id=clip.id,
                    clip_index=clip.clip_index,
                    reason=f"时长 {effective_duration}s 不在模型支持范围 {min_duration}–{max_duration}s",
                )
            )
            continue
        ref_images, ref_videos, ref_audios, missing_ref = _resolve_clip_references(
            clip, by_uuid=by_uuid, by_code=by_code
        )
        if missing_ref is not None:
            skipped.append(
                BatchSkippedClipOut(
                    clip_id=clip.id,
                    clip_index=clip.clip_index,
                    reason=f"参考素材「{missing_ref}」缺少公网媒体文件",
                )
            )
            continue
        limit_err = _check_video_ref_limits(
            model_name=model.display_name,
            image_count=len(ref_images),
            video_count=len(ref_videos),
            audio_count=len(ref_audios),
            limits=limits,
        )
        if limit_err is not None:
            skipped.append(
                BatchSkippedClipOut(
                    clip_id=clip.id,
                    clip_index=clip.clip_index,
                    reason=limit_err[1],
                )
            )
            continue
        amount, rate_snapshot = await quote_video_price(
            session,
            model_id=model.id,
            duration_seconds=effective_duration,
            rule_key=body.resolution,
            usage_multiplier=user.usage_multiplier,
        )
        eligible.append((clip, ref_images, ref_videos, ref_audios, amount, rate_snapshot))

    if not eligible:
        raise AppError(
            400,
            "no_eligible_clips",
            "所选片段当前均不可生成视频（可能正在生成、缺少参考素材或超出模型限制）",
        )

    total_cost = sum((item[4] for item in eligible), Decimal("0.0000")).quantize(Decimal("0.0001"))
    total_duration = sum(
        (body.duration_seconds if body.duration_seconds is not None else item[0].duration_seconds)
        for item in eligible
    )

    locked_user = await session.scalar(select(User).where(User.id == user.id).with_for_update())
    if locked_user is None:
        raise AppError(404, "user_not_found", "用户不存在")
    if locked_user.balance < total_cost:
        raise AppError(
            402,
            "insufficient_credits",
            (
                f"积分不足：本次共 {len(eligible)} 段（{total_duration}s）需预冻结 {total_cost} 积分，"
                f"当前可用 {locked_user.balance} 积分"
            ),
        )

    batch_id = uuid4().hex[:16]
    created_jobs: list[Job] = []
    for clip, ref_images, ref_videos, ref_audios, amount, rate_snapshot in eligible:
        effective_duration = (
            body.duration_seconds
            if body.duration_seconds is not None
            else clip.duration_seconds
        )
        if body.duration_seconds is not None:
            clip.duration_seconds = body.duration_seconds
        job = await create_job(
            session,
            user_id=user.id,
            project_id=project.id,
            job_type="clip_video",
            target_id=str(clip.id),
            input_payload={
                "clipId": str(clip.id),
                "episodeNumber": episode.number,
                "batchId": batch_id,
                "modelId": model.id,
                "resolution": body.resolution,
                "ratio": ratio,
                "durationSeconds": effective_duration,
                "prompt": clip.prompt.strip(),
                "referenceUrls": ref_images,
                "referenceVideoUrls": ref_videos,
                "referenceAudioUrls": ref_audios,
            },
            step_total=4,
            step_label=f"片段 {clip.clip_index} 批量生视频已排队",
        )
        await freeze_media_credits(
            session,
            user_id=user.id,
            business_type="video",
            business_id=job.id,
            model_id=model.id,
            amount=amount,
            rate_snapshot=rate_snapshot,
            reason=f"批量片段生视频预冻结 (片段{clip.clip_index} · {model.id}/{effective_duration}s)",
        )
        clip.video_status = "generating"
        clip.video_model_id = model.id
        clip.last_job_id = job.id
        created_jobs.append(job)

    await session.commit()
    for job in created_jobs:
        await execute_clip_video_job.kiq(str(job.id))

    return ApiResponse(
        data=BatchClipVideoAcceptedOut(
            project_id=project.id,
            episode_number=episode.number,
            batch_id=batch_id,
            accepted_count=len(created_jobs),
            total_duration_seconds=total_duration,
            total_frozen_credits=total_cost,
            jobs=[JobOut.model_validate(j) for j in created_jobs],
            skipped=skipped,
        )
    )


@router.post(
    "/{project_id}/clips/{clip_id}/generate-video",
    response_model=ApiResponse[ProjectJobAcceptedOut],
    status_code=202,
)
async def generate_clip_video(
    project_id: UUID,
    clip_id: UUID,
    body: GenerateClipVideoRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectJobAcceptedOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    clip = await session.scalar(
        select(StoryboardClip).where(
            StoryboardClip.id == clip_id, StoryboardClip.project_id == project.id
        )
    )
    if clip is None:
        raise AppError(404, "clip_not_found", "片段不存在")
    prompt = (clip.prompt or "").strip()
    if not prompt:
        raise AppError(400, "prompt_missing", "片段提示词为空，无法生成视频")
    removed_refs = find_removed_prompt_refs(prompt)
    if removed_refs:
        labels = "、".join(removed_refs[:3])
        raise AppError(
            400,
            "prompt_has_removed_reference",
            f"提示词包含已移除的引用（{labels}），请先删除或重新 @ 引用素材后再生成",
        )

    existing_active = await session.scalar(
        select(Job.id).where(
            Job.project_id == project.id,
            Job.job_type == "clip_video",
            Job.target_id == str(clip.id),
            Job.status.in_(("queued", "running", "polling")),
        )
    )
    if existing_active is not None:
        raise AppError(
            409, "clip_video_in_progress", f"片段 {clip.clip_index} 正在生成视频中，请等待当前任务完成"
        )

    ratio = (body.ratio or "").strip() or str(project.settings.get("ratio") or "16:9")
    model, limits = await _validate_video_model_and_infra(
        session, model_id=body.model_id, resolution=body.resolution, ratio=ratio
    )
    min_duration = limits["minDuration"]
    max_duration = limits["maxDuration"]
    max_prompt_chars = limits["maxPromptChars"]

    effective_duration = body.duration_seconds if body.duration_seconds is not None else clip.duration_seconds
    if len(prompt) > max_prompt_chars:
        raise AppError(
            400,
            "prompt_exceeds_model_limit",
            f"{model.display_name} 提示词上限为 {max_prompt_chars} 字，当前为 {len(prompt)} 字",
        )
    if effective_duration < min_duration or effective_duration > max_duration:
        raise AppError(
            400,
            "duration_exceeds_model_limit",
            (
                f"{model.display_name} 支持 {min_duration}–{max_duration} 秒，"
                f"当前片段为 {effective_duration} 秒，请切换模型或调整片段时长"
            ),
        )
    if body.duration_seconds is not None:
        clip.duration_seconds = body.duration_seconds

    project_assets = list(
        await session.scalars(select(ProjectAsset).where(ProjectAsset.project_id == project.id))
    )
    by_uuid = {str(a.id): a for a in project_assets}
    by_code = {a.asset_code: a for a in project_assets}
    ref_images, ref_videos, ref_audios, missing_ref = _resolve_clip_references(
        clip, by_uuid=by_uuid, by_code=by_code
    )
    if missing_ref is not None:
        raise AppError(
            400,
            "reference_image_missing",
            f"参考素材「{missing_ref}」尚未生成或上传公网媒体文件，请先完成生图或上传",
        )
    limit_err = _check_video_ref_limits(
        model_name=model.display_name,
        image_count=len(ref_images),
        video_count=len(ref_videos),
        audio_count=len(ref_audios),
        limits=limits,
    )
    if limit_err is not None:
        raise AppError(400, limit_err[0], limit_err[1])
    amount, rate_snapshot = await quote_video_price(
        session,
        model_id=model.id,
        duration_seconds=clip.duration_seconds,
        rule_key=body.resolution,
        usage_multiplier=user.usage_multiplier,
    )
    job = await create_job(
        session,
        user_id=user.id,
        project_id=project.id,
        job_type="clip_video",
        target_id=str(clip.id),
        input_payload={
            "clipId": str(clip.id),
            "modelId": model.id,
            "resolution": body.resolution,
            "ratio": ratio,
            "durationSeconds": clip.duration_seconds,
            "prompt": prompt,
            "referenceUrls": ref_images,
            "referenceVideoUrls": ref_videos,
            "referenceAudioUrls": ref_audios,
        },
        step_total=4,
        step_label=f"片段 {clip.clip_index} 视频生成任务已排队",
        idempotency_key=f"clip_vid:{user.id}:{idempotency_key}" if idempotency_key else None,
    )
    await freeze_media_credits(
        session,
        user_id=user.id,
        business_type="video",
        business_id=job.id,
        model_id=model.id,
        amount=amount,
        rate_snapshot=rate_snapshot,
        reason=f"片段生视频预冻结 (片段{clip.clip_index} · {model.id}/{clip.duration_seconds}s)",
    )
    clip.video_status = "generating"
    clip.video_model_id = model.id
    clip.last_job_id = job.id
    await session.commit()
    await execute_clip_video_job.kiq(str(job.id))
    return ApiResponse(data=ProjectJobAcceptedOut(project_id=project.id, job=JobOut.model_validate(job)))


@router.post(
    "/{project_id}/clips/{clip_id}/generate-storyboard-grid",
    response_model=ApiResponse[ProjectJobAcceptedOut],
    status_code=202,
)
async def generate_clip_storyboard_grid(
    project_id: UUID,
    clip_id: UUID,
    body: GenerateClipGridRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectJobAcceptedOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    clip = await session.scalar(
        select(StoryboardClip).where(
            StoryboardClip.id == clip_id, StoryboardClip.project_id == project.id
        )
    )
    if clip is None:
        raise AppError(404, "clip_not_found", "片段不存在")
    if not (clip.cuts or (clip.prompt or "").strip()):
        raise AppError(400, "clip_empty", "片段缺少镜头与提示词，无法生成分镜宫格图")

    existing_active = await session.scalar(
        select(Job.id).where(
            Job.project_id == project.id,
            Job.target_id == str(clip.id),
            Job.job_type.in_(("asset_image", "clip_video")),
            Job.status.in_(("queued", "running", "polling")),
        )
    )
    if existing_active is not None:
        raise AppError(
            409,
            "clip_grid_in_progress",
            f"片段 {clip.clip_index} 正在生成宫格图或视频中，请等待当前任务完成",
        )

    await assert_llm_balance_positive(session, user.id)
    ratio = (body.ratio or "").strip() or str(project.settings.get("ratio") or "16:9")
    model = await _validate_image_model_and_infra(
        session, model_id=body.model_id, tier=body.tier, ratio=ratio
    )
    max_ref_images = int(model.capabilities.get("maxReferenceImages") or 9)

    episode = await session.scalar(select(Episode).where(Episode.id == clip.episode_id))
    project_assets = list(
        await session.scalars(select(ProjectAsset).where(ProjectAsset.project_id == project.id))
    )
    by_uuid = {str(a.id): a for a in project_assets}
    by_code = {a.asset_code: a for a in project_assets}

    ref_urls: list[str] = []
    ordered_refs = sorted(
        list(clip.references or []),
        key=lambda item: int(item.get("index", 999)) if isinstance(item, dict) else 999,
    )
    for ref in ordered_refs:
        if not isinstance(ref, dict):
            continue
        if ref.get("kind") == "storyboard_grid" or str(ref.get("assetId") or "").startswith("grid:"):
            continue
        ref_id = str(ref.get("assetId") or "").strip()
        ref_code = str(ref.get("assetCode") or "").strip()
        matched = by_uuid.get(ref_id) or by_code.get(ref_code) or by_code.get(ref_id)
        url = ""
        if matched is not None:
            url = (matched.image_url or "").strip()
        else:
            media_kind = str(ref.get("mediaKind") or "image").strip().lower()
            if media_kind == "image":
                url = str(ref.get("mediaUrl") or "").strip()
        if url.startswith(("http://", "https://")) and url not in ref_urls:
            ref_urls.append(url)
            if len(ref_urls) >= max_ref_images:
                break

    amount, rate_snapshot = await quote_image_price(
        session,
        model_id=model.id,
        tier=body.tier,
        usage_multiplier=user.usage_multiplier,
    )
    job = await create_job(
        session,
        user_id=user.id,
        project_id=project.id,
        job_type="asset_image",
        target_id=str(clip.id),
        input_payload={
            "action": "clip_storyboard_grid",
            "clipId": str(clip.id),
            "episodeId": str(clip.episode_id),
            "episodeNumber": episode.number if episode is not None else 1,
            "clipIndex": clip.clip_index,
            "modelId": model.id,
            "tier": body.tier,
            "ratio": ratio,
            **({"referenceUrls": ref_urls} if ref_urls else {}),
        },
        step_total=4,
        step_label=f"片段 {clip.clip_index} 分镜宫格任务已排队",
        idempotency_key=f"clip_grid:{user.id}:{idempotency_key}" if idempotency_key else None,
    )
    await freeze_media_credits(
        session,
        user_id=user.id,
        business_type="image",
        business_id=job.id,
        model_id=model.id,
        amount=amount,
        rate_snapshot=rate_snapshot,
        reason=f"片段分镜宫格预冻结 (片段{clip.clip_index} · {model.id}/{body.tier})",
    )
    await session.commit()
    await execute_asset_image_job.kiq(str(job.id))
    return ApiResponse(data=ProjectJobAcceptedOut(project_id=project.id, job=JobOut.model_validate(job)))


@router.post(
    "/{project_id}/episodes/{episode_number}/compose",
    response_model=ApiResponse[ProjectJobAcceptedOut],
    status_code=202,
)
async def compose_project_episode(
    project_id: UUID,
    episode_number: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProjectJobAcceptedOut]:
    project = await get_owned_project(session, project_id=project_id, user_id=user.id)
    episode = await session.scalar(
        select(Episode).where(Episode.project_id == project.id, Episode.number == episode_number)
    )
    if episode is None:
        raise AppError(404, "episode_not_found", f"第 {episode_number} 集不存在")
    await _assert_no_active_episode_board_or_compose_job(
        session, project_id=project.id, episode=episode
    )

    clips = list(
        await session.scalars(
            select(StoryboardClip)
            .where(StoryboardClip.episode_id == episode.id)
            .order_by(StoryboardClip.clip_index)
        )
    )
    if not clips:
        raise AppError(400, "clips_required", "本集尚无分镜片段，无法合成")
    missing = [str(c.clip_index) for c in clips if not (c.video_key or c.video_url)]
    if missing:
        raise AppError(
            400,
            "clip_videos_incomplete",
            f"片段 {'、'.join(missing)} 尚未生成视频，请先完成全部片段生成后再合成本集",
        )

    await load_storage(session)

    # 本集 FFmpeg 合成免费（0 积分），直接入 media_broker 独立队列。
    job = await create_job(
        session,
        user_id=user.id,
        project_id=project.id,
        job_type="episode_compose",
        target_id=str(episode.id),
        input_payload={
            "episodeId": str(episode.id),
            "episodeNumber": episode.number,
            "clipCount": len(clips),
        },
        step_total=4,
        step_label=f"第 {episode.number} 集视频合成任务已排队",
    )
    await session.commit()
    await execute_episode_compose_job.kiq(str(job.id))
    return ApiResponse(data=ProjectJobAcceptedOut(project_id=project.id, job=JobOut.model_validate(job)))
