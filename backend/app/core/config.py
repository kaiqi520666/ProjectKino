from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_FILE, override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FRAMEDRAMA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"

    database_url: SecretStr = SecretStr("postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/framedrama")
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:6379/5")
    redis_key_prefix: str = "framedrama:"

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:5174",
            "http://localhost:5174",
        ]
    )

    session_ttl_seconds: int = 7 * 24 * 3600
    dependency_timeout_seconds: float = 3.0
    db_pool_size: int = 10
    db_max_overflow: int = 20

    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    image_concurrency: int = Field(default=4, ge=1, le=20)
    video_concurrency: int = Field(default=3, ge=1, le=20)
    llm_max_concurrency: int = Field(default=20, ge=1, le=500)
    llm_slot_ttl_seconds: int = Field(default=240, ge=30, le=1800)
    script_step_max_retries: int = Field(default=3, ge=0, le=10)
    script_crash_max_recoveries: int = Field(default=2, ge=0, le=10)
