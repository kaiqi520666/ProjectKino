"""创建或提权管理员账号，并可选择赠送初始积分。"""

import argparse
import asyncio
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.core.security import hash_password
from app.db.session import create_engine, dispose_engine
from app.modules.auth.models import User
from app.modules.credits.service import grant_credits


async def run_create_admin(email: str, password: str, nickname: str, credits: Decimal) -> None:
    settings = Settings()
    engine = create_engine(settings)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    normalized = email.strip().lower()
    try:
        async with sessions() as session:
            user = await session.scalar(select(User).where(User.email == normalized))
            if user is None:
                user = User(
                    email=normalized,
                    password_hash=hash_password(password),
                    nickname=nickname.strip() or normalized.split("@", 1)[0],
                    role="admin",
                    status="active",
                    balance=Decimal("0.0000"),
                    frozen=Decimal("0.0000"),
                    usage_multiplier=Decimal("1.0000"),
                )
                session.add(user)
                await session.flush()
                created = True
            else:
                user.role = "admin"
                user.status = "active"
                created = False

            if credits > 0:
                await grant_credits(
                    session,
                    user_id=user.id,
                    amount=credits,
                    reason="管理员初始化积分",
                    idempotency_key=f"init_admin:{user.id}:{uuid4().hex}",
                )
            await session.commit()
            await session.refresh(user)
            action = "已创建管理员" if created else "已提权管理员"
            print(f"{action}：{user.email} (id={user.id}, balance={user.balance})")
    finally:
        await dispose_engine(engine)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or promote a FrameDrama admin user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--nickname", default="管理员")
    parser.add_argument("--credits", default="0")
    args = parser.parse_args()
    asyncio.run(run_create_admin(args.email, args.password, args.nickname, Decimal(args.credits)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
