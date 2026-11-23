import os

from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
from pydantic_ai.providers.openrouter import OpenRouterProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.core.errors import AppError
from app.modules.catalog.models import AiModel, AiProvider

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TEXT_MODEL_ID = "or-ds-baidu"
DEFAULT_UPSTREAM_PRESET = "@preset/ds-baidu"

MODEL_SETTINGS = OpenRouterModelSettings(
    timeout=420,
    max_tokens=32768,
    openrouter_reasoning={"enabled": False},
    openrouter_usage={"include": True},
)


async def resolve_text_model(
    session: AsyncSession,
    model_id: str | None = None,
) -> tuple[OpenRouterModel, str]:
    """
    从数据库读取已启用的文本模型与 OpenRouter 供应商配置。
    若数据库未填 Key，仅回退环境变量 OPENROUTER_API_KEY（不串用其他供应商 Key）。
    """
    stmt = (
        select(AiModel, AiProvider)
        .join(AiProvider, AiModel.provider_id == AiProvider.id)
        .options(undefer(AiProvider.api_key))
        .where(AiModel.media_type == "text", AiModel.enabled.is_(True), AiProvider.enabled.is_(True))
    )
    if model_id:
        stmt = stmt.where(AiModel.id == model_id)
    else:
        stmt = stmt.order_by(AiModel.is_default.desc(), AiModel.sort, AiModel.id)

    row = (await session.execute(stmt)).first()
    if row is None:
        env_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not env_key:
            raise AppError(
                503,
                "llm_provider_unavailable",
                "未配置可用的 OpenRouter 文本模型，请先在管理后台启用并填写 API Key",
            )
        fallback_upstream = (
            os.getenv("OPENROUTER_MODEL", DEFAULT_UPSTREAM_PRESET).strip()
            or DEFAULT_UPSTREAM_PRESET
        )
        fallback_base = (
            os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).strip()
            or DEFAULT_OPENROUTER_BASE_URL
        )
        provider = OpenRouterProvider(
            api_key=env_key,
            base_url=fallback_base,
            app_title="FrameDrama",
        )
        model = OpenRouterModel(fallback_upstream, provider=provider, settings=MODEL_SETTINGS)
        return model, DEFAULT_TEXT_MODEL_ID

    ai_model, ai_provider = row
    db_key = (ai_provider.api_key or "").strip()
    key = db_key or os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise AppError(
            503,
            "llm_api_key_missing",
            f"尚未配置 {ai_provider.display_name} API Key，请在管理后台「供应商与定价」中填写",
        )

    base_url = (ai_provider.base_url or "").strip() or DEFAULT_OPENROUTER_BASE_URL
    cfg = ai_provider.configuration or {}
    app_title = str(cfg.get("appTitle") or "FrameDrama")
    app_url = str(cfg.get("appUrl") or "").strip() or None

    provider = OpenRouterProvider(
        api_key=key,
        base_url=base_url,
        app_url=app_url,
        app_title=app_title,
    )
    model = OpenRouterModel(ai_model.upstream_model_id, provider=provider, settings=MODEL_SETTINGS)
    return model, ai_model.id


# 保留别名，兼容既有内部引用
resolve_deepseek_model = resolve_text_model
