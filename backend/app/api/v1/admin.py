import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.core.errors import AppError
from app.core.schemas import ApiResponse, CamelModel
from app.db.session import get_session
from app.modules.admin.schemas import (
    AdminImagePriceInOut,
    AdminJobItemOut,
    AdminJobListOut,
    AdminJobRefundRequest,
    AdminJobRescueMediaRequest,
    AdminModelCreateRequest,
    AdminModelItemOut,
    AdminModelReorderRequest,
    AdminModelSyncLogListOut,
    AdminModelSyncLogOut,
    AdminModelUpdateRequest,
    AdminOssSettingsOut,
    AdminOverviewOut,
    AdminProjectItemOut,
    AdminProjectListOut,
    AdminProviderHealthOut,
    AdminProviderOut,
    AdminRegistrationSettingsOut,
    AdminRegistrationSettingsUpdate,
    AdminSettingsOut,
    AdminTextPriceInOut,
    AdminUserItemOut,
    AdminUserLedgersOut,
    AdminUserListOut,
    AdminUserUpdateRequest,
    AdminVideoPriceInOut,
)
from app.modules.auth.deps import require_admin
from app.modules.auth.models import User
from app.modules.canvas.models import Canvas, UserAsset
from app.modules.canvas.service import patch_canvas_node_media
from app.modules.catalog.models import (
    AiModel,
    AiModelSyncLog,
    AiProvider,
    ImageModelPrice,
    TextModelPrice,
    VideoModelPrice,
)
from app.modules.catalog.upstream_sync import sync_provider_models_in_session
from app.modules.credits.models import CreditReservation
from app.modules.credits.redeem_service import (
    disable_redeem_batch,
    generate_redeem_codes,
    list_admin_redeem_codes,
    list_redeem_code_uses,
    resolve_redeem_status,
    update_redeem_code_status,
)
from app.modules.credits.schemas import (
    AdminRedeemBatchCreateOut,
    AdminRedeemBatchCreateRequest,
    AdminRedeemBatchDisableRequest,
    AdminRedeemCodeItemOut,
    AdminRedeemCodeListOut,
    AdminRedeemCodeStatusUpdateRequest,
    AdminRedeemCodeUseListOut,
    AdminRedeemPurchaseUrlUpdateRequest,
    CreditLedgerOut,
)
from app.modules.credits.service import (
    grant_credits,
    list_user_ledgers,
    release_media_credits,
    settle_media_credits,
)
from app.modules.jobs.models import Job
from app.modules.settings.service import (
    DEFAULT_OSS_SETTINGS,
    get_registration_policy,
    get_setting,
    set_redeem_purchase_url,
    upsert_setting,
)
from app.modules.storage.media import (
    detect_image_format,
    download_public_media,
    download_to_file,
    format_exception_detail,
    probe_video_duration,
)
from app.modules.storage.oss import load_storage
from app.modules.studio.models import Episode, Project, ProjectAsset, StoryboardClip
from app.modules.studio.service import append_asset_image_history, append_clip_video_history

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


class OssSettingUpdate(CamelModel):
    endpoint: str = Field(min_length=1)
    bucket: str = Field(min_length=1)
    access_key_id: str | None = None
    access_key_secret: str | None = None
    public_base_url: str = Field(default="")
    prefix: str = Field(default="framedrama", min_length=1)
    timeout_seconds: int = Field(default=30, ge=5, le=120)


class ProviderUpdate(CamelModel):
    display_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    auth_type: str | None = None
    auth_header: str | None = None
    enabled: bool | None = None
    configuration: dict[str, Any] | None = None


class AdminCreditAdjustRequest(CamelModel):
    amount: Decimal
    reason: str = Field(min_length=1, max_length=200)
    idempotency_key: str | None = None


@router.get("/overview", response_model=ApiResponse[AdminOverviewOut])
async def admin_overview(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminOverviewOut]:
    total_users = int(await session.scalar(select(func.count()).select_from(User)) or 0)
    active_users = int(
        await session.scalar(select(func.count()).select_from(User).where(User.status == "active")) or 0
    )
    operator_count = int(
        await session.scalar(select(func.count()).select_from(User).where(User.role == "operator")) or 0
    )
    admin_count = int(
        await session.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0
    )
    active_projects = int(
        await session.scalar(select(func.count()).select_from(Project).where(Project.status == "active")) or 0
    )
    archived_projects = int(
        await session.scalar(select(func.count()).select_from(Project).where(Project.status == "archived"))
        or 0
    )
    running_jobs = int(
        await session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status.in_(("queued", "running", "polling")))
        )
        or 0
    )
    review_jobs = int(
        await session.scalar(select(func.count()).select_from(Job).where(Job.status == "review")) or 0
    )
    since = datetime.now(UTC) - timedelta(hours=24)
    failed_jobs_24h = int(
        await session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == "failed", Job.created_at >= since)
        )
        or 0
    )
    total_balance = Decimal(
        await session.scalar(select(func.coalesce(func.sum(User.balance), Decimal("0.0000")))) or 0
    )
    total_frozen = Decimal(
        await session.scalar(select(func.coalesce(func.sum(User.frozen), Decimal("0.0000")))) or 0
    )

    oss_ok = True
    try:
        await load_storage(session)
    except AppError:
        oss_ok = False

    providers = list(
        await session.scalars(
            select(AiProvider).options(undefer(AiProvider.api_key)).order_by(AiProvider.id)
        )
    )
    provider_items = [
        AdminProviderHealthOut(
            key=p.key,
            display_name=p.display_name,
            adapter=p.adapter,
            base_url=p.base_url,
            enabled=p.enabled,
            has_api_key=bool((p.api_key or "").strip()),
        )
        for p in providers
    ]

    return ApiResponse(
        data=AdminOverviewOut(
            total_users=total_users,
            active_users=active_users,
            operator_count=operator_count,
            admin_count=admin_count,
            active_projects=active_projects,
            archived_projects=archived_projects,
            running_jobs=running_jobs,
            review_jobs=review_jobs,
            failed_jobs_24h=failed_jobs_24h,
            total_balance=total_balance,
            total_frozen=total_frozen,
            oss_configured=oss_ok,
            providers=provider_items,
        )
    )


async def _build_user_item(session: AsyncSession, user: User) -> AdminUserItemOut:
    proj_cnt = int(
        await session.scalar(
            select(func.count()).select_from(Project).where(Project.user_id == user.id)
        )
        or 0
    )
    job_cnt = int(
        await session.scalar(select(func.count()).select_from(Job).where(Job.user_id == user.id)) or 0
    )
    return AdminUserItemOut(
        id=user.id,
        email=user.email,
        nickname=user.nickname,
        role=user.role,  # type: ignore[arg-type]
        status=user.status,  # type: ignore[arg-type]
        balance=user.balance,
        frozen=user.frozen,
        usage_multiplier=user.usage_multiplier,
        project_count=proj_cnt,
        job_count=job_cnt,
        created_at=user.created_at,
    )


@router.get("/users", response_model=ApiResponse[AdminUserListOut])
async def admin_list_users(
    q: str | None = Query(default=None, max_length=120),
    role: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminUserListOut]:
    stmt = select(User)
    count_stmt = select(func.count()).select_from(User)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        cond = or_(User.email.ilike(pattern), User.nickname.ilike(pattern))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if role in ("user", "operator", "admin"):
        stmt = stmt.where(User.role == role)
        count_stmt = count_stmt.where(User.role == role)
    if status in ("active", "disabled"):
        stmt = stmt.where(User.status == status)
        count_stmt = count_stmt.where(User.status == status)

    total = int(await session.scalar(count_stmt) or 0)
    users = list(
        await session.scalars(
            stmt.order_by(desc(User.created_at), desc(User.id)).limit(limit).offset(offset)
        )
    )
    user_ids = [u.id for u in users]
    proj_counts: dict[int, int] = {}
    job_counts: dict[int, int] = {}
    if user_ids:
        proj_counts = {
            uid: int(cnt)
            for uid, cnt in (
                await session.execute(
                    select(Project.user_id, func.count())
                    .where(Project.user_id.in_(user_ids))
                    .group_by(Project.user_id)
                )
            ).all()
        }
        job_counts = {
            uid: int(cnt)
            for uid, cnt in (
                await session.execute(
                    select(Job.user_id, func.count())
                    .where(Job.user_id.in_(user_ids))
                    .group_by(Job.user_id)
                )
            ).all()
        }

    items = [
        AdminUserItemOut(
            id=u.id,
            email=u.email,
            nickname=u.nickname,
            role=u.role,  # type: ignore[arg-type]
            status=u.status,  # type: ignore[arg-type]
            balance=u.balance,
            frozen=u.frozen,
            usage_multiplier=u.usage_multiplier,
            project_count=proj_counts.get(u.id, 0),
            job_count=job_counts.get(u.id, 0),
            created_at=u.created_at,
        )
        for u in users
    ]
    return ApiResponse(data=AdminUserListOut(items=items, total=total))


@router.patch("/users/{user_id}", response_model=ApiResponse[AdminUserItemOut])
async def admin_update_user(
    user_id: int,
    body: AdminUserUpdateRequest,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminUserItemOut]:
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise AppError(404, "user_not_found", "用户不存在")

    removing_admin = user.role == "admin" and (
        (body.role is not None and body.role != "admin")
        or (body.status is not None and body.status != "active")
    )
    if removing_admin:
        if user.id == admin.id:
            raise AppError(400, "cannot_demote_self", "不能取消或禁用当前登录的管理员账号")
        other_admins = int(
            await session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == "admin", User.status == "active", User.id != user.id)
            )
            or 0
        )
        if other_admins == 0:
            raise AppError(400, "last_admin_protected", "系统至少需要保留一位可用的管理员")

    if body.nickname is not None:
        user.nickname = body.nickname.strip()
    if body.role is not None:
        user.role = body.role
    if body.status is not None:
        user.status = body.status
    if body.usage_multiplier is not None:
        user.usage_multiplier = body.usage_multiplier
    await session.commit()
    await session.refresh(user)
    return ApiResponse(data=await _build_user_item(session, user))


@router.get("/users/{user_id}/ledgers", response_model=ApiResponse[AdminUserLedgersOut])
async def admin_user_ledgers(
    user_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminUserLedgersOut]:
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise AppError(404, "user_not_found", "用户不存在")
    rows, total = await list_user_ledgers(session, user_id=user.id, limit=limit, offset=offset)
    return ApiResponse(
        data=AdminUserLedgersOut(
            user=await _build_user_item(session, user),
            items=[CreditLedgerOut.model_validate(row) for row in rows],
            total=total,
        )
    )


def _apply_admin_job_filters(
    stmt: Any,
    *,
    status: str | None = None,
    job_type: str | None = None,
    user_id: int | None = None,
    q: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> Any:
    if status in ("queued", "running", "polling", "succeeded", "failed", "review"):
        stmt = stmt.where(Job.status == status)
    if job_type and job_type.strip():
        stmt = stmt.where(Job.job_type == job_type.strip())
    if user_id is not None:
        stmt = stmt.where(Job.user_id == user_id)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        matched_user_ids = select(User.id).where(
            or_(User.nickname.ilike(pattern), User.email.ilike(pattern))
        )
        stmt = stmt.where(Job.user_id.in_(matched_user_ids))
    if created_from is not None:
        stmt = stmt.where(Job.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(Job.created_at < created_to)
    return stmt


@router.get("/jobs", response_model=ApiResponse[AdminJobListOut])
async def admin_list_jobs(
    status: str | None = Query(default=None),
    job_type: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminJobListOut]:
    filter_kwargs = {
        "status": status,
        "job_type": job_type,
        "user_id": user_id,
        "q": q,
        "created_from": created_from,
        "created_to": created_to,
    }
    stmt = _apply_admin_job_filters(select(Job), **filter_kwargs)
    count_stmt = _apply_admin_job_filters(select(func.count()).select_from(Job), **filter_kwargs)

    total = int(await session.scalar(count_stmt) or 0)
    review_count = int(
        await session.scalar(select(func.count()).select_from(Job).where(Job.status == "review")) or 0
    )
    jobs = list(
        await session.scalars(
            stmt.order_by(desc(Job.created_at), desc(Job.id)).limit(limit).offset(offset)
        )
    )

    user_ids = {j.user_id for j in jobs}
    project_ids = {j.project_id for j in jobs if j.project_id is not None}
    canvas_ids = {j.canvas_id for j in jobs if j.canvas_id is not None}
    job_ids = [j.id for j in jobs]

    users_map: dict[int, tuple[str, str]] = {}
    if user_ids:
        users_map = {
            uid: (email, nickname)
            for uid, email, nickname in (
                await session.execute(
                    select(User.id, User.email, User.nickname).where(User.id.in_(user_ids))
                )
            ).all()
        }
    projects_map: dict[UUID, str] = {}
    if project_ids:
        projects_map = {
            pid: name
            for pid, name in (
                await session.execute(select(Project.id, Project.name).where(Project.id.in_(project_ids)))
            ).all()
        }
    canvases_map: dict[UUID, str] = {}
    if canvas_ids:
        canvases_map = {
            cid: name
            for cid, name in (
                await session.execute(select(Canvas.id, Canvas.name).where(Canvas.id.in_(canvas_ids)))
            ).all()
        }
    res_map: dict[UUID, CreditReservation] = {}
    if job_ids:
        for res in await session.scalars(
            select(CreditReservation).where(CreditReservation.business_id.in_(job_ids))
        ):
            res_map[res.business_id] = res

    items = []
    for job in jobs:
        res = res_map.get(job.id)
        email, nickname = users_map.get(job.user_id, (f"#{job.user_id}", ""))
        items.append(
            AdminJobItemOut(
                id=job.id,
                user_id=job.user_id,
                user_email=email,
                user_nickname=nickname,
                project_id=job.project_id,
                project_name=projects_map.get(job.project_id) if job.project_id else None,
                canvas_id=job.canvas_id,
                canvas_name=canvases_map.get(job.canvas_id) if job.canvas_id else None,
                job_type=job.job_type,
                target_id=job.target_id,
                status=job.status,
                step_index=job.step_index,
                step_total=job.step_total,
                step_label=job.step_label,
                progress=job.progress,
                provider_task_id=job.provider_task_id,
                input_payload=job.input_payload or {},
                result_payload=job.result_payload,
                error_code=job.error_code,
                error_message=job.error_message,
                usage_summary=job.usage_summary,
                reservation_id=res.id if res else None,
                reservation_amount=res.amount if res else None,
                reservation_status=res.status if res else None,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
            )
        )
    return ApiResponse(data=AdminJobListOut(items=items, total=total, review_count=review_count))


@router.post("/jobs/{job_id}/refund", response_model=ApiResponse[dict])
async def admin_refund_review_job(
    job_id: UUID,
    body: AdminJobRefundRequest,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    """管理员核实上游未扣费后，一键退还 review/异常媒体任务的冻结积分。"""
    job = await session.scalar(select(Job).where(Job.id == job_id))
    if job is None:
        raise AppError(404, "job_not_found", "任务不存在")
    if job.job_type not in ("asset_image", "clip_video", "canvas_image", "canvas_video"):
        raise AppError(400, "not_media_job", "仅图片/视频预冻结任务支持退还冻结积分")

    btype = "image" if job.job_type in ("asset_image", "canvas_image") else "video"
    res = await session.scalar(
        select(CreditReservation).where(
            CreditReservation.business_type == btype,
            CreditReservation.business_id == job.id,
        )
    )
    if res is None:
        raise AppError(404, "reservation_not_found", "未找到该任务关联的冻结记录")
    if res.status != "frozen":
        raise AppError(409, "reservation_not_frozen", f"该冻结记录当前状态为 {res.status}，无法重复退款")

    await release_media_credits(
        session,
        reservation_id=res.id,
        reason=f"[管理员#{admin.id}] {body.reason.strip()}",
    )
    if job.status in ("review", "running", "polling", "queued"):
        job.status = "failed"
        job.error_code = job.error_code or "admin_refunded"
        job.error_message = f"{body.reason.strip()}（已退还 {res.amount} 积分）"
        job.finished_at = datetime.now(UTC)
        job.lease_token = None
        job.lease_until = None
    await session.commit()
    return ApiResponse(
        data={"jobId": str(job.id), "refundedAmount": str(res.amount), "status": job.status}
    )


@router.post("/jobs/{job_id}/rescue-media", response_model=ApiResponse[dict])
async def admin_rescue_job_media(
    job_id: UUID,
    body: AdminJobRescueMediaRequest,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    """管理员将上游已生成的图片/视频 URL 转存阿里云 OSS、写回资产/片段并结算冻结积分。"""
    media_url = body.media_url.strip()
    if not media_url.startswith(("http://", "https://")):
        raise AppError(400, "invalid_media_url", "成片链接必须以 http:// 或 https:// 开头")

    job = await session.scalar(select(Job).where(Job.id == job_id))
    if job is None:
        raise AppError(404, "job_not_found", "任务不存在")
    if job.job_type not in ("asset_image", "clip_video", "canvas_image", "canvas_video"):
        raise AppError(400, "not_media_job", "仅支持对图片或视频任务补录成片")
    if not job.target_id:
        raise AppError(400, "target_missing", "任务缺少关联资产、片段或画布节点 ID")

    storage = await load_storage(session)
    public_url = ""
    key = ""
    extra: dict[str, Any] = {}

    if job.job_type == "asset_image":
        target_uuid = UUID(job.target_id)
        asset = await session.scalar(select(ProjectAsset).where(ProjectAsset.id == target_uuid))
        if asset is None:
            raise AppError(404, "asset_not_found", "关联资产不存在")
        try:
            image_bytes = await download_public_media(media_url)
            ext, mime_type = detect_image_format(image_bytes)
            key = storage.make_key(job.user_id, "images", f"{job.id}.{ext}")
            await asyncio.to_thread(storage.put_bytes, key, image_bytes, mime_type)
            public_url = storage.public_url(key)
        except Exception as exc:
            raise AppError(
                400, "rescue_download_failed", f"下载或转存图片失败：{format_exception_detail(exc)}"
            ) from None

        input_payload = job.input_payload or {}
        asset.image_key = key
        asset.image_url = public_url
        asset.image_status = "ready"
        asset.last_job_id = job.id
        append_asset_image_history(
            asset,
            url=public_url,
            key=key,
            source="rescue",
            job_id=job.id,
            model_id=str(input_payload.get("modelId") or asset.image_model_id or "") or None,
            tier=str(input_payload.get("tier") or asset.image_tier or "") or None,
            ratio=str(input_payload.get("ratio") or "") or None,
        )
        extra = {"assetId": str(asset.id), "imageUrl": public_url, "imageKey": key}
        btype = "image"
    elif job.job_type == "clip_video":
        target_uuid = UUID(job.target_id)
        clip = await session.scalar(select(StoryboardClip).where(StoryboardClip.id == target_uuid))
        if clip is None:
            raise AppError(404, "clip_not_found", "关联分镜片段不存在")
        try:
            with tempfile.TemporaryDirectory(prefix="framedrama_admin_rescue_") as tmp:
                local_path = Path(tmp) / f"{job.id}.mp4"
                await download_to_file(media_url, local_path)
                duration = await probe_video_duration(local_path)
                key = storage.make_key(job.user_id, "videos", f"{job.id}.mp4")
                await asyncio.to_thread(storage.put_file, key, str(local_path), "video/mp4")
                public_url = storage.public_url(key)
        except Exception as exc:
            raise AppError(
                400, "rescue_download_failed", f"下载校验或转存视频失败：{format_exception_detail(exc)}"
            ) from None

        input_payload = job.input_payload or {}
        clip.video_key = key
        clip.video_url = public_url
        clip.video_status = "ready"
        clip.last_job_id = job.id
        append_clip_video_history(
            clip,
            url=public_url,
            key=key,
            source="rescue",
            job_id=job.id,
            model_id=str(input_payload.get("modelId") or clip.video_model_id or "") or None,
            resolution=str(input_payload.get("resolution") or "") or None,
            ratio=str(input_payload.get("ratio") or "") or None,
            duration=duration,
        )
        extra = {"clipId": str(clip.id), "videoUrl": public_url, "videoKey": key, "duration": duration}
        btype = "video"
    elif job.job_type == "canvas_image":
        if job.canvas_id is None:
            raise AppError(400, "canvas_missing", "任务缺少关联画布 ID")
        try:
            image_bytes = await download_public_media(media_url)
            ext, mime_type = detect_image_format(image_bytes)
            key = storage.make_key(job.user_id, "images", f"{job.id}.{ext}")
            await asyncio.to_thread(storage.put_bytes, key, image_bytes, mime_type)
            public_url = storage.public_url(key)
        except Exception as exc:
            raise AppError(
                400, "rescue_download_failed", f"下载或转存图片失败：{format_exception_detail(exc)}"
            ) from None

        model_id = str((job.input_payload or {}).get("modelId") or "canvas-image")
        await patch_canvas_node_media(
            session,
            canvas_id=job.canvas_id,
            node_id=job.target_id,
            media={"url": public_url, "key": key, "name": f"{model_id}.{ext}", "modelId": model_id},
            job_id=job.id,
        )
        extra = {
            "canvasId": str(job.canvas_id),
            "nodeId": job.target_id,
            "imageUrl": public_url,
            "imageKey": key,
            "modelId": model_id,
        }
        btype = "image"
    else:
        if job.canvas_id is None:
            raise AppError(400, "canvas_missing", "任务缺少关联画布 ID")
        try:
            with tempfile.TemporaryDirectory(prefix="framedrama_admin_rescue_") as tmp:
                local_path = Path(tmp) / f"{job.id}.mp4"
                await download_to_file(media_url, local_path)
                duration = await probe_video_duration(local_path)
                key = storage.make_key(job.user_id, "videos", f"{job.id}.mp4")
                await asyncio.to_thread(storage.put_file, key, str(local_path), "video/mp4")
                public_url = storage.public_url(key)
        except Exception as exc:
            raise AppError(
                400, "rescue_download_failed", f"下载校验或转存视频失败：{format_exception_detail(exc)}"
            ) from None

        model_id = str((job.input_payload or {}).get("modelId") or "canvas-video")
        await patch_canvas_node_media(
            session,
            canvas_id=job.canvas_id,
            node_id=job.target_id,
            media={"url": public_url, "key": key, "name": f"{model_id}.mp4", "modelId": model_id},
            job_id=job.id,
        )
        extra = {
            "canvasId": str(job.canvas_id),
            "nodeId": job.target_id,
            "videoUrl": public_url,
            "videoKey": key,
            "duration": duration,
            "modelId": model_id,
        }
        btype = "video"

    res = await session.scalar(
        select(CreditReservation).where(
            CreditReservation.business_type == btype,
            CreditReservation.business_id == job.id,
        )
    )
    settled = False
    if res is not None and res.status == "frozen":
        await settle_media_credits(
            session,
            reservation_id=res.id,
            reason=f"[管理员#{admin.id}] {body.note.strip()}",
        )
        settled = True

    job.status = "succeeded"
    job.progress = 100
    job.step_index = job.step_total
    job.step_label = "管理员已人工补录成片并入库"
    job.error_code = None
    job.error_message = None
    job.result_payload = {"projectId": str(job.project_id) if job.project_id else None, **extra}
    job.finished_at = datetime.now(UTC)
    job.lease_token = None
    job.lease_until = None
    await session.commit()

    return ApiResponse(
        data={"jobId": str(job.id), "url": public_url, "key": key, "settledReservation": settled}
    )


@router.get("/providers", response_model=ApiResponse[list[AdminProviderOut]])
async def admin_list_providers(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[AdminProviderOut]]:
    providers = list(
        await session.scalars(
            select(AiProvider).options(undefer(AiProvider.api_key)).order_by(AiProvider.id)
        )
    )
    items = [
        AdminProviderOut(
            id=p.id,
            key=p.key,
            display_name=p.display_name,
            base_url=p.base_url,
            adapter=p.adapter,
            auth_type=p.auth_type,
            auth_header=p.auth_header,
            enabled=p.enabled,
            has_api_key=bool((p.api_key or "").strip()),
            configuration=p.configuration or {},
        )
        for p in providers
    ]
    return ApiResponse(data=items)


async def _serialize_admin_models(
    session: AsyncSession,
    models: list[AiModel],
) -> list[AdminModelItemOut]:
    if not models:
        return []
    model_ids = [m.id for m in models]
    provider_ids = {m.provider_id for m in models}
    providers_map = {
        p.id: p
        for p in await session.scalars(select(AiProvider).where(AiProvider.id.in_(provider_ids)))
    }
    text_map = {
        p.model_id: p
        for p in await session.scalars(
            select(TextModelPrice).where(TextModelPrice.model_id.in_(model_ids))
        )
    }
    image_map: dict[str, list[ImageModelPrice]] = {}
    for row in await session.scalars(
        select(ImageModelPrice)
        .where(ImageModelPrice.model_id.in_(model_ids))
        .order_by(ImageModelPrice.id)
    ):
        image_map.setdefault(row.model_id, []).append(row)
    video_map: dict[str, list[VideoModelPrice]] = {}
    for row in await session.scalars(
        select(VideoModelPrice)
        .where(VideoModelPrice.model_id.in_(model_ids))
        .order_by(VideoModelPrice.id)
    ):
        video_map.setdefault(row.model_id, []).append(row)

    tier_order = {"web": 0, "1k": 1, "2k": 2, "4k": 3}
    items: list[AdminModelItemOut] = []
    for m in models:
        provider = providers_map.get(m.provider_id)
        tp = text_map.get(m.id)
        ips = sorted(image_map.get(m.id, []), key=lambda x: tier_order.get(x.tier, 99))
        vps = video_map.get(m.id, [])
        items.append(
            AdminModelItemOut(
                id=m.id,
                provider_id=m.provider_id,
                provider_key=provider.key if provider else str(m.provider_id),
                provider_name=provider.display_name if provider else "-",
                media_type=m.media_type,  # type: ignore[arg-type]
                category=m.category or "",
                display_name=m.display_name,
                upstream_model_id=m.upstream_model_id,
                enabled=m.enabled,
                upstream_available=m.upstream_available,
                last_synced_at=m.last_synced_at,
                is_default=bool(m.is_default),
                is_default_long=bool(m.is_default_long),
                sort=m.sort,
                capabilities=m.capabilities or {},
                defaults=m.defaults or {},
                configuration=m.configuration or {},
                text_price=AdminTextPriceInOut(
                    input_price_per_million=tp.input_price_per_million,
                    cached_input_price_per_million=tp.cached_input_price_per_million,
                    output_price_per_million=tp.output_price_per_million,
                )
                if tp
                else None,
                image_prices=[
                    AdminImagePriceInOut(tier=ip.tier, credit_price=ip.credit_price)  # type: ignore[arg-type]
                    for ip in ips
                ],
                video_prices=[
                    AdminVideoPriceInOut(
                        rule_key=vp.rule_key,
                        unit=vp.unit,  # type: ignore[arg-type]
                        credit_price=vp.credit_price,
                    )
                    for vp in vps
                ],
            )
        )
    return items


@router.get("/models", response_model=ApiResponse[list[AdminModelItemOut]])
async def admin_list_models(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[AdminModelItemOut]]:
    models = list(
        await session.scalars(select(AiModel).order_by(AiModel.media_type, AiModel.sort, AiModel.id))
    )
    return ApiResponse(data=await _serialize_admin_models(session, models))


def _validate_default_long(
    *,
    media_type: str,
    enabled: bool,
    is_default_long: bool,
    capabilities: dict[str, Any] | None,
) -> None:
    if not is_default_long:
        return
    if media_type != "video":
        raise AppError(400, "default_long_video_only", "仅视频模型支持设为 30s 默认")
    if not enabled:
        raise AppError(400, "default_model_must_be_enabled", "默认模型必须保持启用状态")
    try:
        max_duration = int((capabilities or {}).get("maxDuration") or 15)
    except (TypeError, ValueError):
        max_duration = 15
    if max_duration < 30:
        raise AppError(
            400,
            "default_long_requires_30s",
            "设为 30s 默认的视频模型最长时长须 ≥ 30 秒",
        )


@router.post("/models", response_model=ApiResponse[AdminModelItemOut], status_code=201)
async def admin_create_model(
    body: AdminModelCreateRequest,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminModelItemOut]:
    existing = await session.scalar(select(AiModel).where(AiModel.id == body.id.strip()))
    if existing is not None:
        raise AppError(409, "model_exists", f"模型 ID {body.id} 已存在")

    provider = await session.scalar(select(AiProvider).where(AiProvider.key == body.provider_key.strip()))
    if provider is None:
        raise AppError(404, "provider_not_found", f"供应商 {body.provider_key} 不存在")

    if body.is_default and not body.enabled:
        raise AppError(400, "default_model_must_be_enabled", "默认模型必须保持启用状态")
    _validate_default_long(
        media_type=body.media_type,
        enabled=body.enabled,
        is_default_long=body.is_default_long,
        capabilities=body.capabilities,
    )
    if body.is_default:
        await session.execute(
            update(AiModel)
            .where(AiModel.media_type == body.media_type)
            .values(is_default=False)
        )
    if body.is_default_long:
        await session.execute(
            update(AiModel)
            .where(AiModel.media_type == "video")
            .values(is_default_long=False)
        )

    model = AiModel(
        id=body.id.strip(),
        provider_id=provider.id,
        media_type=body.media_type,
        category=body.category.strip(),
        display_name=body.display_name.strip(),
        upstream_model_id=body.upstream_model_id.strip(),
        enabled=body.enabled,
        upstream_available=True,
        is_default=body.is_default,
        is_default_long=body.is_default_long,
        sort=body.sort,
        capabilities=dict(body.capabilities or {}),
        defaults=dict(body.defaults or {}),
        configuration=dict(body.configuration or {}),
    )
    session.add(model)
    await session.flush()

    if body.text_price is not None and model.media_type == "text":
        session.add(
            TextModelPrice(
                model_id=model.id,
                input_price_per_million=body.text_price.input_price_per_million,
                cached_input_price_per_million=body.text_price.cached_input_price_per_million,
                output_price_per_million=body.text_price.output_price_per_million,
            )
        )
    if body.image_prices is not None and model.media_type == "image":
        for item in body.image_prices:
            session.add(
                ImageModelPrice(
                    model_id=model.id,
                    tier=item.tier,
                    credit_price=item.credit_price,
                )
            )
    if body.video_prices is not None and model.media_type == "video":
        for item in body.video_prices:
            session.add(
                VideoModelPrice(
                    model_id=model.id,
                    rule_key=item.rule_key.strip() or "default",
                    unit=item.unit,
                    credit_price=item.credit_price,
                )
            )

    await session.commit()
    await session.refresh(model)
    serialized = await _serialize_admin_models(session, [model])
    return ApiResponse(data=serialized[0])


@router.patch("/models/{model_id}", response_model=ApiResponse[AdminModelItemOut])
async def admin_update_model(
    model_id: str,
    body: AdminModelUpdateRequest,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminModelItemOut]:
    model = await session.scalar(select(AiModel).where(AiModel.id == model_id))
    if model is None:
        raise AppError(404, "model_not_found", f"模型 {model_id} 不存在")

    if body.category is not None:
        model.category = body.category.strip()
    if body.display_name is not None:
        model.display_name = body.display_name.strip()
    if body.upstream_model_id is not None:
        model.upstream_model_id = body.upstream_model_id.strip()
    if body.sort is not None:
        model.sort = body.sort
    if body.capabilities is not None:
        model.capabilities = dict(body.capabilities)
    if body.defaults is not None:
        model.defaults = dict(body.defaults)
    if body.configuration is not None:
        model.configuration = dict(body.configuration)

    next_enabled = model.enabled if body.enabled is None else body.enabled
    next_default = model.is_default if body.is_default is None else body.is_default
    next_default_long = (
        model.is_default_long if body.is_default_long is None else body.is_default_long
    )
    if next_default and not next_enabled:
        raise AppError(400, "default_model_must_be_enabled", "默认模型必须保持启用状态")
    _validate_default_long(
        media_type=model.media_type,
        enabled=next_enabled,
        is_default_long=next_default_long,
        capabilities=model.capabilities,
    )

    if body.is_default is True and not model.is_default:
        await session.execute(
            update(AiModel)
            .where(AiModel.media_type == model.media_type, AiModel.id != model.id)
            .values(is_default=False)
        )
    if body.is_default_long is True and not model.is_default_long:
        await session.execute(
            update(AiModel)
            .where(AiModel.media_type == "video", AiModel.id != model.id)
            .values(is_default_long=False)
        )
    model.enabled = next_enabled
    model.is_default = next_default
    model.is_default_long = next_default_long

    if body.text_price is not None and model.media_type == "text":
        tp = await session.scalar(select(TextModelPrice).where(TextModelPrice.model_id == model.id))
        if tp is None:
            tp = TextModelPrice(
                model_id=model.id,
                input_price_per_million=body.text_price.input_price_per_million,
                cached_input_price_per_million=body.text_price.cached_input_price_per_million,
                output_price_per_million=body.text_price.output_price_per_million,
            )
            session.add(tp)
        else:
            tp.input_price_per_million = body.text_price.input_price_per_million
            tp.cached_input_price_per_million = body.text_price.cached_input_price_per_million
            tp.output_price_per_million = body.text_price.output_price_per_million

    if body.image_prices is not None and model.media_type == "image":
        existing_ips = {
            row.tier: row
            for row in await session.scalars(
                select(ImageModelPrice).where(ImageModelPrice.model_id == model.id)
            )
        }
        seen_tiers: set[str] = set()
        for item in body.image_prices:
            seen_tiers.add(item.tier)
            if item.tier in existing_ips:
                existing_ips[item.tier].credit_price = item.credit_price
            else:
                session.add(
                    ImageModelPrice(
                        model_id=model.id,
                        tier=item.tier,
                        credit_price=item.credit_price,
                    )
                )
        for tier, row in existing_ips.items():
            if tier not in seen_tiers:
                await session.delete(row)

    if body.video_prices is not None and model.media_type == "video":
        existing_vps = {
            row.rule_key: row
            for row in await session.scalars(
                select(VideoModelPrice).where(VideoModelPrice.model_id == model.id)
            )
        }
        seen_rules: set[str] = set()
        for item in body.video_prices:
            key = item.rule_key.strip() or "default"
            seen_rules.add(key)
            if key in existing_vps:
                existing_vps[key].unit = item.unit
                existing_vps[key].credit_price = item.credit_price
            else:
                session.add(
                    VideoModelPrice(
                        model_id=model.id,
                        rule_key=key,
                        unit=item.unit,
                        credit_price=item.credit_price,
                    )
                )
        for rule_key, row in existing_vps.items():
            if rule_key not in seen_rules:
                await session.delete(row)

    await session.commit()
    await session.refresh(model)
    serialized = await _serialize_admin_models(session, [model])
    return ApiResponse(data=serialized[0])


@router.delete("/models/{model_id}", response_model=ApiResponse[dict])
async def admin_delete_model(
    model_id: str,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    model = await session.scalar(select(AiModel).where(AiModel.id == model_id))
    if model is None:
        raise AppError(404, "model_not_found", f"模型 {model_id} 不存在")
    if model.is_default or model.is_default_long:
        raise AppError(409, "cannot_delete_default_model", "请先将其他模型设为默认后再删除")
    used_res = await session.scalar(
        select(CreditReservation.id).where(CreditReservation.model_id == model.id).limit(1)
    )
    if used_res is not None:
        raise AppError(409, "model_in_use", "该模型已存在历史扣费记录，不可删除，请直接停用")
    await session.delete(model)
    await session.commit()
    return ApiResponse(data={"id": model_id, "deleted": True})


@router.put("/models/reorder", response_model=ApiResponse[dict])
async def admin_reorder_models(
    body: AdminModelReorderRequest,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    unique_ids = list(dict.fromkeys(mid.strip() for mid in body.model_ids if mid.strip()))
    if len(unique_ids) < 2:
        raise AppError(400, "invalid_reorder", "至少需要 2 个模型才能调整排序")

    rows = list(await session.scalars(select(AiModel).where(AiModel.id.in_(unique_ids))))
    by_id = {row.id: row for row in rows}
    ordered = [by_id[mid] for mid in unique_ids if mid in by_id]
    if len(ordered) < 2:
        raise AppError(404, "model_not_found", "待排序模型不存在")

    sort_pool = sorted(row.sort for row in ordered)
    assigned: list[int] = []
    for idx, row in enumerate(ordered):
        next_sort = sort_pool[idx]
        if assigned and next_sort <= assigned[-1]:
            next_sort = assigned[-1] + 1
        row.sort = next_sort
        assigned.append(next_sort)

    await session.commit()
    return ApiResponse(
        data={
            "updated": len(ordered),
            "sorts": {row.id: row.sort for row in ordered},
        }
    )


@router.post("/models/sync", response_model=ApiResponse[dict])
async def admin_sync_upstream_models(
    provider_key: str = Query(default="cc"),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    result = await sync_provider_models_in_session(session, provider_key=provider_key)
    return ApiResponse(data=result)


@router.get("/models/sync-logs", response_model=ApiResponse[AdminModelSyncLogListOut])
async def admin_list_model_sync_logs(
    provider_key: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminModelSyncLogListOut]:
    stmt = select(AiModelSyncLog)
    count_stmt = select(func.count()).select_from(AiModelSyncLog)
    if provider_key and provider_key.strip():
        stmt = stmt.where(AiModelSyncLog.provider_key == provider_key.strip())
        count_stmt = count_stmt.where(AiModelSyncLog.provider_key == provider_key.strip())

    total = int(await session.scalar(count_stmt) or 0)
    rows = list(
        await session.scalars(
            stmt.order_by(desc(AiModelSyncLog.created_at), desc(AiModelSyncLog.id))
            .limit(limit)
            .offset(offset)
        )
    )
    return ApiResponse(
        data=AdminModelSyncLogListOut(
            items=[
                AdminModelSyncLogOut(
                    id=r.id,
                    provider_key=r.provider_key,
                    model_id=r.model_id,
                    upstream_model_id=r.upstream_model_id,
                    event_type=r.event_type,  # type: ignore[arg-type]
                    summary=r.summary,
                    created_at=r.created_at,
                )
                for r in rows
            ],
            total=total,
        )
    )


@router.get("/settings", response_model=ApiResponse[AdminSettingsOut])
async def admin_get_settings(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminSettingsOut]:
    raw_oss = await get_setting(session, "storage.oss", DEFAULT_OSS_SETTINGS)
    key_id = str(raw_oss.get("access_key_id") or raw_oss.get("accessKeyId") or "").strip()
    key_secret = str(
        raw_oss.get("access_key_secret") or raw_oss.get("accessKeySecret") or ""
    ).strip()
    public_base = str(
        raw_oss.get("public_base_url")
        or raw_oss.get("publicBaseUrl")
        or raw_oss.get("public_domain")
        or raw_oss.get("publicDomain")
        or ""
    ).strip()
    oss_ok = True
    try:
        await load_storage(session)
    except AppError:
        oss_ok = False

    initial_credits, default_multiplier = await get_registration_policy(session)
    return ApiResponse(
        data=AdminSettingsOut(
            oss=AdminOssSettingsOut(
                endpoint=str(raw_oss.get("endpoint") or ""),
                bucket=str(raw_oss.get("bucket") or ""),
                public_base_url=public_base,
                prefix=str(raw_oss.get("prefix") or "framedrama"),
                timeout_seconds=int(
                    raw_oss.get("timeout_seconds") or raw_oss.get("timeoutSeconds") or 30
                ),
                has_credentials=bool(key_id and key_secret),
                configured=oss_ok,
            ),
            registration=AdminRegistrationSettingsOut(
                initial_credits=initial_credits,
                default_usage_multiplier=default_multiplier,
            ),
        )
    )


@router.put("/settings/oss", response_model=ApiResponse[dict])
async def update_oss_settings(
    body: OssSettingUpdate,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    existing = await get_setting(session, "storage.oss", DEFAULT_OSS_SETTINGS)
    existing_key_id = str(
        existing.get("access_key_id") or existing.get("accessKeyId") or ""
    ).strip()
    existing_key_secret = str(
        existing.get("access_key_secret") or existing.get("accessKeySecret") or ""
    ).strip()

    key_id = (body.access_key_id or "").strip() or existing_key_id
    key_secret = (body.access_key_secret or "").strip() or existing_key_secret
    if not key_id or not key_secret:
        raise AppError(400, "oss_credentials_required", "首次配置阿里云 OSS 必须填写 AccessKey ID 与 Secret")

    payload = {
        "endpoint": body.endpoint.strip(),
        "bucket": body.bucket.strip(),
        "access_key_id": key_id,
        "access_key_secret": key_secret,
        "public_base_url": body.public_base_url.strip(),
        "prefix": body.prefix.strip("/") or "framedrama",
        "timeout_seconds": body.timeout_seconds,
    }
    await upsert_setting(session, "storage.oss", payload)
    await session.commit()
    return ApiResponse(
        data={
            "endpoint": payload["endpoint"],
            "bucket": payload["bucket"],
            "publicBaseUrl": payload["public_base_url"],
            "prefix": payload["prefix"],
            "timeoutSeconds": payload["timeout_seconds"],
            "hasCredentials": True,
            "configured": True,
        }
    )


@router.put("/settings/registration", response_model=ApiResponse[AdminRegistrationSettingsOut])
async def update_registration_settings(
    body: AdminRegistrationSettingsUpdate,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminRegistrationSettingsOut]:
    payload = {
        "initial_credits": str(body.initial_credits),
        "default_usage_multiplier": str(body.default_usage_multiplier),
    }
    await upsert_setting(session, "registration", payload)
    await session.commit()
    return ApiResponse(
        data=AdminRegistrationSettingsOut(
            initial_credits=body.initial_credits,
            default_usage_multiplier=body.default_usage_multiplier,
        )
    )


@router.get("/projects", response_model=ApiResponse[AdminProjectListOut])
async def admin_list_projects(
    status: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminProjectListOut]:
    stmt = select(Project).join(User, Project.user_id == User.id)
    count_stmt = select(func.count()).select_from(Project).join(User, Project.user_id == User.id)
    if status in ("active", "archived"):
        stmt = stmt.where(Project.status == status)
        count_stmt = count_stmt.where(Project.status == status)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        cond = or_(Project.name.ilike(pattern), User.email.ilike(pattern))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total = int(await session.scalar(count_stmt) or 0)
    archived_count = int(
        await session.scalar(
            select(func.count()).select_from(Project).where(Project.status == "archived")
        )
        or 0
    )
    projects = list(
        await session.scalars(
            stmt.order_by(desc(Project.updated_at), desc(Project.created_at))
            .limit(limit)
            .offset(offset)
        )
    )
    project_ids = [p.id for p in projects]
    user_ids = {p.user_id for p in projects}

    users_map: dict[int, str] = {}
    ep_counts: dict[UUID, int] = {}
    asset_counts: dict[UUID, int] = {}
    clip_counts: dict[UUID, int] = {}
    job_counts: dict[UUID, int] = {}
    active_job_counts: dict[UUID, int] = {}

    if user_ids:
        users_map = {
            uid: email
            for uid, email in (
                await session.execute(select(User.id, User.email).where(User.id.in_(user_ids)))
            ).all()
        }
    if project_ids:
        ep_counts = {
            pid: int(cnt)
            for pid, cnt in (
                await session.execute(
                    select(Episode.project_id, func.count())
                    .where(Episode.project_id.in_(project_ids))
                    .group_by(Episode.project_id)
                )
            ).all()
        }
        asset_counts = {
            pid: int(cnt)
            for pid, cnt in (
                await session.execute(
                    select(ProjectAsset.project_id, func.count())
                    .where(ProjectAsset.project_id.in_(project_ids))
                    .group_by(ProjectAsset.project_id)
                )
            ).all()
        }
        clip_counts = {
            pid: int(cnt)
            for pid, cnt in (
                await session.execute(
                    select(StoryboardClip.project_id, func.count())
                    .where(StoryboardClip.project_id.in_(project_ids))
                    .group_by(StoryboardClip.project_id)
                )
            ).all()
        }
        job_counts = {
            pid: int(cnt)
            for pid, cnt in (
                await session.execute(
                    select(Job.project_id, func.count())
                    .where(Job.project_id.in_(project_ids))
                    .group_by(Job.project_id)
                )
            ).all()
            if pid is not None
        }
        active_job_counts = {
            pid: int(cnt)
            for pid, cnt in (
                await session.execute(
                    select(Job.project_id, func.count())
                    .where(
                        Job.project_id.in_(project_ids),
                        Job.status.in_(("queued", "running", "polling")),
                    )
                    .group_by(Job.project_id)
                )
            ).all()
            if pid is not None
        }

    items = [
        AdminProjectItemOut(
            id=p.id,
            user_id=p.user_id,
            user_email=users_map.get(p.user_id, f"#{p.user_id}"),
            name=p.name,
            status=p.status,
            episode_count=ep_counts.get(p.id, 0),
            asset_count=asset_counts.get(p.id, 0),
            clip_count=clip_counts.get(p.id, 0),
            job_count=job_counts.get(p.id, 0),
            active_job_count=active_job_counts.get(p.id, 0),
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in projects
    ]
    return ApiResponse(
        data=AdminProjectListOut(items=items, total=total, archived_count=archived_count)
    )


@router.post("/projects/{project_id}/restore", response_model=ApiResponse[dict])
async def admin_restore_archived_project(
    project_id: UUID,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    project = await session.scalar(select(Project).where(Project.id == project_id))
    if project is None:
        raise AppError(404, "project_not_found", "项目不存在")
    if project.status != "archived":
        raise AppError(409, "project_not_archived", "该项目当前已是活跃状态")
    project.status = "active"
    await session.commit()
    return ApiResponse(data={"id": str(project.id), "status": project.status})


@router.put("/providers/{provider_key}", response_model=ApiResponse[dict])
async def update_provider(
    provider_key: str,
    body: ProviderUpdate,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    provider = await session.scalar(select(AiProvider).where(AiProvider.key == provider_key))
    if provider is None:
        raise AppError(404, "provider_not_found", f"供应商 {provider_key} 不存在")
    if body.display_name is not None:
        provider.display_name = body.display_name
    if body.base_url is not None:
        provider.base_url = body.base_url.rstrip("/")
    if body.api_key is not None and body.api_key.strip():
        provider.api_key = body.api_key.strip()
    if body.auth_type is not None:
        provider.auth_type = body.auth_type
    if body.auth_header is not None:
        provider.auth_header = body.auth_header
    if body.enabled is not None:
        provider.enabled = body.enabled
    if body.configuration is not None:
        provider.configuration = body.configuration
    await session.commit()
    return ApiResponse(
        data={
            "key": provider.key,
            "displayName": provider.display_name,
            "baseUrl": provider.base_url,
            "enabled": provider.enabled,
        }
    )


@router.post("/users/{user_id}/credits", response_model=ApiResponse[CreditLedgerOut])
async def admin_adjust_credits(
    user_id: int,
    body: AdminCreditAdjustRequest,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CreditLedgerOut]:
    operation = "grant" if body.amount > 0 else "adjust"
    ledger = await grant_credits(
        session,
        user_id=user_id,
        amount=body.amount,
        reason=body.reason,
        idempotency_key=body.idempotency_key or f"admin:{admin.id}:{user_id}:{uuid4().hex}",
        operation=operation,
        operator_id=admin.id,
    )
    await session.commit()
    return ApiResponse(data=CreditLedgerOut.model_validate(ledger))


@router.delete("/projects/{project_id}/purge", response_model=ApiResponse[dict])
async def admin_purge_archived_project(
    project_id: UUID,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    """
    管理员彻底删除已软删（archived）的项目：
    - 级联清除 projects / episodes / project_assets / storyboard_clips 与对应 OSS 媒体文件；
    - 永久保留 credit_ledgers、credit_reservations 与 jobs 历史记录用于对账审计。
    """
    project = await session.scalar(select(Project).where(Project.id == project_id))
    if project is None:
        raise AppError(404, "project_not_found", "项目不存在")
    if project.status != "archived":
        raise AppError(409, "project_not_archived", "仅允许彻底清理已软删除（archived）的项目")
    active_job = await session.scalar(
        select(Job.id).where(
            Job.project_id == project.id,
            Job.status.in_(("queued", "running", "polling")),
        )
    )
    if active_job is not None:
        raise AppError(409, "project_has_active_jobs", "该项目仍有进行中的任务，暂不可清理")

    asset_rows = (
        await session.execute(
            select(ProjectAsset.image_key, ProjectAsset.image_history).where(
                ProjectAsset.project_id == project.id
            )
        )
    ).all()
    clip_rows = (
        await session.execute(
            select(
                StoryboardClip.preview_key,
                StoryboardClip.video_key,
                StoryboardClip.video_history,
            ).where(StoryboardClip.project_id == project.id)
        )
    ).all()
    ep_keys = list(
        await session.scalars(
            select(Episode.composed_video_key).where(
                Episode.project_id == project.id, Episode.composed_video_key.is_not(None)
            )
        )
    )
    candidate_keys: set[str] = set()
    for image_key, image_history in asset_rows:
        if image_key:
            candidate_keys.add(image_key)
        for item in image_history or []:
            if isinstance(item, dict) and isinstance(item.get("key"), str) and item["key"].strip():
                candidate_keys.add(item["key"].strip())
    for preview_key, video_key, video_history in clip_rows:
        if preview_key:
            candidate_keys.add(preview_key)
        if video_key:
            candidate_keys.add(video_key)
        for item in video_history or []:
            if isinstance(item, dict) and isinstance(item.get("key"), str) and item["key"].strip():
                candidate_keys.add(item["key"].strip())
    for k in ep_keys:
        if k:
            candidate_keys.add(k)

    owner_id = project.user_id
    if candidate_keys:
        referenced_user_asset_keys = set(
            await session.scalars(
                select(UserAsset.media_key).where(
                    UserAsset.user_id == owner_id,
                    UserAsset.media_key.in_(candidate_keys),
                )
            )
        )
        candidate_keys.difference_update(k for k in referenced_user_asset_keys if k)
    oss_keys = list(candidate_keys)

    storage = None
    try:
        storage = await load_storage(session)
    except AppError:
        storage = None

    await session.delete(project)
    await session.commit()

    deleted_oss = 0
    if storage is not None and oss_keys:
        try:
            required = f"{storage.config.prefix}/{owner_id}/"
            deleted_oss = await asyncio.to_thread(
                storage.delete_objects, oss_keys, required_prefix=required
            )
        except Exception:
            logger.warning("admin_purge_oss_cleanup_failed", project_id=str(project_id))

    return ApiResponse(
        data={
            "id": str(project_id),
            "purged": True,
            "deletedOssCount": deleted_oss,
        }
    )


@router.get("/redeem-codes", response_model=ApiResponse[AdminRedeemCodeListOut])
async def admin_list_redeem_codes(
    status: Literal["active", "exhausted", "expired", "disabled"] | None = Query(default=None),
    batch_name: str | None = Query(default=None, max_length=120),
    keyword: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminRedeemCodeListOut]:
    data = await list_admin_redeem_codes(
        session,
        status_filter=status,
        batch_name=batch_name,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )
    return ApiResponse(data=data)


@router.post("/redeem-codes/batch", response_model=ApiResponse[AdminRedeemBatchCreateOut])
async def admin_create_redeem_codes(
    body: AdminRedeemBatchCreateRequest,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminRedeemBatchCreateOut]:
    rows = await generate_redeem_codes(
        session,
        credits=body.credits,
        count=body.count,
        prefix=body.prefix,
        batch_name=body.batch_name,
        max_uses=body.max_uses,
        expires_at=body.expires_at,
        created_by=admin.id,
    )
    await session.commit()
    return ApiResponse(
        data=AdminRedeemBatchCreateOut(
            count=len(rows),
            credits=rows[0].credits if rows else body.credits,
            batch_name=rows[0].batch_name if rows else body.batch_name.strip(),
            codes=[r.code for r in rows],
        )
    )


@router.put("/redeem-codes/purchase-url", response_model=ApiResponse[dict])
async def admin_update_redeem_purchase_url(
    body: AdminRedeemPurchaseUrlUpdateRequest,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    saved = await set_redeem_purchase_url(session, body.purchase_url)
    await session.commit()
    return ApiResponse(data={"purchaseUrl": saved})


@router.get("/redeem-codes/{code_id}/uses", response_model=ApiResponse[AdminRedeemCodeUseListOut])
async def admin_get_redeem_code_uses(
    code_id: UUID,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminRedeemCodeUseListOut]:
    items = await list_redeem_code_uses(session, code_id=code_id)
    return ApiResponse(data=AdminRedeemCodeUseListOut(items=items))


@router.patch("/redeem-codes/{code_id}", response_model=ApiResponse[AdminRedeemCodeItemOut])
async def admin_update_redeem_code_status(
    code_id: UUID,
    body: AdminRedeemCodeStatusUpdateRequest,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminRedeemCodeItemOut]:
    row = await update_redeem_code_status(session, code_id=code_id, status=body.status)
    await session.commit()
    return ApiResponse(
        data=AdminRedeemCodeItemOut(
            id=row.id,
            code=row.code,
            batch_name=row.batch_name,
            credits=row.credits,
            max_uses=row.max_uses,
            used_count=row.used_count,
            status=resolve_redeem_status(row),
            raw_status="disabled" if row.status == "disabled" else "active",
            expires_at=row.expires_at,
            created_at=row.created_at,
        )
    )


@router.post("/redeem-codes/batch-disable", response_model=ApiResponse[dict])
async def admin_disable_redeem_batch(
    body: AdminRedeemBatchDisableRequest,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    disabled_count = await disable_redeem_batch(session, batch_name=body.batch_name)
    await session.commit()
    return ApiResponse(data={"batchName": body.batch_name.strip(), "disabledCount": disabled_count})
