import os

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.settings import ModelSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.core.errors import AppError
from app.modules.catalog.models import AiModel, AiProvider

MODEL_SETTINGS = ModelSettings(
    timeout=300,
    max_tokens=8192,
    thinking=False,
    extra_body={"thinking": {"type": "disabled"}},
)


async def resolve_deepseek_model(
    session: AsyncSession,
    model_id: str | None = None,
) -> tuple[OpenAIChatModel, str]:
    """从数据库读取 DeepSeek 供应商与模型配置；若数据库未填 Key 则回退到环境变量 DEEPSEEK_API_KEY。"""
    stmt = (
        select(AiModel, AiProvider)
        .join(AiProvider, AiModel.provider_id == AiProvider.id)
        .options(undefer(AiProvider.api_key))
        .where(AiModel.media_type == "text", AiModel.enabled.is_(True), AiProvider.enabled.is_(True))
    )
    if model_id:
        stmt = stmt.where(AiModel.id == model_id)
    else:
        stmt = stmt.order_by(AiModel.is_default.desc(), AiModel.sort)

    row = (await session.execute(stmt)).first()
    if row is None:
        key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not key:
            raise AppError(503, "llm_provider_unavailable", "未配置可用的 DeepSeek 文本模型")
        fallback_model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
        provider = DeepSeekProvider(api_key=key, base_url=os.getenv("DEEPSEEK_BASE_URL"))
        return OpenAIChatModel(fallback_model, provider=provider), "deepseek-flash"

    ai_model, ai_provider = row
    db_key = (ai_provider.api_key or "").strip()
    key = db_key or os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise AppError(503, "llm_api_key_missing", "尚未配置 DeepSeek API Key")
    db_base_url = (ai_provider.base_url or "").strip()
    env_base_url = os.getenv("DEEPSEEK_BASE_URL", "").strip()
    env_model = os.getenv("DEEPSEEK_MODEL", "").strip()
    base_url = db_base_url if db_key else (env_base_url or db_base_url)
    upstream_model = ai_model.upstream_model_id if db_key else (env_model or ai_model.upstream_model_id)
    provider = DeepSeekProvider(api_key=key, base_url=base_url or None)
    return OpenAIChatModel(upstream_model, provider=provider), ai_model.id
