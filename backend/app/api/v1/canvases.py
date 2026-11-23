from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects import _validate_image_model_and_infra, _validate_video_model_and_infra
from app.core.errors import AppError
from app.core.schemas import ApiResponse
from app.db.session import get_session
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.canvas.generation import resolve_canvas_generation_inputs
from app.modules.canvas.schemas import (
    CanvasCreateRequest,
    CanvasDetailOut,
    CanvasGenerateRequest,
    CanvasJobAcceptedOut,
    CanvasListOut,
    CanvasUpdateRequest,
    UserAssetCreateRequest,
    UserAssetListOut,
    UserAssetOut,
)
from app.modules.canvas.service import (
    archive_canvas,
    create_canvas,
    create_user_asset,
    delete_user_asset,
    get_user_canvas,
    list_canvas_active_jobs,
    list_user_assets,
    list_user_canvases,
    serialize_canvas_detail,
    serialize_canvas_summary,
    update_canvas,
)
from app.modules.catalog.models import AiModel, AiProvider
from app.modules.catalog.service import quote_image_price, quote_video_price
from app.modules.credits.service import assert_llm_balance_positive, freeze_media_credits
from app.modules.jobs.models import Job
from app.modules.jobs.schemas import JobOut
from app.modules.jobs.service import create_job
from app.workers.ai_tasks import (
    execute_asset_image_job,
    execute_clip_video_job,
    execute_llm_job,
)

router = APIRouter(prefix="/canvases", tags=["canvases"])
assets_router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=ApiResponse[CanvasListOut])
async def list_canvases(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CanvasListOut]:
    canvases = await list_user_canvases(session, user_id=user.id)
    return ApiResponse(data=CanvasListOut(items=[serialize_canvas_summary(c) for c in canvases]))


@router.post("", response_model=ApiResponse[CanvasDetailOut], status_code=201)
async def create_canvas_endpoint(
    body: CanvasCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CanvasDetailOut]:
    canvas = await create_canvas(session, user_id=user.id, body=body)
    await session.commit()
    await session.refresh(canvas)
    return ApiResponse(data=serialize_canvas_detail(canvas, []))


@router.get("/{canvas_id}", response_model=ApiResponse[CanvasDetailOut])
async def get_canvas_endpoint(
    canvas_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CanvasDetailOut]:
    canvas = await get_user_canvas(session, canvas_id=canvas_id, user_id=user.id)
    active_jobs = await list_canvas_active_jobs(session, canvas_id=canvas.id, user_id=user.id)
    return ApiResponse(data=serialize_canvas_detail(canvas, active_jobs))


@router.patch("/{canvas_id}", response_model=ApiResponse[CanvasDetailOut])
async def update_canvas_endpoint(
    canvas_id: UUID,
    body: CanvasUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CanvasDetailOut]:
    canvas = await update_canvas(session, canvas_id=canvas_id, user_id=user.id, body=body)
    await session.commit()
    await session.refresh(canvas)
    active_jobs = await list_canvas_active_jobs(session, canvas_id=canvas.id, user_id=user.id)
    return ApiResponse(data=serialize_canvas_detail(canvas, active_jobs))


@router.delete("/{canvas_id}", response_model=ApiResponse[dict])
async def delete_canvas_endpoint(
    canvas_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    await archive_canvas(session, canvas_id=canvas_id, user_id=user.id)
    await session.commit()
    return ApiResponse(data={"id": str(canvas_id), "archived": True})


@router.post(
    "/{canvas_id}/nodes/{node_id}/generate",
    response_model=ApiResponse[CanvasJobAcceptedOut],
    status_code=202,
)
async def generate_canvas_node_endpoint(
    canvas_id: UUID,
    node_id: str,
    body: CanvasGenerateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CanvasJobAcceptedOut]:
    clean_node_id = node_id.strip()
    if not clean_node_id or len(clean_node_id) > 64:
        raise AppError(400, "invalid_node_id", "节点 ID 不合法")

    canvas = await get_user_canvas(session, canvas_id=canvas_id, user_id=user.id)

    existing_active = await session.scalar(
        select(Job.id).where(
            Job.canvas_id == canvas.id,
            Job.target_id == clean_node_id,
            Job.status.in_(("queued", "running", "polling")),
        )
    )
    if existing_active is not None:
        raise AppError(409, "canvas_node_in_progress", "该节点已有正在执行的生成任务，请等待完成")

    resolved = resolve_canvas_generation_inputs(body)

    if body.kind == "text":
        await assert_llm_balance_positive(session, user.id)
        stmt = (
            select(AiModel)
            .join(AiProvider, AiModel.provider_id == AiProvider.id)
            .where(AiModel.media_type == "text", AiModel.enabled.is_(True), AiProvider.enabled.is_(True))
        )
        if body.model_id:
            stmt = stmt.where(AiModel.id == body.model_id)
        else:
            stmt = stmt.order_by(AiModel.is_default.desc(), AiModel.sort, AiModel.id)
        text_model = await session.scalar(stmt)
        chosen_model_id = text_model.id if text_model is not None else body.model_id

        job = await create_job(
            session,
            user_id=user.id,
            project_id=None,
            canvas_id=canvas.id,
            job_type="canvas_text",
            target_id=clean_node_id,
            input_payload={
                "canvasId": str(canvas.id),
                "nodeId": clean_node_id,
                "modelId": chosen_model_id,
                "prompt": resolved.resolved_prompt,
                "rawPrompt": body.prompt,
                "currentText": body.current_text,
                "referenceTexts": resolved.reference_texts,
                "referenceImages": resolved.reference_images,
            },
            step_total=2,
            step_label="画布文本生成任务已排队",
            idempotency_key=f"canvas_txt:{user.id}:{idempotency_key}" if idempotency_key else None,
        )
        await session.commit()
        await execute_llm_job.kiq(str(job.id))
        return ApiResponse(
            data=CanvasJobAcceptedOut(
                canvas_id=canvas.id, node_id=clean_node_id, job=JobOut.model_validate(job)
            )
        )

    if body.kind == "image":
        tier = body.tier or "1k"
        ratio = (body.ratio or "").strip() or "16:9"
        chosen_model_id = body.model_id
        if not chosen_model_id:
            default_img = await session.scalar(
                select(AiModel)
                .where(AiModel.media_type == "image", AiModel.enabled.is_(True))
                .order_by(AiModel.is_default.desc(), AiModel.sort, AiModel.id)
            )
            if default_img is None:
                raise AppError(503, "image_model_unavailable", "暂无可用的生图模型")
            chosen_model_id = default_img.id

        model = await _validate_image_model_and_infra(
            session, model_id=chosen_model_id, tier=tier, ratio=ratio
        )
        max_ref_images = int(model.capabilities.get("maxReferenceImages") or 9)
        if len(resolved.reference_urls) > max_ref_images:
            raise AppError(
                400,
                "reference_images_exceed_limit",
                (
                    f"{model.display_name} 最多支持 {max_ref_images} 张参考图，"
                    f"当前连接了 {len(resolved.reference_urls)} 张"
                ),
            )
        amount, rate_snapshot = await quote_image_price(
            session,
            model_id=model.id,
            tier=tier,
            usage_multiplier=user.usage_multiplier,
        )
        job = await create_job(
            session,
            user_id=user.id,
            project_id=None,
            canvas_id=canvas.id,
            job_type="canvas_image",
            target_id=clean_node_id,
            input_payload={
                "canvasId": str(canvas.id),
                "nodeId": clean_node_id,
                "modelId": model.id,
                "tier": tier,
                "ratio": ratio,
                "prompt": resolved.resolved_prompt,
                "referenceUrls": resolved.reference_urls,
            },
            step_total=4,
            step_label="画布生图任务已排队",
            idempotency_key=f"canvas_img:{user.id}:{idempotency_key}" if idempotency_key else None,
        )
        await freeze_media_credits(
            session,
            user_id=user.id,
            business_type="image",
            business_id=job.id,
            model_id=model.id,
            amount=amount,
            rate_snapshot=rate_snapshot,
            reason=f"画布生图预冻结 ({canvas.name} · {model.id}/{tier})",
        )
        await session.commit()
        await execute_asset_image_job.kiq(str(job.id))
        return ApiResponse(
            data=CanvasJobAcceptedOut(
                canvas_id=canvas.id, node_id=clean_node_id, job=JobOut.model_validate(job)
            )
        )

    # kind == "video"
    chosen_model_id = body.model_id
    if not chosen_model_id:
        default_vid = await session.scalar(
            select(AiModel)
            .where(AiModel.media_type == "video", AiModel.enabled.is_(True))
            .order_by(AiModel.is_default.desc(), AiModel.sort, AiModel.id)
        )
        if default_vid is None:
            raise AppError(503, "video_model_unavailable", "暂无可用的生视频模型")
        chosen_model_id = default_vid.id

    resolution = (body.resolution or "").strip().lower() or "720p"
    ratio = (body.ratio or "").strip() or "16:9"
    model, limits = await _validate_video_model_and_infra(
        session, model_id=chosen_model_id, resolution=resolution, ratio=ratio
    )
    min_duration = limits["minDuration"]
    max_duration = limits["maxDuration"]
    max_prompt_chars = limits["maxPromptChars"]
    max_ref_images = limits["maxReferenceImages"]

    duration_seconds = body.duration_seconds if body.duration_seconds is not None else min_duration
    if duration_seconds < min_duration or duration_seconds > max_duration:
        raise AppError(
            400,
            "duration_out_of_range",
            (
                f"{model.display_name} 支持时长为 {min_duration}–{max_duration} 秒，"
                f"当前请求为 {duration_seconds} 秒"
            ),
        )
    if len(resolved.resolved_prompt) > max_prompt_chars:
        raise AppError(
            400,
            "prompt_exceeds_model_limit",
            (
                f"{model.display_name} 提示词上限为 {max_prompt_chars} 字，"
                f"当前为 {len(resolved.resolved_prompt)} 字"
            ),
        )
    if len(resolved.reference_urls) > max_ref_images:
        raise AppError(
            400,
            "reference_images_exceed_limit",
            (
                f"{model.display_name} 最多支持 {max_ref_images} 张参考图，"
                f"当前连接了 {len(resolved.reference_urls)} 张"
            ),
        )

    amount, rate_snapshot = await quote_video_price(
        session,
        model_id=model.id,
        resolution=resolution,
        duration_seconds=duration_seconds,
        usage_multiplier=user.usage_multiplier,
    )
    job = await create_job(
        session,
        user_id=user.id,
        project_id=None,
        canvas_id=canvas.id,
        job_type="canvas_video",
        target_id=clean_node_id,
        input_payload={
            "canvasId": str(canvas.id),
            "nodeId": clean_node_id,
            "modelId": model.id,
            "resolution": resolution,
            "ratio": ratio,
            "durationSeconds": duration_seconds,
            "prompt": resolved.resolved_prompt,
            "referenceUrls": resolved.reference_urls,
        },
        step_total=4,
        step_label="画布生视频任务已排队",
        idempotency_key=f"canvas_vid:{user.id}:{idempotency_key}" if idempotency_key else None,
    )
    await freeze_media_credits(
        session,
        user_id=user.id,
        business_type="video",
        business_id=job.id,
        model_id=model.id,
        amount=amount,
        rate_snapshot=rate_snapshot,
        reason=f"画布生视频预冻结 ({canvas.name} · {model.id}/{duration_seconds}s)",
    )
    await session.commit()
    await execute_clip_video_job.kiq(str(job.id))
    return ApiResponse(
        data=CanvasJobAcceptedOut(
            canvas_id=canvas.id, node_id=clean_node_id, job=JobOut.model_validate(job)
        )
    )


@assets_router.get("", response_model=ApiResponse[UserAssetListOut])
async def list_assets_endpoint(
    kind: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[UserAssetListOut]:
    assets = await list_user_assets(session, user_id=user.id, kind=kind)
    return ApiResponse(data=UserAssetListOut(items=[UserAssetOut.model_validate(a) for a in assets]))


@assets_router.post("", response_model=ApiResponse[UserAssetOut], status_code=201)
async def create_asset_endpoint(
    body: UserAssetCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[UserAssetOut]:
    asset = await create_user_asset(session, user_id=user.id, body=body)
    await session.commit()
    await session.refresh(asset)
    return ApiResponse(data=UserAssetOut.model_validate(asset))


@assets_router.delete("/{asset_id}", response_model=ApiResponse[dict])
async def delete_asset_endpoint(
    asset_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    await delete_user_asset(session, asset_id=asset_id, user_id=user.id)
    await session.commit()
    return ApiResponse(data={"id": str(asset_id), "deleted": True})
