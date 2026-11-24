from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.modules.auth.models import User
from app.modules.catalog.models import TextModelPrice
from app.modules.credits.models import CreditLedger, CreditReservation
from app.modules.credits.service import (
    assert_llm_balance_positive,
    calculate_llm_token_cost,
    charge_llm_usage,
    freeze_media_credits,
    grant_credits,
    release_media_credits,
    settle_media_credits,
)


class InMemoryCreditSession:
    """轻量内存 Session 替身，覆盖 credits service 的事务、行锁、幂等与状态流转逻辑。"""

    def __init__(self, user: User, text_prices: dict[str, TextModelPrice] | None = None) -> None:
        self.users: dict[int, User] = {user.id: user}
        self.text_prices: dict[str, TextModelPrice] = text_prices or {}
        self.reservations: dict[object, CreditReservation] = {}
        self.ledgers: list[CreditLedger] = []

    def add(self, obj) -> None:
        if isinstance(obj, CreditReservation):
            if obj.id is None:
                obj.id = uuid4()
            self.reservations[obj.id] = obj
        elif isinstance(obj, CreditLedger):
            if obj.id is None:
                obj.id = uuid4()
            self.ledgers.append(obj)

    async def flush(self) -> None:
        return None

    async def scalar(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        params = stmt.compile().params
        values = list(params.values())

        if entity is User:
            user_id = values[0]
            return self.users.get(user_id)
        if entity is TextModelPrice:
            model_id = values[0]
            return self.text_prices.get(model_id)
        if entity is CreditLedger:
            key = values[0]
            return next((row for row in self.ledgers if row.idempotency_key == key), None)
        if entity is CreditReservation:
            if len(values) == 1:
                return self.reservations.get(values[0])
            btype, bid = values[0], values[1]
            return next(
                (
                    row
                    for row in self.reservations.values()
                    if row.business_type == btype and row.business_id == bid
                ),
                None,
            )
        raise NotImplementedError(f"Unsupported entity {entity}")


def _make_user(balance: str, multiplier: str = "1.0000") -> User:
    return User(
        id=1,
        email="user@framedrama.ai",
        password_hash="scrypt:aa:bb",
        nickname="测试用户",
        role="user",
        status="active",
        balance=Decimal(balance),
        frozen=Decimal("0.0000"),
        usage_multiplier=Decimal(multiplier),
    )


def _deepseek_price() -> TextModelPrice:
    return TextModelPrice(
        model_id="deepseek-flash",
        input_price_per_million=Decimal("2.000000"),
        cached_input_price_per_million=Decimal("0.200000"),
        output_price_per_million=Decimal("3.000000"),
    )


def test_calculate_llm_token_cost_splits_cached_and_uncached_input():
    price = _deepseek_price()
    # 500k uncached input ($1.0) + 500k cached input ($0.1) + 200k output ($0.6) = 1.7 * 1.5 = 2.55
    cost = calculate_llm_token_cost(
        input_tokens=1_000_000,
        cache_read_tokens=500_000,
        output_tokens=200_000,
        price=price,
        usage_multiplier=Decimal("1.5000"),
    )
    assert cost == Decimal("2.5500")


async def test_llm_balance_gate_blocks_zero_and_negative():
    session_zero = InMemoryCreditSession(_make_user("0.0000"))
    with pytest.raises(AppError) as exc_zero:
        await assert_llm_balance_positive(session_zero, 1)
    assert exc_zero.value.status_code == 402

    session_neg = InMemoryCreditSession(_make_user("-0.5000"))
    with pytest.raises(AppError) as exc_neg:
        await assert_llm_balance_positive(session_neg, 1)
    assert exc_neg.value.status_code == 402

    session_pos = InMemoryCreditSession(_make_user("0.0001"))
    user = await assert_llm_balance_positive(session_pos, 1)
    assert user.id == 1


async def test_llm_postpaid_charge_allows_negative_balance_and_is_idempotent():
    user = _make_user("0.5000")
    session = InMemoryCreditSession(user, {"deepseek-flash": _deepseek_price()})
    job_id = uuid4()

    # 1,000,000 uncached input (2.0) + 100,000 output (0.3) = 2.3000 -> balance becomes -1.8000
    ledger1 = await charge_llm_usage(
        session,
        user_id=1,
        model_id="deepseek-flash",
        job_id=job_id,
        input_tokens=1_000_000,
        cache_read_tokens=0,
        output_tokens=100_000,
        idempotency_key=f"llm:{job_id}",
        reason="生成全剧剧本（5 集）",
    )
    assert ledger1 is not None
    assert user.balance == Decimal("-1.8000")
    assert ledger1.operation == "llm_consume"
    assert ledger1.balance_before == Decimal("0.5000")
    assert ledger1.balance_after == Decimal("-1.8000")
    assert ledger1.token_usage["outputTokens"] == 100_000

    # Same idempotency_key must not double-charge.
    ledger2 = await charge_llm_usage(
        session,
        user_id=1,
        model_id="deepseek-flash",
        job_id=job_id,
        input_tokens=1_000_000,
        cache_read_tokens=0,
        output_tokens=100_000,
        idempotency_key=f"llm:{job_id}",
        reason="重复回调",
    )
    assert ledger2 is ledger1
    assert user.balance == Decimal("-1.8000")
    assert len(session.ledgers) == 1

    # Next LLM request is now blocked because balance <= 0.
    with pytest.raises(AppError) as blocked:
        await assert_llm_balance_positive(session, 1)
    assert blocked.value.status_code == 402


async def test_media_freeze_settle_and_release_lifecycle():
    user = _make_user("10.0000")
    session = InMemoryCreditSession(user)

    # 1. Image freeze -> settle
    img_job = uuid4()
    res1 = await freeze_media_credits(
        session,
        user_id=1,
        business_type="image",
        business_id=img_job,
        model_id="gpt-image-2.5",
        amount=Decimal("3.0000"),
        rate_snapshot={"tier": "1k"},
        reason="生成角色三视图",
    )
    assert user.balance == Decimal("7.0000")
    assert user.frozen == Decimal("3.0000")
    assert res1.status == "frozen"

    settled = await settle_media_credits(session, reservation_id=res1.id, reason="OSS 转存完成")
    assert settled.status == "settled"
    assert settled.consumed == Decimal("3.0000")
    assert user.balance == Decimal("7.0000")
    assert user.frozen == Decimal("0.0000")

    # 2. Video freeze -> release on definitive failure
    vid_job = uuid4()
    res2 = await freeze_media_credits(
        session,
        user_id=1,
        business_type="video",
        business_id=vid_job,
        model_id="seedance-2.0",
        amount=Decimal("6.0000"),
        rate_snapshot={"duration": 15},
        reason="生成片段视频",
    )
    assert user.balance == Decimal("1.0000")
    assert user.frozen == Decimal("6.0000")

    # Insufficient balance for another 5.0 freeze
    with pytest.raises(AppError) as low:
        await freeze_media_credits(
            session,
            user_id=1,
            business_type="video",
            business_id=uuid4(),
            model_id="seedance-2.0",
            amount=Decimal("5.0000"),
            rate_snapshot={},
            reason="余额不足",
        )
    assert low.value.status_code == 402

    released = await release_media_credits(session, reservation_id=res2.id, reason="供应商拒绝")
    assert released.status == "released"
    assert released.consumed == Decimal("0.0000")
    assert user.balance == Decimal("7.0000")
    assert user.frozen == Decimal("0.0000")

    # 3. Grant credits increases balance cleanly
    await grant_credits(
        session,
        user_id=1,
        amount=Decimal("50.0000"),
        reason="注册赠送",
        idempotency_key="grant:1",
    )
    assert user.balance == Decimal("57.0000")


def test_build_credit_bill_item_merges_freeze_with_settle_release_and_llm():
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    from app.modules.credits.models import CreditLedger, CreditReservation
    from app.modules.credits.service import build_credit_bill_item

    t0 = datetime(2026, 11, 24, 10, 0, 0, tzinfo=UTC)
    t1 = t0 + timedelta(seconds=42)
    res_id = uuid4()
    job_id = uuid4()
    proj_id = uuid4()

    freeze_ledger = CreditLedger(
        id=uuid4(),
        user_id=1,
        reservation_id=res_id,
        job_id=job_id,
        idempotency_key=f"freeze:video:{job_id}",
        operation="freeze",
        balance_change=Decimal("-12.0000"),
        frozen_change=Decimal("12.0000"),
        balance_before=Decimal("100.0000"),
        balance_after=Decimal("88.0000"),
        frozen_before=Decimal("0.0000"),
        frozen_after=Decimal("12.0000"),
        reason="分镜片段视频预扣",
        created_at=t0,
    )
    settle_ledger = CreditLedger(
        id=uuid4(),
        user_id=1,
        reservation_id=res_id,
        job_id=job_id,
        idempotency_key=f"settle:{res_id}",
        operation="settle",
        balance_change=Decimal("0.0000"),
        frozen_change=Decimal("-12.0000"),
        balance_before=Decimal("88.0000"),
        balance_after=Decimal("88.0000"),
        frozen_before=Decimal("12.0000"),
        frozen_after=Decimal("0.0000"),
        reason="分镜片段视频生成成功结算",
        created_at=t1,
    )
    reservation = CreditReservation(
        id=res_id,
        user_id=1,
        business_type="video",
        business_id=job_id,
        model_id="cc-sd2-fast-720",
        amount=Decimal("12.0000"),
        consumed=Decimal("12.0000"),
        status="settled",
        rate_snapshot={
            "modelId": "cc-sd2-fast-720",
            "ruleKey": "720p",
            "unit": "second",
            "durationSeconds": 10,
            "basePrice": "1.2",
            "usageMultiplier": "1.0000",
        },
        created_at=t0,
    )
    job = SimpleNamespace(
        id=job_id,
        job_type="clip_video",
        status="succeeded",
        project_id=proj_id,
        canvas_id=None,
        input_payload={},
    )

    settled_bill = build_credit_bill_item(
        freeze_ledger,
        reservation=reservation,
        paired_ledgers=[settle_ledger],
        job=job,  # type: ignore[arg-type]
        project_name="夜行档案",
        canvas_name=None,
        model_name="Seedance 2.0 Fast",
    )
    assert settled_bill.category == "video"
    assert settled_bill.status == "charged"
    assert settled_bill.amount == Decimal("-12.0000")
    assert settled_bill.original_amount == Decimal("12.0000")
    assert settled_bill.title == "生成分镜视频"
    assert settled_bill.project_name == "夜行档案"
    assert settled_bill.model_name == "Seedance 2.0 Fast"
    assert settled_bill.settled_at == t1
    assert [ev.operation for ev in settled_bill.timeline] == ["freeze", "settle"]

    # Released reservation -> refunded with 0 net charge
    release_ledger = CreditLedger(
        id=uuid4(),
        user_id=1,
        reservation_id=res_id,
        job_id=job_id,
        idempotency_key=f"release:{res_id}",
        operation="release",
        balance_change=Decimal("12.0000"),
        frozen_change=Decimal("-12.0000"),
        balance_before=Decimal("88.0000"),
        balance_after=Decimal("100.0000"),
        frozen_before=Decimal("12.0000"),
        frozen_after=Decimal("0.0000"),
        reason="上游失败自动退还",
        created_at=t1,
    )
    reservation.status = "released"
    reservation.consumed = Decimal("0.0000")
    refunded_bill = build_credit_bill_item(
        freeze_ledger,
        reservation=reservation,
        paired_ledgers=[release_ledger],
        job=job,  # type: ignore[arg-type]
        project_name="夜行档案",
        canvas_name=None,
        model_name="Seedance 2.0 Fast",
    )
    assert refunded_bill.status == "refunded"
    assert refunded_bill.amount == Decimal("0.0000")
    assert refunded_bill.original_amount == Decimal("12.0000")
    assert refunded_bill.balance_after == Decimal("100.0000")

    # LLM consume -> text category with model extracted from tokenUsage
    llm_ledger = CreditLedger(
        id=uuid4(),
        user_id=1,
        job_id=job_id,
        idempotency_key=f"llm:{job_id}",
        operation="llm_consume",
        balance_change=Decimal("-0.3500"),
        frozen_change=Decimal("0.0000"),
        balance_before=Decimal("100.0000"),
        balance_after=Decimal("99.6500"),
        frozen_before=Decimal("0.0000"),
        frozen_after=Decimal("0.0000"),
        token_usage={
            "modelId": "deepseek-chat",
            "inputTokens": 12000,
            "cacheReadTokens": 8000,
            "outputTokens": 2500,
        },
        reason="生成全剧剧本",
        created_at=t0,
    )
    llm_bill = build_credit_bill_item(
        llm_ledger,
        reservation=None,
        paired_ledgers=[],
        job=SimpleNamespace(
            id=job_id,
            job_type="script_generate",
            status="succeeded",
            project_id=proj_id,
            canvas_id=None,
            input_payload={},
        ),  # type: ignore[arg-type]
        project_name="夜行档案",
        canvas_name=None,
        model_name="DeepSeek V3",
    )
    assert llm_bill.category == "text"
    assert llm_bill.status == "charged"
    assert llm_bill.amount == Decimal("-0.3500")
    assert llm_bill.model_id == "deepseek-chat"
    assert llm_bill.model_name == "DeepSeek V3"
