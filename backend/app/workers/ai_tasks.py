import asyncio
import tempfile
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from pydantic_ai import RunUsage
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models import Model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import undefer
from taskiq import Context, TaskiqDepends

from app.core.errors import AppError
from app.modules.canvas.generation import generate_canvas_text
from app.modules.canvas.service import (
    patch_canvas_node_error,
    patch_canvas_node_media,
    patch_canvas_node_text,
)
from app.modules.catalog.models import AiModel, AiProvider
from app.modules.credits.models import CreditReservation
from app.modules.credits.service import (
    charge_llm_usage,
    release_media_credits,
    settle_media_credits,
)
from app.modules.jobs.models import Job
from app.modules.jobs.service import (
    claim_job_lease,
    heartbeat_job_lease,
    publish_job_event,
    update_job_progress,
)
from app.modules.llm_engine.asset_gen import analyze_assets
from app.modules.llm_engine.provider import DEFAULT_TEXT_MODEL_ID, resolve_text_model
from app.modules.llm_engine.schema import ProjectSettings
from app.modules.llm_engine.script_gen import (
    Source,
    append_episode,
    generate_script,
    regenerate_episode,
)
from app.modules.llm_engine.storyboard_gen import (
    generate_new_clip_storyboard,
    regenerate_clip_storyboard,
    storyboard,
)
from app.modules.media_providers.cangyuan_image import (
    CangyuanImageAdapter,
    MediaProviderError,
    asset_aspect_ratio,
)
from app.modules.media_providers.cc_video import CcVideoAdapter
from app.modules.storage.media import (
    detect_image_format,
    download_public_media,
    download_to_file,
    format_exception_detail,
    probe_video_duration,
)
from app.modules.storage.oss import OssStorage, load_storage
from app.modules.studio.models import Episode, Project, ProjectAsset, StoryboardClip
from app.modules.studio.service import (
    append_asset_image_history,
    append_clip_video_history,
    apply_regenerated_clip,
    build_asset_result_from_db,
    build_script_result_from_db,
    persist_appended_episode,
    persist_extracted_assets,
    persist_generated_new_clip,
    persist_rewritten_episode,
    persist_script_result,
    persist_storyboard_result,
)
from app.workers.broker import WorkerRuntime, ai_broker

logger = structlog.get_logger(__name__)

_IMAGE_SEMAPHORES: dict[tuple[int, int], asyncio.Semaphore] = {}
_VIDEO_SEMAPHORES: dict[tuple[int, int], asyncio.Semaphore] = {}


def _get_image_semaphore(limit: int) -> asyncio.Semaphore:
    bounded = max(1, int(limit))
    key = (id(asyncio.get_running_loop()), bounded)
    sem = _IMAGE_SEMAPHORES.get(key)
    if sem is None:
        sem = asyncio.Semaphore(bounded)
        _IMAGE_SEMAPHORES[key] = sem
    return sem


def _get_video_semaphore(limit: int) -> asyncio.Semaphore:
    bounded = max(1, int(limit))
    key = (id(asyncio.get_running_loop()), bounded)
    sem = _VIDEO_SEMAPHORES.get(key)
    if sem is None:
        sem = asyncio.Semaphore(bounded)
        _VIDEO_SEMAPHORES[key] = sem
    return sem


def _format_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, AppError):
        return exc.code, exc.message
    if isinstance(exc, AgentRunError):
        status = getattr(exc, "status_code", None)
        head = f"模型调用失败 (HTTP {status})" if status else type(exc).__name__
        cause = exc.__cause__
        detail = f"{head}：{str(cause)[:1000]}" if cause else f"{head}：{str(exc)[:1000]}"
        return "llm_failed", detail
    return type(exc).__name__, str(exc)[:1000] or "任务执行失败"


async def run_llm_job_core(
    *,
    sessions: async_sessionmaker[AsyncSession],
    redis: Any,
    settings: Any,
    job_id: UUID,
    model_override: tuple[Model, str] | None = None,
) -> None:
    """
    执行单条 LLM 任务的核心状态机：
    - 租约抢占 + 30s 心跳续约
    - 共享 RunUsage 累加所有重试与分集 token
    - finally 必结算：无论成功还是中途报错，只要有 token 消耗一律按真实单价扣费（允许负余额）
    """
    claimed = await claim_job_lease(sessions, job_id)
    if claimed is None:
        return
    job, lease_token = claimed
    await publish_job_event(redis, settings, job)

    heartbeat = asyncio.create_task(heartbeat_job_lease(sessions, job_id, lease_token))
    run_usage = RunUsage()
    model_id = DEFAULT_TEXT_MODEL_ID

    async def on_progress(step_index: int, step_total: int, label: str, progress: int) -> None:
        await update_job_progress(
            sessions,
            redis,
            settings,
            job_id=job_id,
            step_index=step_index,
            step_total=step_total,
            step_label=label,
            progress=progress,
        )

    try:
        async with sessions() as session:
            payload = dict(job.input_payload or {})
            requested_model_id = (
                str(payload.get("modelId")).strip() if payload.get("modelId") else None
            )
            if model_override is not None:
                model, model_id = model_override
            else:
                model, model_id = await resolve_text_model(session, model_id=requested_model_id)

            if job.job_type == "canvas_text":
                if job.canvas_id is None or not job.target_id:
                    raise AppError(400, "canvas_target_missing", "画布文本任务缺少关联画布或节点 ID")
                generated_text = await generate_canvas_text(
                    model,
                    prompt=str(payload.get("prompt") or ""),
                    current_text=(
                        str(payload["currentText"])
                        if isinstance(payload.get("currentText"), str)
                        else None
                    ),
                    reference_texts=(
                        payload.get("referenceTexts")
                        if isinstance(payload.get("referenceTexts"), list)
                        else None
                    ),
                    reference_urls=(
                        payload.get("referenceUrls")
                        if isinstance(payload.get("referenceUrls"), list)
                        else None
                    ),
                    reference_images=(
                        payload.get("referenceImages")
                        if isinstance(payload.get("referenceImages"), list)
                        else None
                    ),
                    usage=run_usage,
                    on_progress=on_progress,
                )
                await patch_canvas_node_text(
                    session,
                    canvas_id=job.canvas_id,
                    node_id=job.target_id,
                    text=generated_text,
                    base_text=(
                        str(payload["currentText"])
                        if isinstance(payload.get("currentText"), str)
                        else None
                    ),
                    job_id=job_id,
                )
                result_payload: dict[str, Any] = {
                    "canvasId": str(job.canvas_id),
                    "nodeId": job.target_id,
                    "modelId": model_id,
                    "text": generated_text,
                }
            else:
                project = (
                    await session.scalar(select(Project).where(Project.id == job.project_id))
                    if job.project_id
                    else None
                )
                if project is None:
                    raise AppError(404, "project_not_found", "关联项目不存在")

                result_payload = {"projectId": str(project.id)}

                if job.job_type in ("script_generate", "script_regenerate"):
                    proj_settings = ProjectSettings.model_validate(project.settings)
                    source = Source.from_text(project.mode, project.source_text)  # type: ignore[arg-type]
                    generated = await generate_script(
                        model,
                        proj_settings,
                        source,
                        feedback=str(payload.get("feedback", "")),
                        usage=run_usage,
                        on_progress=on_progress,
                    )
                    await persist_script_result(
                        session,
                        project,
                        generated,
                        reset_downstream=(job.job_type == "script_regenerate"),
                    )
                    result_payload["episodeCount"] = len(generated.episodes)

                elif job.job_type == "episode_rewrite":
                    ep_num = int(payload["episodeNumber"])
                    script_result = await build_script_result_from_db(session, project)
                    source = (
                        Source.from_text(project.mode, project.source_text)  # type: ignore[arg-type]
                        if project.source_text.strip()
                        else None
                    )
                    rewritten = await regenerate_episode(
                        model,
                        script_result,
                        ep_num,
                        source=source,
                        feedback=str(payload.get("feedback", "")),
                        usage=run_usage,
                        on_progress=on_progress,
                    )
                    await persist_rewritten_episode(session, project, rewritten)
                    result_payload["episodeNumber"] = rewritten.number

                elif job.job_type == "episode_append":
                    script_result = await build_script_result_from_db(session, project)
                    source = (
                        Source.from_text(project.mode, project.source_text)  # type: ignore[arg-type]
                        if project.source_text.strip()
                        else None
                    )
                    updated = await append_episode(
                        model,
                        script_result,
                        source=source,
                        feedback=str(payload.get("feedback", "")),
                        usage=run_usage,
                        on_progress=on_progress,
                    )
                    appended = await persist_appended_episode(session, project, updated)
                    result_payload["episodeNumber"] = appended.number

                elif job.job_type == "assets_extract":
                    mode = str(payload.get("mode", "incremental"))
                    script_result = await build_script_result_from_db(session, project)
                    existing_assets = (
                        (
                            await build_asset_result_from_db(
                                session, project, include_variants=True
                            )
                        ).assets
                        if mode == "incremental"
                        else []
                    )
                    extracted = await analyze_assets(
                        model,
                        script_result,
                        existing=existing_assets,
                        usage=run_usage,
                        on_progress=on_progress,
                    )
                    saved = await persist_extracted_assets(
                        session,
                        project,
                        extracted,
                        preserve_edits=(mode == "incremental"),
                    )
                    result_payload["assetCount"] = len(saved)

                elif job.job_type == "storyboard_generate":
                    action = str(payload.get("action") or "episode")
                    if action == "clip_regenerate":
                        clip_uuid = UUID(str(payload["clipId"]))
                        clip_row = await session.scalar(
                            select(StoryboardClip).where(
                                StoryboardClip.id == clip_uuid,
                                StoryboardClip.project_id == project.id,
                            )
                        )
                        if clip_row is None:
                            raise AppError(404, "clip_not_found", "片段不存在")
                        ep_row = await session.scalar(
                            select(Episode).where(
                                Episode.id == clip_row.episode_id,
                                Episode.project_id == project.id,
                            )
                        )
                        if ep_row is None:
                            raise AppError(404, "episode_not_found", "关联分集不存在")
                        script_result = await build_script_result_from_db(session, project)
                        llm_ep = next(
                            (e for e in script_result.episodes if e.number == ep_row.number),
                            None,
                        )
                        if llm_ep is None:
                            raise AppError(
                                404, "episode_not_found", f"剧本里缺少第 {ep_row.number} 集"
                            )
                        asset_result = await build_asset_result_from_db(
                            session, project, include_variants=True
                        )
                        if not asset_result.assets:
                            raise AppError(
                                400, "assets_required", "请先识别并生成项目资产后再重生成分镜"
                            )

                        ep_clips = list(
                            await session.scalars(
                                select(StoryboardClip)
                                .where(StoryboardClip.episode_id == ep_row.id)
                                .order_by(StoryboardClip.clip_index)
                            )
                        )
                        pos = next((i for i, c in enumerate(ep_clips) if c.id == clip_row.id), -1)
                        prev_row = ep_clips[pos - 1] if pos > 0 else None
                        next_row = ep_clips[pos + 1] if 0 <= pos < len(ep_clips) - 1 else None
                        prev_ctx = (
                            {
                                "clipIndex": prev_row.clip_index,
                                "blocking": prev_row.blocking or "",
                                "promptExcerpt": (prev_row.prompt or "")[:360],
                            }
                            if prev_row is not None
                            else None
                        )
                        next_ctx = (
                            {
                                "clipIndex": next_row.clip_index,
                                "blocking": next_row.blocking or "",
                                "promptExcerpt": (next_row.prompt or "")[:360],
                            }
                            if next_row is not None
                            else None
                        )
                        beat_tuple = (
                            (int(clip_row.beats[0]), int(clip_row.beats[1]))
                            if isinstance(clip_row.beats, list) and len(clip_row.beats) == 2
                            else None
                        )
                        refresh_refs = bool(payload.get("refreshReferences", True))
                        spec = await regenerate_clip_storyboard(
                            model,
                            script=script_result,
                            episode=llm_ep,
                            assets=asset_result,
                            clip_index=clip_row.clip_index,
                            clip_beats=beat_tuple,
                            duration_seconds=clip_row.duration_seconds,
                            current_prompt=clip_row.prompt or "",
                            current_references=list(clip_row.references or []),
                            refresh_references=refresh_refs,
                            feedback=str(payload.get("feedback", "")),
                            prev_clip=prev_ctx,
                            next_clip=next_ctx,
                            usage=run_usage,
                            on_progress=on_progress,
                        )
                        updated = await apply_regenerated_clip(
                            session,
                            project=project,
                            clip_id=clip_row.id,
                            prompt_text=spec.prompt,
                            blocking=spec.blocking,
                            cuts=[c.model_dump() for c in spec.cuts] if spec.cuts else None,
                            raw_references=(
                                [r.model_dump() for r in spec.references] if refresh_refs else None
                            ),
                            refresh_references=refresh_refs,
                        )
                        result_payload["episodeNumber"] = ep_row.number
                        result_payload["clipId"] = str(updated.id)
                        result_payload["clipIndex"] = updated.clip_index

                    elif action == "clip_create":
                        ep_num = int(payload["episodeNumber"])
                        duration_sec = int(payload.get("durationSeconds") or 10)
                        insert_after_raw = payload.get("insertAfterClipId")
                        insert_after_id = UUID(str(insert_after_raw)) if insert_after_raw else None

                        ep_row = await session.scalar(
                            select(Episode).where(
                                Episode.project_id == project.id,
                                Episode.number == ep_num,
                            )
                        )
                        if ep_row is None:
                            raise AppError(404, "episode_not_found", f"第 {ep_num} 集不存在")
                        script_result = await build_script_result_from_db(session, project)
                        llm_ep = next(
                            (e for e in script_result.episodes if e.number == ep_num), None
                        )
                        if llm_ep is None:
                            raise AppError(404, "episode_not_found", f"剧本里缺少第 {ep_num} 集")
                        asset_result = await build_asset_result_from_db(
                            session, project, include_variants=True
                        )
                        if not asset_result.assets:
                            raise AppError(
                                400, "assets_required", "请先识别并生成项目资产后再新增片段"
                            )

                        ep_clips = list(
                            await session.scalars(
                                select(StoryboardClip)
                                .where(StoryboardClip.episode_id == ep_row.id)
                                .order_by(StoryboardClip.clip_index)
                            )
                        )
                        insert_pos = len(ep_clips)
                        if insert_after_id is not None:
                            anchor = next(
                                (i for i, c in enumerate(ep_clips) if c.id == insert_after_id),
                                None,
                            )
                            if anchor is not None:
                                insert_pos = anchor + 1
                        prev_row = ep_clips[insert_pos - 1] if insert_pos > 0 else None
                        next_row = ep_clips[insert_pos] if insert_pos < len(ep_clips) else None
                        prev_ctx = (
                            {
                                "clipIndex": prev_row.clip_index,
                                "blocking": prev_row.blocking or "",
                                "promptExcerpt": (prev_row.prompt or "")[:360],
                            }
                            if prev_row is not None
                            else None
                        )
                        next_ctx = (
                            {
                                "clipIndex": next_row.clip_index,
                                "blocking": next_row.blocking or "",
                                "promptExcerpt": (next_row.prompt or "")[:360],
                            }
                            if next_row is not None
                            else None
                        )
                        spec = await generate_new_clip_storyboard(
                            model,
                            script=script_result,
                            episode=llm_ep,
                            assets=asset_result,
                            duration_seconds=duration_sec,
                            feedback=str(payload.get("feedback", "")),
                            prev_clip=prev_ctx,
                            next_clip=next_ctx,
                            usage=run_usage,
                            on_progress=on_progress,
                        )
                        created = await persist_generated_new_clip(
                            session,
                            project=project,
                            episode_number=ep_num,
                            duration_seconds=duration_sec,
                            prompt_text=spec.prompt,
                            blocking=spec.blocking,
                            cuts=[c.model_dump() for c in spec.cuts] if spec.cuts else None,
                            raw_references=[r.model_dump() for r in spec.references],
                            insert_after_clip_id=insert_after_id,
                        )
                        result_payload["episodeNumber"] = ep_num
                        result_payload["clipId"] = str(created.id)
                        result_payload["clipIndex"] = created.clip_index

                    else:
                        ep_num = payload.get("episodeNumber")
                        script_result = await build_script_result_from_db(session, project)
                        asset_result = await build_asset_result_from_db(
                            session, project, include_variants=True
                        )
                        if not asset_result.assets:
                            raise AppError(
                                400, "assets_required", "请先识别并生成项目资产后再生成分镜"
                            )
                        board = await storyboard(
                            model,
                            script_result,
                            asset_result,
                            only_episode=int(ep_num) if ep_num is not None else None,
                            feedback=str(payload.get("feedback", "")),
                            usage=run_usage,
                            on_progress=on_progress,
                        )
                        await persist_storyboard_result(session, project, board)
                        result_payload["episodes"] = [item.number for item in board.episodes]

                else:
                    raise AppError(400, "unsupported_job_type", f"不支持的 LLM 任务类型：{job.job_type}")

            db_job = await session.scalar(select(Job).where(Job.id == job_id))
            if db_job is not None:
                db_job.status = "succeeded"
                db_job.progress = 100
                db_job.step_index = db_job.step_total
                db_job.step_label = "已完成"
                db_job.result_payload = result_payload
                db_job.finished_at = datetime.now(UTC)
                db_job.lease_token = None
            await session.commit()
            if db_job is not None:
                await session.refresh(db_job)
                await publish_job_event(redis, settings, db_job)

    except Exception as exc:
        code, message = _format_error(exc)
        logger.warning("llm_job_failed", job_id=str(job_id), code=code, error=message)
        async with sessions() as session:
            if job.job_type == "canvas_text" and job.canvas_id and job.target_id:
                await patch_canvas_node_error(
                    session,
                    canvas_id=job.canvas_id,
                    node_id=job.target_id,
                    error_message=message,
                    job_id=job_id,
                )
            db_job = await session.scalar(select(Job).where(Job.id == job_id))
            if db_job is not None:
                db_job.status = "failed"
                db_job.error_code = code
                db_job.error_message = message
                db_job.finished_at = datetime.now(UTC)
                db_job.lease_token = None
            await session.commit()
            if db_job is not None:
                await session.refresh(db_job)
                await publish_job_event(redis, settings, db_job)
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass

        # 只要 DeepSeek 消耗了任何 token，无论最终成功还是中途失败，全额按实计费（零垫资）。
        if run_usage.input_tokens > 0 or run_usage.output_tokens > 0:
            try:
                async with sessions() as session:
                    ledger = await charge_llm_usage(
                        session,
                        user_id=job.user_id,
                        model_id=model_id,
                        job_id=job.id,
                        input_tokens=run_usage.input_tokens,
                        cache_read_tokens=run_usage.cache_read_tokens,
                        output_tokens=run_usage.output_tokens,
                        idempotency_key=f"llm:{job.id}",
                        reason=f"LLM 任务消耗 ({job.job_type})",
                    )
                    db_job = await session.scalar(select(Job).where(Job.id == job_id))
                    if db_job is not None and ledger is not None:
                        db_job.usage_summary = ledger.token_usage
                    await session.commit()
            except Exception:
                logger.exception("llm_postpaid_charge_failed", job_id=str(job_id))


@ai_broker.task(task_name="framedrama.ai.execute_llm_job")
async def execute_llm_job(
    job_id: str,
    context: Context = TaskiqDepends(),
) -> None:
    runtime: WorkerRuntime = context.state.runtime
    await run_llm_job_core(
        sessions=runtime.sessions,
        redis=runtime.redis,
        settings=runtime.settings,
        job_id=UUID(job_id),
    )


async def run_asset_image_job_core(
    *,
    sessions: async_sessionmaker[AsyncSession],
    redis: Any,
    settings: Any,
    job_id: UUID,
    adapter: CangyuanImageAdapter | None = None,
    storage_loader: Callable[[AsyncSession], Awaitable[OssStorage]] = load_storage,
    downloader: Callable[[str], Awaitable[bytes]] = download_public_media,
    poll_interval_seconds: float = 5.0,
    max_wait_seconds: float = 600.0,
    concurrency_semaphore: asyncio.Semaphore | None = None,
) -> None:
    """
    沧元资产生图核心状态机：
    - 并发信号量限流（默认 4 并发），排队阶段不占用租约与心跳
    - 租约抢占 + 心跳续约
    - 异步提交后立即落库 provider_task_id，重启恢复直接续查不重复扣费
    - 成功转存 OSS 后结算冻结积分；明确拒绝/失败释放积分；状态不明标记 review 保留冻结
    """
    sem = concurrency_semaphore or _get_image_semaphore(getattr(settings, "image_concurrency", 4))
    async with sem:
        await _execute_asset_image_under_slot(
            sessions=sessions,
            redis=redis,
            settings=settings,
            job_id=job_id,
            adapter=adapter,
            storage_loader=storage_loader,
            downloader=downloader,
            poll_interval_seconds=poll_interval_seconds,
            max_wait_seconds=max_wait_seconds,
        )


async def _execute_asset_image_under_slot(
    *,
    sessions: async_sessionmaker[AsyncSession],
    redis: Any,
    settings: Any,
    job_id: UUID,
    adapter: CangyuanImageAdapter | None = None,
    storage_loader: Callable[[AsyncSession], Awaitable[OssStorage]] = load_storage,
    downloader: Callable[[str], Awaitable[bytes]] = download_public_media,
    poll_interval_seconds: float = 5.0,
    max_wait_seconds: float = 600.0,
) -> None:
    claimed = await claim_job_lease(sessions, job_id)
    if claimed is None:
        return
    job, lease_token = claimed
    await publish_job_event(redis, settings, job)

    heartbeat = asyncio.create_task(heartbeat_job_lease(sessions, job_id, lease_token))
    client_adapter = adapter or CangyuanImageAdapter()
    payload_in = dict(job.input_payload or {})
    is_canvas = job.job_type == "canvas_image"
    asset_id = None if is_canvas else UUID(str(job.target_id or payload_in["assetId"]))
    canvas_node_id = str(job.target_id or payload_in.get("nodeId") or "") if is_canvas else ""

    async def set_progress(step_index: int, label: str, progress: int) -> None:
        await update_job_progress(
            sessions,
            redis,
            settings,
            job_id=job_id,
            step_index=step_index,
            step_total=4,
            step_label=label,
            progress=progress,
        )

    try:
        async with sessions() as session:
            if is_canvas:
                if job.canvas_id is None or not canvas_node_id:
                    raise MediaProviderError(
                        "canvas_target_missing", "画布生图缺少关联画布或节点 ID", rejected=True
                    )
                model_id = str(payload_in.get("modelId") or "gpt-image-2")
                tier = str(payload_in.get("tier") or "1k")
                ratio = str(payload_in.get("ratio") or "16:9")
                prompt = str(payload_in.get("prompt") or "").strip()
            else:
                asset = await session.scalar(select(ProjectAsset).where(ProjectAsset.id == asset_id))
                if asset is None:
                    raise MediaProviderError("asset_not_found", "关联资产不存在", rejected=True)
                model_id = str(payload_in.get("modelId") or "gpt-image-2")
                tier = str(payload_in.get("tier") or "1k")
                ratio = str(payload_in.get("ratio") or asset_aspect_ratio(asset.kind))
                prompt = str(payload_in.get("prompt") or asset.prompt or "").strip()
            if not prompt:
                raise MediaProviderError("prompt_missing", "提示词为空，无法生图", rejected=True)
            reference_urls = [
                str(u).strip() for u in (payload_in.get("referenceUrls") or []) if str(u).strip()
            ]

            model = await session.scalar(select(AiModel).where(AiModel.id == model_id))
            if model is None:
                raise MediaProviderError("model_not_found", f"图片模型 {model_id} 不存在", rejected=True)
            max_ref_images = int(model.capabilities.get("maxReferenceImages") or 9)
            if len(reference_urls) > max_ref_images:
                raise MediaProviderError(
                    "reference_images_exceed_limit",
                    (
                        f"{model.display_name} 最多支持 {max_ref_images} 张参考图，"
                        f"当前为 {len(reference_urls)} 张"
                    ),
                    rejected=True,
                )
            provider = await session.scalar(
                select(AiProvider)
                .options(undefer(AiProvider.api_key))
                .where(AiProvider.id == model.provider_id)
            )
            if provider is None or not provider.api_key.strip():
                raise MediaProviderError(
                    "provider_not_configured", "尚未配置沧元图片供应商 API Key", rejected=True
                )

            storage = await storage_loader(session)
            provider_base_url = provider.base_url
            provider_api_key = provider.api_key
            provider_auth_type = provider.auth_type
            provider_auth_header = provider.auth_header
            timeout_ms = int(provider.configuration.get("timeoutMs", 30000))
            timeout_seconds = max(5.0, min(timeout_ms / 1000.0, 120.0))
            req_payload, submit_endpoint = client_adapter.build_payload(
                upstream_model_id=model.upstream_model_id,
                prompt=prompt,
                tier=tier,
                ratio=ratio,
                quality=str(model.configuration.get("quality") or "high"),
                series=model.configuration.get("series"),
                reference_urls=reference_urls,
            )
            poll_endpoint = "generations"
            existing_task_id = job.provider_task_id

        if not existing_task_id:
            submit_label = (
                f"正在提交图生图任务（{model_id} · {tier} · {ratio} · {len(reference_urls)} 张参考图）..."
                if reference_urls
                else f"正在向图片引擎提交任务（{model_id} · {tier} · {ratio}）..."
            )
            await set_progress(1, submit_label, 15)
            submit_result = await client_adapter.submit(
                base_url=provider_base_url,
                api_key=provider_api_key,
                auth_type=provider_auth_type,
                auth_header=provider_auth_header,
                endpoint=submit_endpoint,
                payload=req_payload,
                timeout_seconds=timeout_seconds,
            )
            if submit_result.status == "failed":
                raise MediaProviderError("provider_failed", submit_result.message, rejected=True)
            if submit_result.task_id:
                existing_task_id = submit_result.task_id
                async with sessions() as session:
                    db_job = await session.scalar(select(Job).where(Job.id == job_id))
                    if db_job is not None:
                        db_job.provider_task_id = existing_task_id
                        if submit_result.status != "completed":
                            db_job.status = "polling"
                        await session.commit()
            elif submit_result.status != "completed":
                raise MediaProviderError(
                    "submissionUnknown",
                    "图片供应商未返回任务编号，请人工核对后再决定是否退款",
                    uncertain=True,
                )
            result = submit_result
        else:
            result = await client_adapter.query(
                base_url=provider_base_url,
                api_key=provider_api_key,
                auth_type=provider_auth_type,
                auth_header=provider_auth_header,
                endpoint=poll_endpoint,
                task_id=existing_task_id,
                timeout_seconds=timeout_seconds,
            )

        elapsed = 0.0
        transient_errors = 0
        poll_count = 0
        while result.status != "completed":
            if result.status == "failed":
                raise MediaProviderError("provider_failed", result.message, rejected=True)
            if not existing_task_id:
                raise MediaProviderError(
                    "submissionUnknown", "缺少供应商任务编号，转人工核对", uncertain=True
                )
            if elapsed >= max_wait_seconds:
                raise MediaProviderError(
                    "poll_timeout", "图片生成轮询超时，待人工核对供应商结果", uncertain=True
                )

            poll_count += 1
            pct = min(75, 25 + poll_count * 6)
            await set_progress(2, "图片生成中，正在等待结果返回...", pct)
            if poll_interval_seconds > 0:
                await asyncio.sleep(poll_interval_seconds)
            elapsed += max(poll_interval_seconds, 0.01)

            try:
                result = await client_adapter.query(
                    base_url=provider_base_url,
                    api_key=provider_api_key,
                    auth_type=provider_auth_type,
                    auth_header=provider_auth_header,
                    endpoint=poll_endpoint,
                    task_id=existing_task_id,
                    timeout_seconds=timeout_seconds,
                )
                transient_errors = 0
            except MediaProviderError as poll_exc:
                if poll_exc.rejected:
                    raise
                transient_errors += 1
                if transient_errors >= 3:
                    raise MediaProviderError(
                        "poll_failed",
                        f"图片状态查询连续失败：{poll_exc.message}",
                        uncertain=True,
                    ) from None

        if not result.url:
            raise MediaProviderError("result_url_missing", "图片生成完成但未返回下载地址", uncertain=True)

        await set_progress(3, "正在将成图转存至阿里云 OSS...", 85)
        try:
            image_bytes = await downloader(result.url)
            ext, mime_type = detect_image_format(image_bytes)
            key = storage.make_key(job.user_id, "images", f"{job.id}.{ext}")
            await asyncio.to_thread(storage.put_bytes, key, image_bytes, mime_type)
            public_url = storage.public_url(key)
        except Exception as transfer_exc:
            async with sessions() as session:
                db_job = await session.scalar(select(Job).where(Job.id == job_id))
                if db_job is not None:
                    db_job.result_payload = {
                        **(db_job.result_payload or {}),
                        "upstreamUrl": result.url,
                    }
                    await session.commit()
            raise MediaProviderError(
                "oss_transfer_failed",
                f"供应商已出图，但转存阿里云 OSS 失败：{format_exception_detail(transfer_exc)}",
                uncertain=True,
            ) from None

        async with sessions() as session:
            reservation = await session.scalar(
                select(CreditReservation).where(
                    CreditReservation.business_type == "image",
                    CreditReservation.business_id == job_id,
                )
            )
            if reservation is not None:
                await settle_media_credits(
                    session,
                    reservation_id=reservation.id,
                    reason=(
                        f"画布生图完成结算 ({model_id}/{tier})"
                        if is_canvas
                        else f"资产生图完成结算 ({model_id}/{tier})"
                    ),
                )
            if is_canvas and job.canvas_id is not None:
                await patch_canvas_node_media(
                    session,
                    canvas_id=job.canvas_id,
                    node_id=canvas_node_id,
                    media={
                        "url": public_url,
                        "key": key,
                        "name": f"{model_id}.{ext}",
                        "modelId": model_id,
                    },
                    job_id=job_id,
                )
            elif asset_id is not None:
                db_asset = await session.scalar(select(ProjectAsset).where(ProjectAsset.id == asset_id))
                if db_asset is not None:
                    db_asset.image_key = key
                    db_asset.image_url = public_url
                    db_asset.image_model_id = model_id
                    db_asset.image_tier = tier
                    db_asset.image_status = "ready"
                    db_asset.last_job_id = job_id
                    append_asset_image_history(
                        db_asset,
                        url=public_url,
                        key=key,
                        source="ai",
                        job_id=job_id,
                        model_id=model_id,
                        tier=tier,
                        ratio=ratio,
                    )
            db_job = await session.scalar(select(Job).where(Job.id == job_id))
            if db_job is not None:
                db_job.status = "succeeded"
                db_job.progress = 100
                db_job.step_index = 4
                db_job.step_total = 4
                db_job.step_label = "画布图片生成完成" if is_canvas else "资产形象生成完成"
                db_job.result_payload = (
                    {
                        "canvasId": str(job.canvas_id) if job.canvas_id else None,
                        "nodeId": canvas_node_id,
                        "imageUrl": public_url,
                        "imageKey": key,
                        "modelId": model_id,
                        "tier": tier,
                        "ratio": ratio,
                    }
                    if is_canvas
                    else {
                        "projectId": str(job.project_id) if job.project_id else None,
                        "assetId": str(asset_id),
                        "imageUrl": public_url,
                        "imageKey": key,
                        "modelId": model_id,
                        "tier": tier,
                        "ratio": ratio,
                    }
                )
                db_job.finished_at = datetime.now(UTC)
                db_job.lease_token = None
            await session.commit()
            if db_job is not None:
                await session.refresh(db_job)
                await publish_job_event(redis, settings, db_job)

    except Exception as exc:
        is_uncertain = isinstance(exc, MediaProviderError) and exc.uncertain
        code = exc.code if isinstance(exc, (AppError, MediaProviderError)) else type(exc).__name__
        message = (
            exc.message
            if isinstance(exc, (AppError, MediaProviderError))
            else (str(exc)[:1000] or ("画布生图失败" if is_canvas else "资产生图失败"))
        )
        logger.warning(
            "asset_image_job_failed",
            job_id=str(job_id),
            code=code,
            uncertain=is_uncertain,
            error=message,
        )
        async with sessions() as session:
            reservation = await session.scalar(
                select(CreditReservation).where(
                    CreditReservation.business_type == "image",
                    CreditReservation.business_id == job_id,
                )
            )
            if reservation is not None and not is_uncertain and reservation.status == "frozen":
                await release_media_credits(
                    session,
                    reservation_id=reservation.id,
                    reason=(
                        f"画布生图失败退还冻结积分 ({code})"
                        if is_canvas
                        else f"资产生图失败退还冻结积分 ({code})"
                    ),
                )
            if is_canvas and job.canvas_id is not None and canvas_node_id:
                await patch_canvas_node_error(
                    session,
                    canvas_id=job.canvas_id,
                    node_id=canvas_node_id,
                    error_message=message,
                    job_id=job_id,
                )
            elif asset_id is not None:
                db_asset = await session.scalar(select(ProjectAsset).where(ProjectAsset.id == asset_id))
                if db_asset is not None:
                    db_asset.image_status = "ready" if db_asset.image_url else "failed"
                    db_asset.last_job_id = job_id
            db_job = await session.scalar(select(Job).where(Job.id == job_id))
            if db_job is not None:
                db_job.status = "review" if is_uncertain else "failed"
                db_job.error_code = code
                db_job.error_message = message
                db_job.finished_at = datetime.now(UTC)
                db_job.lease_token = None
            await session.commit()
            if db_job is not None:
                await session.refresh(db_job)
                await publish_job_event(redis, settings, db_job)
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass


@ai_broker.task(task_name="framedrama.ai.execute_asset_image_job")
async def execute_asset_image_job(
    job_id: str,
    context: Context = TaskiqDepends(),
) -> None:
    runtime: WorkerRuntime = context.state.runtime
    await run_asset_image_job_core(
        sessions=runtime.sessions,
        redis=runtime.redis,
        settings=runtime.settings,
        job_id=UUID(job_id),
    )


async def run_clip_video_job_core(
    *,
    sessions: async_sessionmaker[AsyncSession],
    redis: Any,
    settings: Any,
    job_id: UUID,
    adapter: CcVideoAdapter | None = None,
    storage_loader: Callable[[AsyncSession], Awaitable[OssStorage]] = load_storage,
    file_downloader: Callable[[str, Path], Awaitable[int]] = download_to_file,
    duration_prober: Callable[..., Awaitable[float]] = probe_video_duration,
    poll_interval_seconds: float = 20.0,
    enforce_min_interval: bool = True,
    max_wait_seconds: float = 1200.0,
    concurrency_semaphore: asyncio.Semaphore | None = None,
) -> None:
    """
    CC 片段视频生成核心状态机（Seedance 2.0 / 2.5）：
    - 独立视频并发信号量限流（默认 3 并发），排队阶段不占租约与心跳
    - 租约抢占 + 30s 心跳续约
    - 提交后立即落库 provider_task_id，最小 20s 间隔轮询进度
    - 下载至临时目录 -> ffprobe 校验 -> 上传阿里云 OSS -> 结算冻结积分
    - 明确失败退还冻结积分；状态不明/转存异常保留冻结并转 review
    """
    sem = concurrency_semaphore or _get_video_semaphore(getattr(settings, "video_concurrency", 3))
    async with sem:
        await _execute_clip_video_under_slot(
            sessions=sessions,
            redis=redis,
            settings=settings,
            job_id=job_id,
            adapter=adapter,
            storage_loader=storage_loader,
            file_downloader=file_downloader,
            duration_prober=duration_prober,
            poll_interval_seconds=poll_interval_seconds,
            enforce_min_interval=enforce_min_interval,
            max_wait_seconds=max_wait_seconds,
        )


async def _execute_clip_video_under_slot(
    *,
    sessions: async_sessionmaker[AsyncSession],
    redis: Any,
    settings: Any,
    job_id: UUID,
    adapter: CcVideoAdapter | None = None,
    storage_loader: Callable[[AsyncSession], Awaitable[OssStorage]] = load_storage,
    file_downloader: Callable[[str, Path], Awaitable[int]] = download_to_file,
    duration_prober: Callable[..., Awaitable[float]] = probe_video_duration,
    poll_interval_seconds: float = 20.0,
    enforce_min_interval: bool = True,
    max_wait_seconds: float = 1200.0,
) -> None:
    claimed = await claim_job_lease(sessions, job_id)
    if claimed is None:
        return
    job, lease_token = claimed
    await publish_job_event(redis, settings, job)

    heartbeat = asyncio.create_task(heartbeat_job_lease(sessions, job_id, lease_token))
    client_adapter = adapter or CcVideoAdapter()
    effective_interval = (
        max(poll_interval_seconds, float(client_adapter.minimum_poll_interval))
        if enforce_min_interval
        else max(0.0, poll_interval_seconds)
    )
    payload_in = dict(job.input_payload or {})
    is_canvas = job.job_type == "canvas_video"
    clip_id = None if is_canvas else UUID(str(job.target_id or payload_in["clipId"]))
    canvas_node_id = str(job.target_id or payload_in.get("nodeId") or "") if is_canvas else ""

    async def set_progress(step_index: int, label: str, progress: int) -> None:
        await update_job_progress(
            sessions,
            redis,
            settings,
            job_id=job_id,
            step_index=step_index,
            step_total=4,
            step_label=label,
            progress=progress,
        )

    try:
        async with sessions() as session:
            if is_canvas:
                if job.canvas_id is None or not canvas_node_id:
                    raise MediaProviderError(
                        "canvas_target_missing", "画布生视频缺少关联画布或节点 ID", rejected=True
                    )
                model_id = str(payload_in.get("modelId") or "seedance-2.0")
                resolution = str(payload_in.get("resolution") or "720p")
                ratio = str(payload_in.get("ratio") or "16:9")
                duration_seconds = int(payload_in.get("durationSeconds") or 5)
                prompt = str(payload_in.get("prompt") or "").strip()
            else:
                clip = await session.scalar(select(StoryboardClip).where(StoryboardClip.id == clip_id))
                if clip is None:
                    raise MediaProviderError("clip_not_found", "关联分镜片段不存在", rejected=True)
                model_id = str(payload_in.get("modelId") or "seedance-2.0")
                resolution = str(payload_in.get("resolution") or "720p")
                ratio = str(payload_in.get("ratio") or "16:9")
                duration_seconds = int(payload_in.get("durationSeconds") or clip.duration_seconds)
                prompt = str(payload_in.get("prompt") or clip.prompt or "").strip()
            reference_urls = [str(u) for u in (payload_in.get("referenceUrls") or []) if str(u).strip()]
            reference_video_urls = [
                str(u) for u in (payload_in.get("referenceVideoUrls") or []) if str(u).strip()
            ]
            reference_audio_urls = [
                str(u) for u in (payload_in.get("referenceAudioUrls") or []) if str(u).strip()
            ]
            if not prompt:
                raise MediaProviderError("prompt_missing", "提示词为空，无法生成视频", rejected=True)

            model = await session.scalar(select(AiModel).where(AiModel.id == model_id))
            if model is None:
                raise MediaProviderError("model_not_found", f"视频模型 {model_id} 不存在", rejected=True)
            provider = await session.scalar(
                select(AiProvider)
                .options(undefer(AiProvider.api_key))
                .where(AiProvider.id == model.provider_id)
            )
            if provider is None or not provider.api_key.strip():
                raise MediaProviderError(
                    "provider_not_configured", "尚未配置 CC 视频供应商 API Key", rejected=True
                )

            storage = await storage_loader(session)
            provider_base_url = provider.base_url
            provider_api_key = provider.api_key
            provider_auth_type = provider.auth_type
            provider_auth_header = provider.auth_header
            timeout_ms = int(provider.configuration.get("timeoutMs", 30000))
            timeout_seconds = max(5.0, min(timeout_ms / 1000.0, 120.0))
            submit_timeout_seconds = max(timeout_seconds, 120.0)
            req_payload = client_adapter.build_payload(
                upstream_model_id=model.upstream_model_id,
                prompt=prompt,
                reference_urls=reference_urls,
                reference_video_urls=reference_video_urls,
                reference_audio_urls=reference_audio_urls,
                ratio=ratio,
                resolution=resolution,
                duration=duration_seconds,
                parameter_bindings=model.parameter_bindings,
            )
            existing_task_id = job.provider_task_id

        if not existing_task_id:
            await set_progress(
                1, f"正在提交视频生成任务（{model_id} · {duration_seconds}s · {resolution}）...", 10
            )
            submit_result = await client_adapter.submit(
                base_url=provider_base_url,
                api_key=provider_api_key,
                auth_type=provider_auth_type,
                auth_header=provider_auth_header,
                payload=req_payload,
                timeout_seconds=submit_timeout_seconds,
            )
            if submit_result.status == "failed":
                raise MediaProviderError(
                    "provider_failed", submit_result.message or "视频任务被供应商拒绝", rejected=True
                )
            if submit_result.task_id:
                existing_task_id = submit_result.task_id
                async with sessions() as session:
                    db_job = await session.scalar(select(Job).where(Job.id == job_id))
                    if db_job is not None:
                        db_job.provider_task_id = existing_task_id
                        if submit_result.status != "completed":
                            db_job.status = "polling"
                        await session.commit()
            elif submit_result.status != "completed":
                raise MediaProviderError(
                    "submissionUnknown",
                    "视频供应商未返回任务编号，请人工核对后再决定是否退款",
                    uncertain=True,
                )
            result = submit_result
        else:
            result = await client_adapter.query(
                base_url=provider_base_url,
                api_key=provider_api_key,
                auth_type=provider_auth_type,
                auth_header=provider_auth_header,
                task_id=existing_task_id,
                timeout_seconds=timeout_seconds,
            )

        elapsed = 0.0
        transient_errors = 0
        poll_count = 0
        while result.status != "completed":
            if result.status == "failed":
                raise MediaProviderError(
                    "provider_failed", result.message or "视频生成失败", rejected=True
                )
            if not existing_task_id:
                raise MediaProviderError(
                    "submissionUnknown", "缺少供应商任务编号，转人工核对", uncertain=True
                )
            if elapsed >= max_wait_seconds:
                raise MediaProviderError(
                    "poll_timeout", "视频生成轮询超时，待人工核对供应商结果", uncertain=True
                )

            poll_count += 1
            mapped_pct = (
                20 + int(result.progress * 0.58)
                if result.progress > 0
                else min(76, 18 + poll_count * 4)
            )
            label = (
                f"视频渲染中（供应商进度 {result.progress}%）..."
                if result.progress > 0
                else "视频渲染中，等待供应商返回成片..."
            )
            await set_progress(2, label, mapped_pct)
            if effective_interval > 0:
                await asyncio.sleep(effective_interval)
            elapsed += max(effective_interval, 0.01)

            try:
                result = await client_adapter.query(
                    base_url=provider_base_url,
                    api_key=provider_api_key,
                    auth_type=provider_auth_type,
                    auth_header=provider_auth_header,
                    task_id=existing_task_id,
                    timeout_seconds=timeout_seconds,
                )
                transient_errors = 0
            except MediaProviderError as poll_exc:
                if poll_exc.rejected:
                    raise
                transient_errors += 1
                if transient_errors >= 3:
                    raise MediaProviderError(
                        "poll_failed",
                        f"视频状态查询连续失败：{poll_exc.message}",
                        uncertain=True,
                    ) from None

        if not result.url:
            raise MediaProviderError("result_url_missing", "视频生成完成但未返回下载地址", uncertain=True)

        await set_progress(3, "正在校验成片并转存至阿里云 OSS...", 85)
        try:
            with tempfile.TemporaryDirectory(prefix="framedrama_vid_") as tmp_dir:
                local_path = Path(tmp_dir) / f"{job.id}.mp4"
                await file_downloader(result.url, local_path)
                actual_duration = await duration_prober(
                    local_path, ffprobe_path=getattr(settings, "ffprobe_path", "ffprobe")
                )
                key = storage.make_key(job.user_id, "videos", f"{job.id}.mp4")
                await asyncio.to_thread(storage.put_file, key, str(local_path), "video/mp4")
                public_url = storage.public_url(key)
        except Exception as transfer_exc:
            async with sessions() as session:
                db_job = await session.scalar(select(Job).where(Job.id == job_id))
                if db_job is not None:
                    db_job.result_payload = {
                        **(db_job.result_payload or {}),
                        "upstreamUrl": result.url,
                    }
                    await session.commit()
            raise MediaProviderError(
                "oss_transfer_failed",
                f"视频已生成，但校验或转存阿里云 OSS 失败：{format_exception_detail(transfer_exc)}",
                uncertain=True,
            ) from None

        async with sessions() as session:
            reservation = await session.scalar(
                select(CreditReservation).where(
                    CreditReservation.business_type == "video",
                    CreditReservation.business_id == job_id,
                )
            )
            if reservation is not None:
                await settle_media_credits(
                    session,
                    reservation_id=reservation.id,
                    reason=(
                        f"画布视频完成结算 ({model_id}/{duration_seconds}s)"
                        if is_canvas
                        else f"片段视频完成结算 ({model_id}/{duration_seconds}s)"
                    ),
                )
            if is_canvas and job.canvas_id is not None:
                await patch_canvas_node_media(
                    session,
                    canvas_id=job.canvas_id,
                    node_id=canvas_node_id,
                    media={
                        "url": public_url,
                        "key": key,
                        "name": f"{model_id}.mp4",
                        "modelId": model_id,
                    },
                    job_id=job_id,
                )
            elif clip_id is not None:
                db_clip = await session.scalar(select(StoryboardClip).where(StoryboardClip.id == clip_id))
                if db_clip is not None:
                    db_clip.video_key = key
                    db_clip.video_url = public_url
                    db_clip.video_model_id = model_id
                    db_clip.video_status = "ready"
                    db_clip.last_job_id = job_id
                    append_clip_video_history(
                        db_clip,
                        url=public_url,
                        key=key,
                        source="ai",
                        job_id=job_id,
                        model_id=model_id,
                        resolution=resolution,
                        ratio=ratio,
                        duration=actual_duration,
                    )
            db_job = await session.scalar(select(Job).where(Job.id == job_id))
            if db_job is not None:
                db_job.status = "succeeded"
                db_job.progress = 100
                db_job.step_index = 4
                db_job.step_total = 4
                db_job.step_label = "画布视频生成完成" if is_canvas else "片段视频生成完成"
                db_job.result_payload = (
                    {
                        "canvasId": str(job.canvas_id) if job.canvas_id else None,
                        "nodeId": canvas_node_id,
                        "videoUrl": public_url,
                        "videoKey": key,
                        "duration": actual_duration,
                        "modelId": model_id,
                        "resolution": resolution,
                        "ratio": ratio,
                    }
                    if is_canvas
                    else {
                        "projectId": str(job.project_id) if job.project_id else None,
                        "clipId": str(clip_id),
                        "videoUrl": public_url,
                        "videoKey": key,
                        "duration": actual_duration,
                        "modelId": model_id,
                        "resolution": resolution,
                    }
                )
                db_job.finished_at = datetime.now(UTC)
                db_job.lease_token = None
            await session.commit()
            if db_job is not None:
                await session.refresh(db_job)
                await publish_job_event(redis, settings, db_job)

    except Exception as exc:
        is_uncertain = isinstance(exc, MediaProviderError) and exc.uncertain
        code = exc.code if isinstance(exc, (AppError, MediaProviderError)) else type(exc).__name__
        message = (
            exc.message
            if isinstance(exc, (AppError, MediaProviderError))
            else (str(exc)[:1000] or ("画布视频生成失败" if is_canvas else "片段视频生成失败"))
        )
        logger.warning(
            "clip_video_job_failed",
            job_id=str(job_id),
            code=code,
            uncertain=is_uncertain,
            error=message,
        )
        async with sessions() as session:
            reservation = await session.scalar(
                select(CreditReservation).where(
                    CreditReservation.business_type == "video",
                    CreditReservation.business_id == job_id,
                )
            )
            if reservation is not None and not is_uncertain and reservation.status == "frozen":
                await release_media_credits(
                    session,
                    reservation_id=reservation.id,
                    reason=(
                        f"画布视频失败退还冻结积分 ({code})"
                        if is_canvas
                        else f"片段视频失败退还冻结积分 ({code})"
                    ),
                )
            if is_canvas and job.canvas_id is not None and canvas_node_id:
                await patch_canvas_node_error(
                    session,
                    canvas_id=job.canvas_id,
                    node_id=canvas_node_id,
                    error_message=message,
                    job_id=job_id,
                )
            elif clip_id is not None:
                db_clip = await session.scalar(select(StoryboardClip).where(StoryboardClip.id == clip_id))
                if db_clip is not None:
                    db_clip.video_status = "ready" if db_clip.video_url else "failed"
                    db_clip.last_job_id = job_id
            db_job = await session.scalar(select(Job).where(Job.id == job_id))
            if db_job is not None:
                db_job.status = "review" if is_uncertain else "failed"
                db_job.error_code = code
                db_job.error_message = message
                db_job.finished_at = datetime.now(UTC)
                db_job.lease_token = None
            await session.commit()
            if db_job is not None:
                await session.refresh(db_job)
                await publish_job_event(redis, settings, db_job)
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass


@ai_broker.task(task_name="framedrama.ai.execute_clip_video_job")
async def execute_clip_video_job(
    job_id: str,
    context: Context = TaskiqDepends(),
) -> None:
    runtime: WorkerRuntime = context.state.runtime
    await run_clip_video_job_core(
        sessions=runtime.sessions,
        redis=runtime.redis,
        settings=runtime.settings,
        job_id=UUID(job_id),
    )
