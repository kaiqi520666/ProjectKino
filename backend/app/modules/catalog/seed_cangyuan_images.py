"""初始化苍渊算力 GPT Image 2 / 2.5 / 2.6 共 5 款图片模型（走 -x 统一路由，不轮询上游状态）。"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import AiModel, AiProvider, ImageModelPrice

IMAGE_TIERS = ["web", "1k", "2k", "4k"]
IMAGE_RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9", "9:21", "auto"]
GEMINI_IMAGE_RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9", "auto"]
DEFAULT_ASSET_RATIOS = {"character": "16:9", "scene": "16:9", "prop": "1:1"}


@dataclass(frozen=True)
class CangyuanImageSpec:
    model_id: str
    upstream_model_id: str
    category: str
    display_name: str
    description: str
    series: str | None  # None | "flare" | "sunburst"
    prices: dict[str, Decimal]
    sort: int
    is_default: bool = False
    quality: str = "high"
    tiers: tuple[str, ...] = tuple(IMAGE_TIERS)
    ratios: tuple[str, ...] = tuple(IMAGE_RATIOS)
    max_reference_images: int = 9
    supports_mask: bool = True
    protocol: str = "gpt_image"
    poll_by_submit_endpoint: bool = False


CANGYUAN_IMAGE_SPECS: list[CangyuanImageSpec] = [
    CangyuanImageSpec(
        model_id="gpt-image-2",
        upstream_model_id="gpt-image-2-x",
        category="GPT Image 2",
        display_name="GPT Image 2",
        description="经典稳定、性价比高，适合日常角色与场景批量出图",
        series=None,
        prices={
            "web": Decimal("1.0000"),
            "1k": Decimal("2.0000"),
            "2k": Decimal("4.0000"),
            "4k": Decimal("8.0000"),
        },
        sort=10,
        is_default=True,
    ),
    CangyuanImageSpec(
        model_id="gpt-image-2.5",
        upstream_model_id="gpt-image-2.5-x",
        category="GPT Image 2.5",
        display_name="GPT Image 2.5 极速",
        description="Flare 极速通道，出图更快且光影构图升级，适合新图生成与批量试稿",
        series="flare",
        prices={
            "web": Decimal("1.5000"),
            "1k": Decimal("3.0000"),
            "2k": Decimal("5.0000"),
            "4k": Decimal("9.0000"),
        },
        sort=20,
    ),
    CangyuanImageSpec(
        model_id="gpt-image-2.5-sunburst",
        upstream_model_id="gpt-image-2.5-x",
        category="GPT Image 2.5",
        display_name="GPT Image 2.5 精修",
        description="Sunburst 精修通道，画面细节与局部还原精度更高，适合精细重绘",
        series="sunburst",
        prices={
            "web": Decimal("2.0000"),
            "1k": Decimal("3.5000"),
            "2k": Decimal("6.0000"),
            "4k": Decimal("10.0000"),
        },
        sort=21,
    ),
    CangyuanImageSpec(
        model_id="gpt-image-2.6-flare",
        upstream_model_id="gpt-image-2.6-x",
        category="GPT Image 2.6",
        display_name="GPT Image 2.6 极速",
        description="新一代 Flare 极速迭代，出图更快、版式与质感兼优，适合高质量批量生成",
        series="flare",
        prices={
            "web": Decimal("2.0000"),
            "1k": Decimal("3.5000"),
            "2k": Decimal("6.0000"),
            "4k": Decimal("10.0000"),
        },
        sort=30,
    ),
    CangyuanImageSpec(
        model_id="gpt-image-2.6-sunburst",
        upstream_model_id="gpt-image-2.6-x",
        category="GPT Image 2.6",
        display_name="GPT Image 2.6 精修",
        description="新一代 Sunburst 精修旗舰，人物脸型、道具细节与多轮修改一致性最稳",
        series="sunburst",
        prices={
            "web": Decimal("2.5000"),
            "1k": Decimal("4.0000"),
            "2k": Decimal("7.0000"),
            "4k": Decimal("12.0000"),
        },
        sort=31,
    ),
    CangyuanImageSpec(
        model_id="gemini-nano-banana-2.1",
        upstream_model_id="gemini-nano-banana-2.1",
        category="Gemini 图像",
        display_name="Nano Banana 2.1",
        description="Google Gemini 图像模型，支持 1K/2K/4K 高清创作与最多 14 张参考图",
        series=None,
        prices={
            "1k": Decimal("8.0000"),
            "2k": Decimal("8.0000"),
            "4k": Decimal("10.0000"),
        },
        sort=40,
        is_default=False,
        tiers=("1k", "2k", "4k"),
        ratios=tuple(GEMINI_IMAGE_RATIOS),
        max_reference_images=14,
        supports_mask=False,
        protocol="gemini_quality",
        poll_by_submit_endpoint=True,
    ),
]


async def seed_cangyuan_image_models(
    session: AsyncSession,
    *,
    overwrite_prices: bool = False,
) -> dict[str, int]:
    """幂等写入苍渊图片模型（GPT Image + Gemini 图像），保留原有主键与默认设置。"""
    provider = await session.scalar(select(AiProvider).where(AiProvider.key == "cangyuan"))
    if provider is None:
        raise RuntimeError("未找到 key='cangyuan' 的图片供应商，请先初始化基础供应商")

    existing_models = {
        m.id: m
        for m in await session.scalars(select(AiModel).where(AiModel.media_type == "image"))
    }
    created = 0
    updated = 0

    for spec in CANGYUAN_IMAGE_SPECS:
        caps = {
            "description": spec.description,
            "variant": spec.series or "",
            "tiers": list(spec.tiers),
            "ratios": list(spec.ratios),
            "aspectRatios": dict(DEFAULT_ASSET_RATIOS),
            "maxReferenceImages": spec.max_reference_images,
            "supportsMask": spec.supports_mask,
        }
        config: dict[str, object]
        if spec.protocol == "gemini_quality":
            config = {
                "protocol": spec.protocol,
                "pollBySubmitEndpoint": spec.poll_by_submit_endpoint,
            }
        else:
            config = {"quality": spec.quality}
            if spec.series:
                config["series"] = spec.series

        model = existing_models.get(spec.model_id)
        if model is None:
            model = AiModel(
                id=spec.model_id,
                provider_id=provider.id,
                media_type="image",
                category=spec.category,
                display_name=spec.display_name,
                upstream_model_id=spec.upstream_model_id,
                enabled=True,
                upstream_available=True,
                is_default=spec.is_default,
                sort=spec.sort,
                capabilities=caps,
                defaults={"tier": "1k"},
                configuration=config,
            )
            session.add(model)
            await session.flush()
            created += 1
        else:
            model.provider_id = provider.id
            model.category = spec.category
            model.display_name = spec.display_name
            model.upstream_model_id = spec.upstream_model_id
            model.upstream_available = True
            model.sort = spec.sort
            model.capabilities = caps
            model.defaults = {"tier": "1k"}
            model.configuration = config
            updated += 1

        existing_prices = {
            row.tier: row
            for row in await session.scalars(
                select(ImageModelPrice).where(ImageModelPrice.model_id == model.id)
            )
        }
        for tier, price in spec.prices.items():
            if tier in existing_prices:
                if overwrite_prices:
                    existing_prices[tier].credit_price = price
            else:
                session.add(
                    ImageModelPrice(
                        model_id=model.id,
                        tier=tier,
                        credit_price=price,
                    )
                )

    await session.commit()
    return {"created": created, "updated": updated, "total": len(CANGYUAN_IMAGE_SPECS)}


if __name__ == "__main__":
    import asyncio
    import sys

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.config import Settings
    from app.db.session import create_engine

    async def _run() -> None:
        overwrite = "--overwrite-prices" in sys.argv
        engine = create_engine(Settings())
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            summary = await seed_cangyuan_image_models(session, overwrite_prices=overwrite)
            print("Seeded Cangyuan image models:", summary)
        await engine.dispose()

    asyncio.run(_run())
