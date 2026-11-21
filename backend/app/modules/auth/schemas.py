from decimal import Decimal

from pydantic import Field, field_validator

from app.core.schemas import CamelModel


class RegisterRequest(CamelModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)
    nickname: str = Field(default="", max_length=80)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
            raise ValueError("请输入有效的邮箱地址")
        return cleaned


class LoginRequest(CamelModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserOut(CamelModel):
    id: int
    email: str
    nickname: str
    role: str
    balance: Decimal
    frozen: Decimal
    usage_multiplier: Decimal


class AuthSessionOut(CamelModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserOut
