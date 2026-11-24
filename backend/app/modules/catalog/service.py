from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.catalog.models import (
    AiModel,
    AiProvider,
    ImageModelPrice,
    TextModelPrice,
    VideoModelPrice,
)
from app.modules.catalog.schemas import (
    ImageModelPriceOut,
    ModelCatalogItemOut,
    ModelCatalogOut,
    TextModelPriceOut,
    VideoModelPriceOut,
)

_QUANT = Decimal("0.0001")


async def list_enabled_catalog(
    session: AsyncSession,
    *,
    usage_multiplier: Decimal = Decimal("1.0000"),
) -> ModelCatalogOut:
    models = list(
        await session.scalars(
            select(AiModel)
            .join(AiProvider, AiModel.provider_id == AiProvider.id)
            .where(
                AiModel.enabled.is_(True),
                AiModel.upstream_available.is_(True),
                AiProvider.enabled.is_(True),
            )
            .order_by(AiModel.sort, AiModel.id)
        )
    )
    text_prices = {row.model_id: row for row in await session.scalars(select(TextModelPrice))}
    image_prices: dict[str, list[ImageModelPrice]] = {}
    for row in await session.scalars(select(ImageModelPrice)):
        image_prices.setdefault(row.model_id, []).append(row)
    video_prices: dict[str, list[VideoModelPrice]] = {}
    for row in await session.scalars(select(VideoModelPrice)):
        video_prices.setdefault(row.model_id, []).append(row)

    tier_order = {"web": 0, "1k": 1, "2k": 2, "4k": 3}
    buckets: dict[str, list[ModelCatalogItemOut]] = {"text": [], "image": [], "video": []}
    for model in models:
        tp = text_prices.get(model.id)
        ip = sorted(image_prices.get(model.id, []), key=lambda item: tier_order.get(item.tier, 99))
        vp = sorted(video_prices.get(model.id, []), key=lambda item: item.rule_key)
        buckets[model.media_type].append(
            ModelCatalogItemOut(
                id=model.id,
                media_type=model.media_type,
                category=model.category or "",
                display_name=model.display_name,
                is_default=bool(model.is_default),
                is_default_long=bool(model.is_default_long),
                capabilities=model.capabilities,
                defaults=model.defaults,
                text_price=(
                    TextModelPriceOut(
                        input_price_per_million=(tp.input_price_per_million * usage_multiplier).quantize(
                            _QUANT, rounding=ROUND_HALF_UP
                        ),
                        cached_input_price_per_million=(
                            tp.cached_input_price_per_million * usage_multiplier
                        ).quantize(_QUANT, rounding=ROUND_HALF_UP),
                        output_price_per_million=(tp.output_price_per_million * usage_multiplier).quantize(
                            _QUANT, rounding=ROUND_HALF_UP
                        ),
                    )
                    if tp
                    else None
                ),
                image_prices=[
                    ImageModelPriceOut(
                        tier=item.tier,
                        credit_price=(item.credit_price * usage_multiplier).quantize(
                            _QUANT, rounding=ROUND_HALF_UP
                        ),
                    )
                    for item in ip
                ],
                video_prices=[
                    VideoModelPriceOut(
                        rule_key=item.rule_key,
                        unit=item.unit,
                        credit_price=(item.credit_price * usage_multiplier).quantize(
                            _QUANT, rounding=ROUND_HALF_UP
                        ),
                    )
                    for item in vp
                ],
            )
        )
    # 若某类默认模型当前上游不可用，自动将顺位第一个可用模型标为有效默认
    for items in buckets.values():
        if items and not any(item.is_default for item in items):
            items[0].is_default = True
    video_items = buckets["video"]
    if video_items and not any(item.is_default_long for item in video_items):
        for item in video_items:
            try:
                max_dur = int((item.capabilities or {}).get("maxDuration") or 15)
            except (TypeError, ValueError):
                max_dur = 15
            if max_dur >= 30:
                item.is_default_long = True
                break
    return ModelCatalogOut(**buckets)


async def quote_image_price(
    session: AsyncSession,
    *,
    model_id: str,
    tier: str,
    usage_multiplier: Decimal,
) -> tuple[Decimal, dict]:
    row = await session.scalar(
        select(ImageModelPrice).where(
            ImageModelPrice.model_id == model_id,
            ImageModelPrice.tier == tier,
        )
    )
    if row is None:
        raise AppError(400, "image_price_missing", f"模型 {model_id} 暂未配置 {tier} 档位价格")
    total = (row.credit_price * usage_multiplier).quantize(_QUANT, rounding=ROUND_HALF_UP)
    return total, {
        "modelId": model_id,
        "tier": tier,
        "basePrice": str(row.credit_price),
        "usageMultiplier": str(usage_multiplier),
    }


async def quote_video_price(
    session: AsyncSession,
    *,
    model_id: str,
    duration_seconds: int,
    rule_key: str = "default",
    usage_multiplier: Decimal = Decimal("1.0000"),
) -> tuple[Decimal, dict]:
    row = await session.scalar(
        select(VideoModelPrice).where(
            VideoModelPrice.model_id == model_id,
            VideoModelPrice.rule_key == rule_key,
        )
    )
    if row is None and rule_key != "default":
        row = await session.scalar(
            select(VideoModelPrice).where(
                VideoModelPrice.model_id == model_id,
                VideoModelPrice.rule_key == "default",
            )
        )
    if row is None:
        raise AppError(400, "video_price_missing", f"视频模型 {model_id} 暂未配置价格")
    units = Decimal(duration_seconds) if row.unit == "second" else Decimal("1")
    total = (row.credit_price * units * usage_multiplier).quantize(_QUANT, rounding=ROUND_HALF_UP)
    return total, {
        "modelId": model_id,
        "ruleKey": row.rule_key,
        "unit": row.unit,
        "durationSeconds": duration_seconds,
        "basePrice": str(row.credit_price),
        "usageMultiplier": str(usage_multiplier),
    }
