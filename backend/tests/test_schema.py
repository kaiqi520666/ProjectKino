from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db import models as _models  # noqa: F401
from app.db.base import Base


def test_all_v1_tables_registered_in_metadata():
    expected = {
        "users",
        "system_settings",
        "ai_providers",
        "ai_models",
        "ai_model_sync_logs",
        "text_model_prices",
        "image_model_prices",
        "video_model_prices",
        "credit_reservations",
        "credit_ledgers",
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
    assert heads[0] == "0004_canvas_and_assets"
