from decimal import Decimal

import pytest

from app.core.errors import AppError
from app.modules.auth.deps import require_admin, require_staff
from app.modules.auth.models import User


def _user(role: str) -> User:
    return User(
        id=1,
        email=f"{role}@framedrama.local",
        password_hash="scrypt:a:b",
        nickname=role,
        role=role,
        status="active",
        balance=Decimal("10.0000"),
        frozen=Decimal("0.0000"),
        usage_multiplier=Decimal("1.0000"),
    )


async def test_role_guards_enforce_admin_and_operator_boundaries():
    admin = _user("admin")
    operator = _user("operator")
    normal = _user("user")

    assert await require_admin(admin) is admin
    with pytest.raises(AppError) as op_err:
        await require_admin(operator)
    assert op_err.value.status_code == 403

    with pytest.raises(AppError) as user_err:
        await require_admin(normal)
    assert user_err.value.status_code == 403

    assert await require_staff(admin) is admin
    assert await require_staff(operator) is operator
    with pytest.raises(AppError) as staff_err:
        await require_staff(normal)
    assert staff_err.value.status_code == 403


def test_admin_batch2_schemas_serialize_camel_case_and_validate_bounds():
    from pydantic import ValidationError

    from app.modules.admin.schemas import (
        AdminModelUpdateRequest,
        AdminRegistrationSettingsUpdate,
        AdminTextPriceInOut,
    )

    req = AdminModelUpdateRequest.model_validate(
        {
            "displayName": "DeepSeek Chat",
            "upstreamModelId": "deepseek-chat",
            "isDefault": True,
            "textPrice": {
                "inputPricePerMillion": "2.0",
                "cachedInputPricePerMillion": "0.2",
                "outputPricePerMillion": "3.0",
            },
        }
    )
    assert req.display_name == "DeepSeek Chat"
    assert req.upstream_model_id == "deepseek-chat"
    assert req.text_price == AdminTextPriceInOut(
        input_price_per_million=Decimal("2.0"),
        cached_input_price_per_million=Decimal("0.2"),
        output_price_per_million=Decimal("3.0"),
    )

    reg = AdminRegistrationSettingsUpdate.model_validate(
        {"initialCredits": "50", "defaultUsageMultiplier": "1.0"}
    )
    assert reg.initial_credits == Decimal("50")
    assert reg.default_usage_multiplier == Decimal("1.0")

    with pytest.raises(ValidationError):
        AdminRegistrationSettingsUpdate.model_validate(
            {"initialCredits": "-1", "defaultUsageMultiplier": "1.0"}
        )


def test_admin_job_filters_compile_user_search_and_date_bounds():
    from datetime import UTC, datetime
    from uuid import uuid4

    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    from app.api.v1.admin import _apply_admin_job_filters
    from app.modules.admin.schemas import AdminJobItemOut
    from app.modules.jobs.models import Job

    dt_from = datetime(2026, 11, 21, 0, 0, tzinfo=UTC)
    dt_to = datetime(2026, 11, 22, 0, 0, tzinfo=UTC)
    stmt = _apply_admin_job_filters(
        select(Job),
        status="failed",
        job_type="script_generate",
        q="  alice  ",
        created_from=dt_from,
        created_to=dt_to,
    )
    compiled = stmt.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "jobs.status =" in sql
    assert "jobs.job_type =" in sql
    assert "users.nickname ILIKE" in sql
    assert "users.email ILIKE" in sql
    assert "jobs.created_at >=" in sql
    assert "jobs.created_at <" in sql
    assert "%alice%" in compiled.params.values()

    item = AdminJobItemOut(
        id=uuid4(),
        user_id=7,
        user_email="alice@framedrama.local",
        user_nickname="Alice",
        job_type="script_generate",
        status="succeeded",
        step_index=1,
        step_total=1,
        step_label="已完成",
        progress=100,
        input_payload={},
        created_at=dt_from,
    )
    dumped = item.model_dump(by_alias=True)
    assert dumped["userNickname"] == "Alice"
    assert dumped["userEmail"] == "alice@framedrama.local"


