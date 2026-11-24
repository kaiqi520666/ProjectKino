from typing import Literal

from sqlalchemy import asc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.art_styles.models import ArtStyle
from app.modules.art_styles.schemas import (
    AdminArtStyleOut,
    ArtStyleCreateRequest,
    ArtStyleOut,
    ArtStyleUpdateRequest,
)
from app.modules.storage.oss import OssStorage
from app.modules.studio.models import Project

SYSTEM_ART_STYLES_CATEGORY = "art-styles"


def resolve_art_style_url(row: ArtStyle, storage: OssStorage | None) -> str:
    if storage is not None and row.image_key:
        return storage.public_url(row.image_key)
    return row.image_url


def serialize_art_style(row: ArtStyle, storage: OssStorage | None) -> ArtStyleOut:
    return ArtStyleOut(
        id=row.id,
        code=row.code,
        label=row.label,
        prompt=row.prompt,
        image_url=resolve_art_style_url(row, storage),
        is_enabled=row.is_enabled,
        is_default=row.is_default,
        sort_order=row.sort_order,
    )


def serialize_admin_art_style(
    row: ArtStyle,
    storage: OssStorage | None,
    *,
    project_count: int = 0,
) -> AdminArtStyleOut:
    return AdminArtStyleOut(
        id=row.id,
        code=row.code,
        label=row.label,
        prompt=row.prompt,
        image_key=row.image_key,
        image_url=resolve_art_style_url(row, storage),
        is_enabled=row.is_enabled,
        is_default=row.is_default,
        sort_order=row.sort_order,
        project_count=project_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def list_public_art_styles(session: AsyncSession) -> list[ArtStyle]:
    """返回全部画风（按 sort_order 升序），包含启用状态供前台筛选与历史项目兜底显示。"""
    return list(
        await session.scalars(
            select(ArtStyle).order_by(asc(ArtStyle.sort_order), asc(ArtStyle.id))
        )
    )


async def get_project_usage_counts(session: AsyncSession, codes: list[str]) -> dict[str, int]:
    if not codes:
        return {}
    style_expr = Project.settings["visualStyle"].astext
    rows = (
        await session.execute(
            select(style_expr, func.count(Project.id))
            .where(style_expr.in_(codes))
            .group_by(style_expr)
        )
    ).all()
    return {str(code): int(cnt) for code, cnt in rows if code}


async def list_admin_art_styles(
    session: AsyncSession,
    *,
    keyword: str | None = None,
    status: Literal["all", "enabled", "disabled"] = "all",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ArtStyle], int, dict[str, int]]:
    conditions = []
    if status == "enabled":
        conditions.append(ArtStyle.is_enabled.is_(True))
    elif status == "disabled":
        conditions.append(ArtStyle.is_enabled.is_(False))

    clean_kw = (keyword or "").strip()
    if clean_kw:
        pattern = f"%{clean_kw}%"
        conditions.append(
            or_(
                ArtStyle.code.ilike(pattern),
                ArtStyle.label.ilike(pattern),
                ArtStyle.prompt.ilike(pattern),
            )
        )

    total = int(await session.scalar(select(func.count(ArtStyle.id)).where(*conditions)) or 0)
    rows = list(
        await session.scalars(
            select(ArtStyle)
            .where(*conditions)
            .order_by(asc(ArtStyle.sort_order), asc(ArtStyle.id))
            .limit(max(1, min(limit, 200)))
            .offset(max(0, offset))
        )
    )
    usage_counts = await get_project_usage_counts(session, [row.code for row in rows])
    return rows, total, usage_counts


async def resolve_art_style_prompt(session: AsyncSession, code: str | None) -> str | None:
    clean = (code or "").strip()
    if not clean:
        return None
    prompt = await session.scalar(select(ArtStyle.prompt).where(ArtStyle.code == clean))
    return prompt.strip() if isinstance(prompt, str) and prompt.strip() else None


async def _clear_default_flag(session: AsyncSession, *, exclude_id: int | None = None) -> None:
    stmt = update(ArtStyle).where(ArtStyle.is_default.is_(True))
    if exclude_id is not None:
        stmt = stmt.where(ArtStyle.id != exclude_id)
    await session.execute(stmt.values(is_default=False))
    await session.flush()


async def create_art_style(
    session: AsyncSession,
    body: ArtStyleCreateRequest,
) -> ArtStyle:
    exists = await session.scalar(select(ArtStyle.id).where(ArtStyle.code == body.code))
    if exists is not None:
        raise AppError(409, "art_style_code_exists", f"画风标识「{body.code}」已存在")

    has_default = (
        await session.scalar(select(ArtStyle.id).where(ArtStyle.is_default.is_(True))) is not None
    )
    is_default = body.is_default or (not has_default and body.is_enabled)
    is_enabled = True if is_default else body.is_enabled

    if is_default:
        await _clear_default_flag(session)

    row = ArtStyle(
        code=body.code,
        label=body.label,
        prompt=body.prompt,
        image_key=body.image_key,
        image_url=body.image_url,
        is_enabled=is_enabled,
        is_default=is_default,
        sort_order=body.sort_order,
    )
    session.add(row)
    await session.flush()
    return row


async def update_art_style(
    session: AsyncSession,
    *,
    style_id: int,
    body: ArtStyleUpdateRequest,
) -> tuple[ArtStyle, str | None]:
    row = await session.scalar(
        select(ArtStyle).where(ArtStyle.id == style_id).with_for_update()
    )
    if row is None:
        raise AppError(404, "art_style_not_found", "画风不存在")

    old_image_key: str | None = None

    if body.label is not None:
        row.label = body.label
    if body.prompt is not None:
        row.prompt = body.prompt
    if body.sort_order is not None:
        row.sort_order = body.sort_order

    if body.image_key is not None or body.image_url is not None:
        if body.image_key is None or body.image_url is None:
            raise AppError(400, "art_style_image_incomplete", "替换图片时需同时提供图片路径与访问地址")
        if body.image_key != row.image_key:
            old_image_key = row.image_key
        row.image_key = body.image_key
        row.image_url = body.image_url

    next_default = row.is_default if body.is_default is None else body.is_default
    next_enabled = row.is_enabled if body.is_enabled is None else body.is_enabled

    if row.is_default and body.is_default is False:
        raise AppError(
            400,
            "art_style_default_required",
            "无法直接取消默认画风，请将其他画风设为默认",
        )

    if next_default:
        if body.is_enabled is False:
            raise AppError(
                400,
                "default_art_style_cannot_disable",
                "默认画风不可停用，请先将其他画风设为默认",
            )
        next_enabled = True
        if not row.is_default:
            await _clear_default_flag(session, exclude_id=row.id)

    row.is_default = next_default
    row.is_enabled = next_enabled
    await session.flush()
    return row, old_image_key


async def delete_art_style(
    session: AsyncSession,
    *,
    style_id: int,
) -> str:
    row = await session.scalar(
        select(ArtStyle).where(ArtStyle.id == style_id).with_for_update()
    )
    if row is None:
        raise AppError(404, "art_style_not_found", "画风不存在")
    if row.is_default:
        raise AppError(
            400,
            "default_art_style_cannot_delete",
            "默认画风不可删除，请先将其他画风设为默认",
        )

    usage = await get_project_usage_counts(session, [row.code])
    if usage.get(row.code, 0) > 0:
        raise AppError(
            409,
            "art_style_in_use",
            f"该画风已被 {usage[row.code]} 个短剧项目引用，不能删除，请改用「停用」",
        )

    image_key = row.image_key
    await session.delete(row)
    await session.flush()
    return image_key
