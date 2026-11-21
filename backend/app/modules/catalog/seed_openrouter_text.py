"""初始化 OpenRouter 文本供应商与 @preset/ds-baidu 默认文本模型，并清理不再使用的 DeepSeek 官方渠道。"""

from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import AiModel, AiProvider, TextModelPrice
from app.modules.credits.models import CreditReservation

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
TEXT_MODEL_ID = "or-ds-baidu"
TEXT_UPSTREAM_MODEL = "@preset/ds-baidu"
TEXT_DISPLAY_NAME = "DeepSeek V4.1 Flash (OpenRouter)"
TEXT_DESCRIPTION = "OpenRouter Preset（Baidu / River / DeepInfra · FP8 价格优先）"

INPUT_PRICE = Decimal("2.000000")
CACHED_INPUT_PRICE = Decimal("0.200000")
OUTPUT_PRICE = Decimal("3.000000")


async def seed_openrouter_text_model(
    session: AsyncSession,
    *,
    remove_deepseek: bool = True,
) -> dict[str, object]:
    """
    幂等写入 OpenRouter 供应商 + @preset/ds-baidu 默认文本模型（输入 2 / 缓存 0.2 / 输出 3 积分/百万 token）。
    保留已有 OpenRouter api_key（若此前已在后台填过），并安全清理旧 DeepSeek 官方供应商与模型。
    """
    provider = await session.scalar(select(AiProvider).where(AiProvider.key == "openrouter"))
    if provider is None:
        provider = AiProvider(
            key="openrouter",
            display_name="OpenRouter",
            base_url=OPENROUTER_BASE_URL,
            adapter="openrouter",
            auth_type="bearer",
            api_key="",
            enabled=True,
            configuration={"appTitle": "FrameDrama"},
        )
        session.add(provider)
        await session.flush()
    else:
        provider.display_name = "OpenRouter"
        provider.base_url = OPENROUTER_BASE_URL
        provider.adapter = "openrouter"
        provider.auth_type = "bearer"
        provider.enabled = True
        provider.configuration = {**(provider.configuration or {}), "appTitle": "FrameDrama"}

    # 先将其余文本模型取消默认
    await session.execute(
        update(AiModel)
        .where(AiModel.media_type == "text", AiModel.id != TEXT_MODEL_ID)
        .values(is_default=False)
    )

    model = await session.scalar(select(AiModel).where(AiModel.id == TEXT_MODEL_ID))
    if model is None:
        model = AiModel(
            id=TEXT_MODEL_ID,
            provider_id=provider.id,
            media_type="text",
            category="OpenRouter",
            display_name=TEXT_DISPLAY_NAME,
            upstream_model_id=TEXT_UPSTREAM_MODEL,
            enabled=True,
            upstream_available=True,
            is_default=True,
            sort=10,
            capabilities={"description": TEXT_DESCRIPTION},
            defaults={},
            configuration={},
        )
        session.add(model)
        await session.flush()
    else:
        model.provider_id = provider.id
        model.category = "OpenRouter"
        model.display_name = TEXT_DISPLAY_NAME
        model.upstream_model_id = TEXT_UPSTREAM_MODEL
        model.enabled = True
        model.upstream_available = True
        model.is_default = True
        model.sort = 10
        model.capabilities = {**(model.capabilities or {}), "description": TEXT_DESCRIPTION}

    price = await session.scalar(select(TextModelPrice).where(TextModelPrice.model_id == model.id))
    if price is None:
        session.add(
            TextModelPrice(
                model_id=model.id,
                input_price_per_million=INPUT_PRICE,
                cached_input_price_per_million=CACHED_INPUT_PRICE,
                output_price_per_million=OUTPUT_PRICE,
            )
        )
    else:
        price.input_price_per_million = INPUT_PRICE
        price.cached_input_price_per_million = CACHED_INPUT_PRICE
        price.output_price_per_million = OUTPUT_PRICE

    deepseek_action = "kept"
    if remove_deepseek:
        old_provider = await session.scalar(select(AiProvider).where(AiProvider.key == "deepseek"))
        if old_provider is not None:
            old_models = list(
                await session.scalars(select(AiModel).where(AiModel.provider_id == old_provider.id))
            )
            can_delete_provider = True
            for old_m in old_models:
                used = await session.scalar(
                    select(CreditReservation.id).where(CreditReservation.model_id == old_m.id).limit(1)
                )
                if used is None:
                    await session.delete(old_m)
                else:
                    old_m.enabled = False
                    old_m.is_default = False
                    can_delete_provider = False
            await session.flush()
            if can_delete_provider:
                await session.delete(old_provider)
                deepseek_action = "deleted"
            else:
                old_provider.enabled = False
                deepseek_action = "disabled"
        else:
            deepseek_action = "not_found"

    await session.commit()
    return {
        "provider": provider.key,
        "modelId": model.id,
        "upstreamModelId": model.upstream_model_id,
        "deepseek": deepseek_action,
    }


if __name__ == "__main__":
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.config import Settings
    from app.db.session import create_engine

    async def _run() -> None:
        engine = create_engine(Settings())
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            result = await seed_openrouter_text_model(session)
            print("Seeded OpenRouter text config:", result)
        await engine.dispose()

    asyncio.run(_run())
