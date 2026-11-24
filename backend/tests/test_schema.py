from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db import models as _models  # noqa: F401
from app.db.base import Base


def test_all_v1_tables_registered_in_metadata():
    expected = {
        "users",
        "announcements",
        "art_styles",
        "system_settings",
        "ai_providers",
        "ai_models",
        "ai_model_sync_logs",
        "text_model_prices",
        "image_model_prices",
        "video_model_prices",
        "credit_reservations",
        "credit_ledgers",
        "redeem_codes",
        "redeem_code_uses",
        "projects",
        "episodes",
        "project_assets",
        "storyboard_clips",
        "canvases",
        "user_assets",
        "jobs",
    }
    assert expected.issubset(set(Base.metadata.tables.keys()))


def test_credit_ledgers_allows_negative_balance_for_llm_postpaid():
    table = Base.metadata.tables["credit_ledgers"]
    constraint_sql = [str(c.sqltext) for c in table.constraints if hasattr(c, "sqltext")]
    assert any("frozen_before >= 0" in sql for sql in constraint_sql)
    assert any("balance_after = balance_before + balance_change" in sql for sql in constraint_sql)
    assert not any("balance_after >= 0" in sql for sql in constraint_sql)


def test_alembic_has_single_head():
    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1
    assert heads[0] == "0011_art_styles"


def test_studio_media_history_and_variant_columns_registered():
    assets_cols = Base.metadata.tables["project_assets"].c
    assert "image_history" in assets_cols
    assert "parent_asset_id" in assets_cols
    assert "variant_label" in assets_cols
    assert "video_history" in Base.metadata.tables["storyboard_clips"].c
    assert "is_default_long" in Base.metadata.tables["ai_models"].c


def test_validate_default_long_and_project_settings_media_defaults():
    import pytest

    from app.api.v1.admin import _validate_default_long
    from app.core.errors import AppError
    from app.modules.llm_engine.schema import ProjectSettings

    _validate_default_long(
        media_type="video",
        enabled=True,
        is_default_long=True,
        capabilities={"maxDuration": 30},
    )
    with pytest.raises(AppError) as exc_non_video:
        _validate_default_long(
            media_type="image",
            enabled=True,
            is_default_long=True,
            capabilities={"maxDuration": 30},
        )
    assert exc_non_video.value.code == "default_long_video_only"

    with pytest.raises(AppError) as exc_short:
        _validate_default_long(
            media_type="video",
            enabled=True,
            is_default_long=True,
            capabilities={"maxDuration": 15},
        )
    assert exc_short.value.code == "default_long_requires_30s"

    settings = ProjectSettings(
        name="双默认测试",
        ratio="16:9",
        language="zh-CN",
        visualStyle="live-action",
        episodeCount=2,
        maxSegmentDuration=30,
        secondsPerEpisode=180,
        imageModelId="gpt-image-2.6-flare",
        imageTier="2k",
        videoModelId="wan-3-30s",
    )
    full_dump = settings.model_dump()
    assert full_dump["imageModelId"] == "gpt-image-2.6-flare"
    assert full_dump["imageTier"] == "2k"
    assert full_dump["videoModelId"] == "wan-3-30s"
    llm_payload = settings.llm_dump()
    assert "imageModelId" not in llm_payload
    assert "imageTier" not in llm_payload
    assert "videoModelId" not in llm_payload
