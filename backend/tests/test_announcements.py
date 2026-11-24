from datetime import UTC, datetime

import pytest

from app.core.errors import AppError
from app.modules.announcements.models import Announcement
from app.modules.announcements.service import (
    create_announcement,
    delete_announcement,
    get_announcement_index,
    list_announcements,
    update_announcement,
)


class InMemoryAnnouncementSession:
    def __init__(self) -> None:
        self.rows: list[Announcement] = []
        self._seq = 0

    def add(self, obj: Announcement) -> None:
        self._seq += 1
        obj.id = self._seq
        now = datetime.now(UTC)
        obj.published_at = obj.published_at or now
        obj.created_at = now
        obj.updated_at = now
        self.rows.append(obj)

    async def delete(self, obj: Announcement) -> None:
        self.rows = [row for row in self.rows if row.id != obj.id]

    async def flush(self) -> None:
        return None

    async def scalar(self, stmt):
        params = stmt.compile().params
        values = list(params.values())
        target_id = values[0]
        return next((row for row in self.rows if row.id == target_id), None)

    async def scalars(self, stmt):
        col = stmt.column_descriptions[0]["expr"]
        params = stmt.compile().params
        ordered = sorted(self.rows, key=lambda r: r.id, reverse=True)
        if col is Announcement.id:
            return [r.id for r in ordered]
        before_id = params.get("id_1")
        if before_id is not None:
            ordered = [r for r in ordered if r.id < before_id]
        limit = params.get("param_1")
        if isinstance(limit, int):
            ordered = ordered[:limit]
        return ordered


async def test_announcement_crud_cursor_pagination_and_optimistic_lock():
    session = InMemoryAnnouncementSession()

    a1 = await create_announcement(session, title="公告一", content="# 内容 1", created_by=1)  # type: ignore[arg-type]
    a2 = await create_announcement(session, title="公告二", content="内容 2", created_by=1)  # type: ignore[arg-type]
    a3 = await create_announcement(session, title="公告三", content="内容 3", created_by=1)  # type: ignore[arg-type]

    ids = await get_announcement_index(session)  # type: ignore[arg-type]
    assert ids == [a3.id, a2.id, a1.id]

    page1, has_more1 = await list_announcements(session, limit=2)  # type: ignore[arg-type]
    assert [r.id for r in page1] == [a3.id, a2.id]
    assert has_more1 is True

    page2, has_more2 = await list_announcements(session, before_id=page1[-1].id, limit=2)  # type: ignore[arg-type]
    assert [r.id for r in page2] == [a1.id]
    assert has_more2 is False

    updated = await update_announcement(
        session,  # type: ignore[arg-type]
        announcement_id=a2.id,
        title="公告二（修订）",
        content="修订正文",
        version=1,
    )
    assert updated.version == 2
    assert updated.title == "公告二（修订）"

    with pytest.raises(AppError) as exc_conflict:
        await update_announcement(
            session,  # type: ignore[arg-type]
            announcement_id=a2.id,
            title="过期修改",
            content="内容",
            version=1,
        )
    assert exc_conflict.value.status_code == 409
    assert exc_conflict.value.code == "announcement_conflict"

    with pytest.raises(AppError) as exc_del_conflict:
        await delete_announcement(session, announcement_id=a2.id, version=1)  # type: ignore[arg-type]
    assert exc_del_conflict.value.status_code == 409

    await delete_announcement(session, announcement_id=a2.id, version=2)  # type: ignore[arg-type]
    assert await get_announcement_index(session) == [a3.id, a1.id]
