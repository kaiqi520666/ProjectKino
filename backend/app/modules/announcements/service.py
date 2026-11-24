from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.announcements.models import Announcement


async def get_announcement_index(session: AsyncSession) -> list[int]:
    """返回所有公告 ID（倒序），专供前端轻量轮询与计算未读红点。"""
    return list(
        await session.scalars(select(Announcement.id).order_by(desc(Announcement.id)))
    )


async def list_announcements(
    session: AsyncSession,
    *,
    before_id: int | None = None,
    limit: int = 20,
) -> tuple[list[Announcement], bool]:
    """按游标 before_id 倒序拉取公告正文。"""
    safe_limit = max(1, min(limit, 50))
    stmt = select(Announcement)
    if before_id is not None:
        stmt = stmt.where(Announcement.id < before_id)
    rows = list(
        await session.scalars(stmt.order_by(desc(Announcement.id)).limit(safe_limit + 1))
    )
    has_more = len(rows) > safe_limit
    return rows[:safe_limit], has_more


async def list_admin_announcements(
    session: AsyncSession,
    *,
    keyword: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Announcement], int]:
    conditions = []
    clean_kw = (keyword or "").strip()
    if clean_kw:
        pattern = f"%{clean_kw}%"
        conditions.append(
            or_(Announcement.title.ilike(pattern), Announcement.content.ilike(pattern))
        )

    total = int(
        await session.scalar(select(func.count(Announcement.id)).where(*conditions)) or 0
    )
    if total == 0:
        return [], 0

    rows = list(
        await session.scalars(
            select(Announcement)
            .where(*conditions)
            .order_by(desc(Announcement.id))
            .limit(max(1, min(limit, 100)))
            .offset(max(0, offset))
        )
    )
    return rows, total


async def _locked_announcement(
    session: AsyncSession,
    announcement_id: int,
    version: int,
) -> Announcement:
    row = await session.scalar(
        select(Announcement)
        .where(Announcement.id == announcement_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise AppError(404, "announcement_not_found", "公告不存在")
    if row.version != version:
        raise AppError(409, "announcement_conflict", "公告已被他人修改，请刷新后重试")
    return row


async def create_announcement(
    session: AsyncSession,
    *,
    title: str,
    content: str,
    created_by: int | None = None,
) -> Announcement:
    row = Announcement(
        title=title.strip(),
        content=content,
        version=1,
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    return row


async def update_announcement(
    session: AsyncSession,
    *,
    announcement_id: int,
    title: str,
    content: str,
    version: int,
) -> Announcement:
    row = await _locked_announcement(session, announcement_id, version)
    row.title = title.strip()
    row.content = content
    row.version += 1
    await session.flush()
    return row


async def delete_announcement(
    session: AsyncSession,
    *,
    announcement_id: int,
    version: int,
) -> None:
    row = await _locked_announcement(session, announcement_id, version)
    await session.delete(row)
    await session.flush()
