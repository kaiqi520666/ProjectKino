from datetime import UTC, datetime

import pytest

from app.core.errors import AppError
from app.modules.art_styles.defaults import SEED_ART_STYLES
from app.modules.art_styles.models import ArtStyle
from app.modules.art_styles.schemas import ArtStyleCreateRequest, ArtStyleUpdateRequest
from app.modules.art_styles.service import (
    create_art_style,
    delete_art_style,
    resolve_art_style_url,
    update_art_style,
)
from app.modules.storage.oss import OssConfig, OssStorage


class _ExecResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class InMemoryArtStyleSession:
    def __init__(self, project_usage: dict[str, int] | None = None) -> None:
        self.rows: list[ArtStyle] = []
        self._seq = 0
        self.project_usage = dict(project_usage or {})

    def add(self, obj: ArtStyle) -> None:
        self._seq += 1
        obj.id = self._seq
        now = datetime.now(UTC)
        obj.created_at = now
        obj.updated_at = now
        self.rows.append(obj)

    async def delete(self, obj: ArtStyle) -> None:
        self.rows = [row for row in self.rows if row.id != obj.id]

    async def flush(self) -> None:
        return None

    async def scalar(self, stmt):
        sql = str(stmt)
        where_sql = sql.split("WHERE", 1)[1] if "WHERE" in sql else ""
        params = stmt.compile().params
        if "art_styles.code" in where_sql:
            code = next(iter(params.values()), None)
            row = next((r for r in self.rows if r.code == code), None)
            return row.id if row and "SELECT art_styles.id" in sql else row
        if "art_styles.is_default" in where_sql:
            row = next((r for r in self.rows if r.is_default), None)
            return row.id if row else None
        if "art_styles.id" in where_sql:
            target_id = next(iter(params.values()), None)
            return next((r for r in self.rows if r.id == target_id), None)
        return None

    async def execute(self, stmt):
        sql = str(stmt)
        params = stmt.compile().params
        if sql.startswith("UPDATE art_styles"):
            exclude_id = params.get("id_1")
            for row in self.rows:
                if row.is_default and (exclude_id is None or row.id != exclude_id):
                    row.is_default = False
            return _ExecResult([])
        if "projects" in sql:
            codes = next((v for v in params.values() if isinstance(v, list)), [])
            return _ExecResult(
                [(code, self.project_usage[code]) for code in codes if self.project_usage.get(code, 0) > 0]
            )
        return _ExecResult([])


def test_seed_art_styles_has_18_unique_entries_and_one_default():
    assert len(SEED_ART_STYLES) == 18
    codes = [item.code for item in SEED_ART_STYLES]
    assert len(set(codes)) == 18
    defaults = [item for item in SEED_ART_STYLES if item.is_default]
    assert len(defaults) == 1
    assert defaults[0].code == "live-action"


def test_art_style_create_request_validation():
    req = ArtStyleCreateRequest(
        code="  Ink-Painting  ",
        label="  国风水墨  ",
        prompt="  中国传统水墨  ",
        image_key="framedrama/system/art-styles/ink-painting-123.webp",
        image_url="https://cdn.example.com/framedrama/system/art-styles/ink-painting-123.webp",
    )
    assert req.code == "ink-painting"
    assert req.label == "国风水墨"

    with pytest.raises(ValueError):
        ArtStyleCreateRequest(
            code="bad_code!",
            label="无效",
            prompt="测试",
            image_key="k",
            image_url="https://cdn.example.com/a.webp",
        )


def test_oss_system_upload_policy_and_url_resolution():
    storage = OssStorage(
        OssConfig(
            endpoint="https://oss-cn-hangzhou.aliyuncs.com",
            bucket="demo-bucket",
            access_key_id="ak",
            access_key_secret="sk",
            public_domain="https://cdn.framedrama.example",
            prefix="framedrama",
        )
    )
    policy = storage.system_upload_policy(
        category="art-styles",
        file_name="preview.webp",
        mime_type="image/webp",
        size=12345,
        slug="anime",
    )
    assert policy["key"].startswith("framedrama/system/art-styles/anime-")
    assert policy["key"].endswith(".webp")
    assert policy["url"].startswith("https://cdn.framedrama.example/framedrama/system/art-styles/anime-")

    row = ArtStyle(
        code="anime",
        label="日漫",
        prompt="现代日漫",
        image_key=policy["key"],
        image_url="https://old-domain.example/stale.webp",
        is_enabled=True,
        is_default=False,
        sort_order=20,
    )
    assert resolve_art_style_url(row, storage) == policy["url"]
    assert resolve_art_style_url(row, None) == "https://old-domain.example/stale.webp"


async def test_art_style_crud_default_switch_and_delete_guards():
    session = InMemoryArtStyleSession(project_usage={"anime": 2})

    s1 = await create_art_style(
        session,  # type: ignore[arg-type]
        ArtStyleCreateRequest(
            code="live-action",
            label="真人电影写实",
            prompt="真人摄影",
            image_key="framedrama/system/art-styles/live-action-1.webp",
            image_url="https://cdn.example.com/live-action-1.webp",
        ),
    )
    assert s1.is_default is True
    assert s1.is_enabled is True

    with pytest.raises(AppError) as dup_exc:
        await create_art_style(
            session,  # type: ignore[arg-type]
            ArtStyleCreateRequest(
                code="live-action",
                label="重复",
                prompt="重复",
                image_key="framedrama/system/art-styles/live-action-2.webp",
                image_url="https://cdn.example.com/live-action-2.webp",
            ),
        )
    assert dup_exc.value.code == "art_style_code_exists"

    s2 = await create_art_style(
        session,  # type: ignore[arg-type]
        ArtStyleCreateRequest(
            code="anime",
            label="日漫",
            prompt="日漫",
            image_key="framedrama/system/art-styles/anime-1.webp",
            image_url="https://cdn.example.com/anime-1.webp",
            sort_order=20,
        ),
    )
    assert s2.is_default is False

    # 默认画风不可停用
    with pytest.raises(AppError) as disable_exc:
        await update_art_style(
            session,  # type: ignore[arg-type]
            style_id=s1.id,
            body=ArtStyleUpdateRequest(is_enabled=False),
        )
    assert disable_exc.value.code == "default_art_style_cannot_disable"

    # 将 s2 设为默认并替换图片 -> s1 自动取消默认，并返回 s2 旧图片 key
    updated_s2, old_key = await update_art_style(
        session,  # type: ignore[arg-type]
        style_id=s2.id,
        body=ArtStyleUpdateRequest(
            is_default=True,
            image_key="framedrama/system/art-styles/anime-2.webp",
            image_url="https://cdn.example.com/anime-2.webp",
        ),
    )
    assert updated_s2.is_default is True
    assert s1.is_default is False
    assert old_key == "framedrama/system/art-styles/anime-1.webp"

    # s2 是默认画风，不可删除
    with pytest.raises(AppError) as del_def_exc:
        await delete_art_style(session, style_id=s2.id)  # type: ignore[arg-type]
    assert del_def_exc.value.code == "default_art_style_cannot_delete"

    # 把默认切回 s1 后，s2 因被 2 个项目引用仍不可删除
    await update_art_style(
        session,  # type: ignore[arg-type]
        style_id=s1.id,
        body=ArtStyleUpdateRequest(is_default=True),
    )
    with pytest.raises(AppError) as in_use_exc:
        await delete_art_style(session, style_id=s2.id)  # type: ignore[arg-type]
    assert in_use_exc.value.code == "art_style_in_use"

    # 新增未被引用的 s3，可正常删除并返回其 image_key
    s3 = await create_art_style(
        session,  # type: ignore[arg-type]
        ArtStyleCreateRequest(
            code="watercolor",
            label="水彩",
            prompt="水彩",
            image_key="framedrama/system/art-styles/watercolor-1.webp",
            image_url="https://cdn.example.com/watercolor-1.webp",
        ),
    )
    deleted_key = await delete_art_style(session, style_id=s3.id)  # type: ignore[arg-type]
    assert deleted_key == "framedrama/system/art-styles/watercolor-1.webp"
    assert all(r.id != s3.id for r in session.rows)
