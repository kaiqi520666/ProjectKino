from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.modules.auth.models import User
from app.modules.credits.models import CreditLedger, RedeemCode, RedeemCodeUse
from app.modules.credits.redeem_service import (
    REDEEM_ALPHABET,
    generate_random_code_str,
    generate_redeem_codes,
    normalize_redeem_code,
    redeem_code_for_user,
    resolve_redeem_status,
    sanitize_prefix,
)
from app.modules.credits.service import build_credit_bill_item


class InMemoryRedeemSession:
    """轻量内存 Session，验证兑换码生成、核销幂等、并发校验与账本联动。"""

    def __init__(self, users: list[User]) -> None:
        self.users: dict[int, User] = {u.id: u for u in users}
        self.codes: list[RedeemCode] = []
        self.uses: list[RedeemCodeUse] = []
        self.ledgers: list[CreditLedger] = []

    def add(self, obj) -> None:
        if isinstance(obj, CreditLedger):
            if obj.id is None:
                obj.id = uuid4()
            if obj.created_at is None:
                obj.created_at = datetime.now(UTC)
            self.ledgers.append(obj)
        elif isinstance(obj, RedeemCodeUse):
            if obj.id is None:
                obj.id = uuid4()
            if obj.created_at is None:
                obj.created_at = datetime.now(UTC)
            self.uses.append(obj)
        elif isinstance(obj, RedeemCode):
            if obj.id is None:
                obj.id = uuid4()
            self.codes.append(obj)

    def add_all(self, objs) -> None:
        for obj in objs:
            self.add(obj)

    async def flush(self) -> None:
        return None

    async def scalars(self, stmt):
        col = stmt.column_descriptions[0]["expr"]
        params = stmt.compile().params
        values = list(params.values())
        if col is RedeemCode.code_normalized:
            targets = set(values[0]) if values and isinstance(values[0], (list, tuple, set)) else set(values)
            return [row.code_normalized for row in self.codes if row.code_normalized in targets]
        raise NotImplementedError(f"Unsupported scalars {col}")

    async def scalar(self, stmt):
        desc_0 = stmt.column_descriptions[0]
        entity = desc_0.get("entity")
        expr = desc_0.get("expr")
        params = stmt.compile().params
        values = list(params.values())

        if entity is User:
            return self.users.get(values[0])
        if entity is CreditLedger:
            return next((row for row in self.ledgers if row.idempotency_key == values[0]), None)
        if entity is RedeemCode:
            if expr is RedeemCode.id:
                norm = values[0]
                row = next((c for c in self.codes if c.code_normalized == norm), None)
                return row.id if row else None
            norm = values[0]
            return next((c for c in self.codes if c.code_normalized == norm), None)
        if entity is RedeemCodeUse:
            code_id, user_id = values[0], values[1]
            row = next((u for u in self.uses if u.code_id == code_id and u.user_id == user_id), None)
            return row.id if row else None
        raise NotImplementedError(f"Unsupported scalar {entity} {expr}")


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    async def get(self, key: str):
        val = self.store.get(key)
        return str(val) if val is not None else None

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, _ttl: int) -> None:
        return None

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


def _user(uid: int, balance: str = "10.0000") -> User:
    return User(
        id=uid,
        email=f"u{uid}@kino.test",
        password_hash="scrypt:aa:bb",
        nickname=f"用户{uid}",
        role="user",
        status="active",
        balance=Decimal(balance),
        frozen=Decimal("0.0000"),
        usage_multiplier=Decimal("1.0000"),
    )


def test_random_code_format_and_normalization():
    for _ in range(30):
        code = generate_random_code_str()
        parts = code.split("-")
        assert len(parts) == 3
        assert all(len(p) == 4 for p in parts)
        joined = "".join(parts)
        assert all(ch in REDEEM_ALPHABET for ch in joined)
        for ambiguous in ("0", "O", "1", "I", "L"):
            assert ambiguous not in joined

    prefixed = generate_random_code_str("KINO")
    assert prefixed.startswith("KINO-")
    assert normalize_redeem_code(f"  {prefixed.lower()} ") == normalize_redeem_code(prefixed)

    assert sanitize_prefix(" pk26 ") == "PK26"
    with pytest.raises(AppError):
        sanitize_prefix("BAD-PREFIX!")


async def test_generate_and_redeem_single_use_code_happy_path():
    u1 = _user(1, "10.0000")
    u2 = _user(2, "5.0000")
    session = InMemoryRedeemSession([u1, u2])
    redis = FakeRedis()

    codes = await generate_redeem_codes(
        session,  # type: ignore[arg-type]
        credits=Decimal("100"),
        count=3,
        prefix="PK",
        batch_name="发卡网100积分",
        created_by=99,
    )
    assert len(codes) == 3
    assert len({c.code_normalized for c in codes}) == 3

    target = codes[0]
    # 兼容小写 + 去横杠 + 前后空格输入
    messy_input = f"  {target.code.lower().replace('-', '')}  "
    code_row, ledger = await redeem_code_for_user(
        session,  # type: ignore[arg-type]
        user_id=1,
        raw_code=messy_input,
        redis=redis,
    )
    assert code_row.used_count == 1
    assert u1.balance == Decimal("110.0000")
    assert ledger.operation == "redeem"
    assert ledger.balance_change == Decimal("100.0000")
    assert ledger.reason == "兑换码充值（发卡网100积分）"

    # 账单视图正确归类为 income / credited
    bill = build_credit_bill_item(
        ledger,
        reservation=None,
        paired_ledgers=[],
        job=None,
        project_name=None,
        canvas_name=None,
        model_name=None,
    )
    assert bill.category == "income"
    assert bill.status == "credited"
    assert bill.title == "兑换码充值"
    assert bill.amount == Decimal("100.0000")

    # 同一用户重复兑换被拦截
    with pytest.raises(AppError) as exc_dup:
        await redeem_code_for_user(
            session,  # type: ignore[arg-type]
            user_id=1,
            raw_code=target.code,
            redis=redis,
        )
    assert exc_dup.value.code == "redeem_code_already_used_by_user"

    # 其他用户兑换已被用完的一次性卡密被拦截
    with pytest.raises(AppError) as exc_used:
        await redeem_code_for_user(
            session,  # type: ignore[arg-type]
            user_id=2,
            raw_code=target.code,
            redis=redis,
        )
    assert exc_used.value.code == "redeem_code_exhausted"


async def test_disabled_expired_and_rate_limited_redeem_codes():
    u1 = _user(1)
    session = InMemoryRedeemSession([u1])
    redis = FakeRedis()

    expired = RedeemCode(
        id=uuid4(),
        code="EXPD-EXPD-EXPD",
        code_normalized="EXPDEXPDEXPD",
        batch_name="",
        credits=Decimal("50"),
        max_uses=1,
        used_count=0,
        status="active",
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    disabled = RedeemCode(
        id=uuid4(),
        code="DISA-DISA-DISA",
        code_normalized="DISADISADISA",
        batch_name="",
        credits=Decimal("50"),
        max_uses=1,
        used_count=0,
        status="disabled",
    )
    session.add_all([expired, disabled])

    assert resolve_redeem_status(expired) == "expired"
    assert resolve_redeem_status(disabled) == "disabled"

    with pytest.raises(AppError) as exc_exp:
        await redeem_code_for_user(
            session,  # type: ignore[arg-type]
            user_id=1,
            raw_code=expired.code,
            redis=redis,
        )
    assert exc_exp.value.code == "redeem_code_expired"

    with pytest.raises(AppError) as exc_dis:
        await redeem_code_for_user(
            session,  # type: ignore[arg-type]
            user_id=1,
            raw_code=disabled.code,
            redis=redis,
        )
    assert exc_dis.value.code == "redeem_code_disabled"

    # 连续失败达到阈值后触发频控（前两次已计 2 次，再试 8 次满 10 次）
    for _ in range(8):
        with pytest.raises(AppError):
            await redeem_code_for_user(
                session,  # type: ignore[arg-type]
                user_id=1,
                raw_code="NOPE-NOPE-NOPE",
                redis=redis,
            )

    with pytest.raises(AppError) as exc_rl:
        await redeem_code_for_user(
            session,  # type: ignore[arg-type]
            user_id=1,
            raw_code="NOPE-NOPE-NOPE",
            redis=redis,
        )
    assert exc_rl.value.status_code == 429
    assert exc_rl.value.code == "redeem_rate_limited"
