from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.canvas.models import Canvas, UserAsset
from app.modules.canvas.schemas import (
    CanvasCreateRequest,
    CanvasDetailOut,
    CanvasGraphPayload,
    CanvasSummaryOut,
    CanvasUpdateRequest,
    CanvasViewportPayload,
    UserAssetCreateRequest,
)
from app.modules.jobs.models import Job
from app.modules.jobs.schemas import JobOut

ACTIVE_JOB_STATUSES = ("queued", "running", "polling")
MAX_NODE_HISTORY = 20


def serialize_canvas_summary(canvas: Canvas) -> CanvasSummaryOut:
    return CanvasSummaryOut(
        id=canvas.id,
        name=canvas.name,
        description=canvas.description,
        cover_url=canvas.cover_url,
        status=canvas.status,
        version=canvas.version,
        node_count=canvas.node_count,
        created_at=canvas.created_at,
        updated_at=canvas.updated_at,
    )


def serialize_canvas_detail(canvas: Canvas, active_jobs: list[Job]) -> CanvasDetailOut:
    graph = CanvasGraphPayload.model_validate(canvas.graph_data or {"nodes": [], "edges": []})
    viewport = CanvasViewportPayload.model_validate(canvas.viewport) if canvas.viewport else None
    return CanvasDetailOut(
        id=canvas.id,
        name=canvas.name,
        description=canvas.description,
        cover_key=canvas.cover_key,
        cover_url=canvas.cover_url,
        status=canvas.status,
        schema_version=canvas.schema_version,
        version=canvas.version,
        node_count=canvas.node_count,
        viewport=viewport,
        graph_data=graph,
        active_jobs=[JobOut.model_validate(job) for job in active_jobs],
        created_at=canvas.created_at,
        updated_at=canvas.updated_at,
    )


async def list_user_canvases(session: AsyncSession, *, user_id: int) -> list[Canvas]:
    return list(
        await session.scalars(
            select(Canvas)
            .where(Canvas.user_id == user_id, Canvas.status == "active")
            .order_by(desc(Canvas.updated_at), desc(Canvas.id))
        )
    )


async def get_user_canvas(
    session: AsyncSession, *, canvas_id: UUID, user_id: int, for_update: bool = False
) -> Canvas:
    stmt = select(Canvas).where(
        Canvas.id == canvas_id,
        Canvas.user_id == user_id,
        Canvas.status == "active",
    )
    if for_update:
        stmt = stmt.with_for_update()
    canvas = await session.scalar(stmt)
    if canvas is None:
        raise AppError(404, "canvas_not_found", "画布不存在或已删除")
    return canvas


async def list_canvas_active_jobs(session: AsyncSession, *, canvas_id: UUID, user_id: int) -> list[Job]:
    return list(
        await session.scalars(
            select(Job)
            .where(
                Job.canvas_id == canvas_id,
                Job.user_id == user_id,
                Job.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(desc(Job.created_at), desc(Job.id))
            .limit(50)
        )
    )


async def create_canvas(
    session: AsyncSession, *, user_id: int, body: CanvasCreateRequest
) -> Canvas:
    canvas = Canvas(
        user_id=user_id,
        name=body.name.strip(),
        description=body.description.strip(),
        status="active",
        schema_version=1,
        version=1,
        node_count=0,
        graph_data={"nodes": [], "edges": []},
    )
    session.add(canvas)
    await session.flush()
    return canvas


async def update_canvas(
    session: AsyncSession, *, canvas_id: UUID, user_id: int, body: CanvasUpdateRequest
) -> Canvas:
    canvas = await get_user_canvas(session, canvas_id=canvas_id, user_id=user_id, for_update=True)
    if body.expected_version is not None and body.expected_version != canvas.version:
        raise AppError(
            409,
            "canvas_version_conflict",
            f"画布版本已更新（当前 v{canvas.version}，请求基于 v{body.expected_version}），请刷新同步后重试",
        )

    fields_set = body.model_fields_set
    if "name" in fields_set and body.name is not None:
        canvas.name = body.name.strip()
    if "description" in fields_set and body.description is not None:
        canvas.description = body.description.strip()
    if "cover_key" in fields_set:
        canvas.cover_key = body.cover_key
    if "cover_url" in fields_set:
        canvas.cover_url = body.cover_url
    if "viewport" in fields_set:
        canvas.viewport = body.viewport.model_dump(by_alias=True) if body.viewport else None
    if "graph_data" in fields_set and body.graph_data is not None:
        dumped = body.graph_data.model_dump(by_alias=True, exclude_none=True)
        canvas.graph_data = dumped
        canvas.node_count = len(body.graph_data.nodes)

    canvas.version += 1
    await session.flush()
    return canvas


async def archive_canvas(session: AsyncSession, *, canvas_id: UUID, user_id: int) -> None:
    canvas = await get_user_canvas(session, canvas_id=canvas_id, user_id=user_id, for_update=True)
    canvas.status = "archived"
    canvas.version += 1
    await session.flush()


async def patch_canvas_node_media(
    session: AsyncSession,
    *,
    canvas_id: UUID,
    node_id: str,
    media: dict[str, Any],
    job_id: UUID,
) -> bool:
    """在行锁内原子局部回写单个画布节点的媒体产出与历史，不覆盖用户对其他节点的并发修改。"""
    canvas = await session.scalar(select(Canvas).where(Canvas.id == canvas_id).with_for_update())
    if canvas is None:
        return False

    graph = deepcopy(canvas.graph_data or {"nodes": [], "edges": []})
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        return False

    target = next((n for n in nodes if isinstance(n, dict) and n.get("id") == node_id), None)
    if target is None:
        return False

    data = target.setdefault("data", {})
    if not isinstance(data, dict):
        data = {}
        target["data"] = data

    entry = {
        **media,
        "jobId": str(job_id),
        "createdAt": media.get("createdAt") or datetime.now(UTC).isoformat(),
    }
    history = data.get("history")
    history_list: list[dict[str, Any]] = list(history) if isinstance(history, list) else []
    if not any(isinstance(item, dict) and item.get("jobId") == str(job_id) for item in history_list):
        history_list.append(entry)
    if len(history_list) > MAX_NODE_HISTORY:
        history_list = history_list[-MAX_NODE_HISTORY:]

    data["media"] = entry
    data["history"] = history_list
    data["lastJobId"] = str(job_id)
    data.pop("lastError", None)

    canvas.graph_data = graph
    canvas.version += 1
    await session.flush()
    return True


async def patch_canvas_node_text(
    session: AsyncSession,
    *,
    canvas_id: UUID,
    node_id: str,
    text: str,
    base_text: str | None,
    job_id: UUID,
) -> bool:
    """在行锁内原子回写文本节点结果；若生成期间用户改过原正文，则写入 draft 供对比确认。"""
    canvas = await session.scalar(select(Canvas).where(Canvas.id == canvas_id).with_for_update())
    if canvas is None:
        return False

    graph = deepcopy(canvas.graph_data or {"nodes": [], "edges": []})
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        return False

    target = next((n for n in nodes if isinstance(n, dict) and n.get("id") == node_id), None)
    if target is None:
        return False

    data = target.setdefault("data", {})
    if not isinstance(data, dict):
        data = {}
        target["data"] = data

    current_text = data.get("text") if isinstance(data.get("text"), str) else ""
    expected_base = base_text or ""
    if current_text == expected_base:
        data["text"] = text
        data.pop("draft", None)
    else:
        data["draft"] = text
    data["lastJobId"] = str(job_id)
    data.pop("lastError", None)

    canvas.graph_data = graph
    canvas.version += 1
    await session.flush()
    return True


async def patch_canvas_node_error(
    session: AsyncSession,
    *,
    canvas_id: UUID,
    node_id: str,
    error_message: str,
    job_id: UUID,
) -> bool:
    canvas = await session.scalar(select(Canvas).where(Canvas.id == canvas_id).with_for_update())
    if canvas is None:
        return False

    graph = deepcopy(canvas.graph_data or {"nodes": [], "edges": []})
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        return False

    target = next((n for n in nodes if isinstance(n, dict) and n.get("id") == node_id), None)
    if target is None:
        return False

    data = target.setdefault("data", {})
    if not isinstance(data, dict):
        data = {}
        target["data"] = data

    data["lastJobId"] = str(job_id)
    data["lastError"] = error_message[:500]
    canvas.graph_data = graph
    canvas.version += 1
    await session.flush()
    return True


async def list_user_assets(
    session: AsyncSession, *, user_id: int, kind: str | None = None
) -> list[UserAsset]:
    stmt = select(UserAsset).where(UserAsset.user_id == user_id)
    if kind in ("text", "image", "video", "audio"):
        stmt = stmt.where(UserAsset.kind == kind)
    return list(await session.scalars(stmt.order_by(desc(UserAsset.created_at), desc(UserAsset.id))))


async def create_user_asset(
    session: AsyncSession, *, user_id: int, body: UserAssetCreateRequest
) -> UserAsset:
    if body.kind == "text":
        if not (body.text_content and body.text_content.strip()):
            raise AppError(400, "asset_text_required", "文本素材内容不能为空")
    else:
        if not body.media_url:
            raise AppError(400, "asset_media_required", "媒体素材必须包含有效链接")

    asset = UserAsset(
        user_id=user_id,
        kind=body.kind,
        title=body.title.strip(),
        text_content=body.text_content.strip() if body.text_content else None,
        media_key=body.media_key,
        media_url=body.media_url,
        media_name=body.media_name,
        source_type=body.source_type,
        source_id=body.source_id,
    )
    session.add(asset)
    await session.flush()
    return asset


async def delete_user_asset(session: AsyncSession, *, asset_id: UUID, user_id: int) -> None:
    asset = await session.scalar(
        select(UserAsset).where(UserAsset.id == asset_id, UserAsset.user_id == user_id)
    )
    if asset is None:
        raise AppError(404, "user_asset_not_found", "素材不存在")
    await session.delete(asset)
    await session.flush()
