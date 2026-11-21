"""初始化上游 CC 全部 20 个 Seedance 视频模型（1 元 = 10 积分，全部启用）。"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import AiModel, AiProvider, VideoModelPrice

ALL_RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"]
BASIC_RATIOS = ["1:1", "16:9", "9:16"]


@dataclass(frozen=True)
class SeedanceSpec:
    model_id: str
    upstream_model_id: str
    category: str
    display_name: str
    description: str
    resolutions: list[str]
    unit: str  # "call" | "second"
    credit_price: Decimal
    min_duration: int
    max_duration: int
    ratios: list[str]
    max_ref_images: int
    max_ref_videos: int
    max_ref_audios: int
    max_prompt_chars: int = 5000
    sort: int = 100
    is_default: bool = False


# 全部 20 个 Seedance 型号：复用原有 seedance-2.0 (-> sd-2-c4) 与 seedance-2.5 (-> sd-2.5-c3) 主键
SEEDANCE_SPECS: list[SeedanceSpec] = [
    # ---- Seedance 2.0（10 个，按条计费，1 元 = 10 积分） ----
    SeedanceSpec(
        model_id="cc-sd2-fast-720",
        upstream_model_id="cc-sd2-fast-720",
        category="Seedance 2.0",
        display_name="Seedance 2.0 极速 720p",
        description="快速稳定不限并发，适合日常分镜批量出片",
        resolutions=["720p"],
        unit="call",
        credit_price=Decimal("15.0000"),
        min_duration=4,
        max_duration=15,
        ratios=ALL_RATIOS,
        max_ref_images=9,
        max_ref_videos=3,
        max_ref_audios=3,
        sort=10,
        is_default=True,
    ),
    SeedanceSpec(
        model_id="cc-sd2-fast-480",
        upstream_model_id="cc-sd2-fast-480",
        category="Seedance 2.0",
        display_name="Seedance 2.0 极速 480p",
        description="标清极速特惠渠道，适合快速验证镜头节奏",
        resolutions=["480p"],
        unit="call",
        credit_price=Decimal("9.0000"),
        min_duration=4,
        max_duration=15,
        ratios=ALL_RATIOS,
        max_ref_images=9,
        max_ref_videos=3,
        max_ref_audios=3,
        sort=11,
    ),
    SeedanceSpec(
        model_id="cc-sd2-mini-480",
        upstream_model_id="cc-sd2-mini-480",
        category="Seedance 2.0",
        display_name="Seedance 2.0 Mini 480p",
        description="最低成本试片档位，适合草稿预览与大批量测试",
        resolutions=["480p"],
        unit="call",
        credit_price=Decimal("6.0000"),
        min_duration=4,
        max_duration=15,
        ratios=ALL_RATIOS,
        max_ref_images=9,
        max_ref_videos=3,
        max_ref_audios=3,
        sort=12,
    ),
    SeedanceSpec(
        model_id="cc-sd2-mini-720",
        upstream_model_id="cc-sd2-mini-720",
        category="Seedance 2.0",
        display_name="Seedance 2.0 Mini 720p",
        description="高清轻量特惠版，兼顾清晰度与低成本",
        resolutions=["720p"],
        unit="call",
        credit_price=Decimal("9.0000"),
        min_duration=4,
        max_duration=15,
        ratios=ALL_RATIOS,
        max_ref_images=9,
        max_ref_videos=3,
        max_ref_audios=3,
        sort=13,
    ),
    SeedanceSpec(
        model_id="cc-sd2-480",
        upstream_model_id="cc-sd2-480",
        category="Seedance 2.0",
        display_name="Seedance 2.0 标准 480p",
        description="标准画质特惠渠道，原生真人不卡脸",
        resolutions=["480p"],
        unit="call",
        credit_price=Decimal("21.0000"),
        min_duration=4,
        max_duration=15,
        ratios=ALL_RATIOS,
        max_ref_images=9,
        max_ref_videos=3,
        max_ref_audios=3,
        sort=14,
    ),
    SeedanceSpec(
        model_id="cc-sd2-720",
        upstream_model_id="cc-sd2-720",
        category="Seedance 2.0",
        display_name="Seedance 2.0 标准 720p",
        description="标准高清特惠渠道，人物表现与细节更均衡",
        resolutions=["720p"],
        unit="call",
        credit_price=Decimal("28.0000"),
        min_duration=4,
        max_duration=15,
        ratios=ALL_RATIOS,
        max_ref_images=9,
        max_ref_videos=3,
        max_ref_audios=3,
        sort=15,
    ),
    SeedanceSpec(
        model_id="seedance-2.0",
        upstream_model_id="sd-2-c4",
        category="Seedance 2.0",
        display_name="Seedance 2.0 C4 720p",
        description="长期稳定老牌渠道，仅支持 16:9 / 9:16 / 1:1",
        resolutions=["720p"],
        unit="call",
        credit_price=Decimal("18.0000"),
        min_duration=4,
        max_duration=15,
        ratios=BASIC_RATIOS,
        max_ref_images=9,
        max_ref_videos=3,
        max_ref_audios=3,
        sort=16,
    ),
    SeedanceSpec(
        model_id="sd-2-c5",
        upstream_model_id="sd-2-c5",
        category="Seedance 2.0",
        display_name="Seedance 2.0 C5 720p",
        description="全比例高清渠道，仅支持参考图与音频（不支持视频参考）",
        resolutions=["720p"],
        unit="call",
        credit_price=Decimal("25.0000"),
        min_duration=4,
        max_duration=15,
        ratios=ALL_RATIOS,
        max_ref_images=9,
        max_ref_videos=0,
        max_ref_audios=3,
        sort=17,
    ),
    SeedanceSpec(
        model_id="sd-2-c7",
        upstream_model_id="sd-2-c7",
        category="Seedance 2.0",
        display_name="Seedance 2.0 C7 720p",
        description="长期稳定高成功率渠道，全比例且全素材支持",
        resolutions=["720p"],
        unit="call",
        credit_price=Decimal("28.0000"),
        min_duration=4,
        max_duration=15,
        ratios=ALL_RATIOS,
        max_ref_images=9,
        max_ref_videos=3,
        max_ref_audios=3,
        sort=18,
    ),
    SeedanceSpec(
        model_id="sd-2-c8",
        upstream_model_id="sd-2-c8",
        category="Seedance 2.0",
        display_name="Seedance 2.0 C8 满血 720p",
        description="2.0 满血版本，动作与画面质感更佳（耗时略长）",
        resolutions=["720p"],
        unit="call",
        credit_price=Decimal("38.0000"),
        min_duration=4,
        max_duration=15,
        ratios=ALL_RATIOS,
        max_ref_images=9,
        max_ref_videos=3,
        max_ref_audios=3,
        sort=19,
    ),
    # ---- Seedance 2.5（10 个：6 个按秒 + 4 个按条，1 元 = 10 积分） ----
    SeedanceSpec(
        model_id="cc-sd2.5-480",
        upstream_model_id="cc-sd2.5-480",
        category="Seedance 2.5",
        display_name="Seedance 2.5 480p 按秒",
        description="2.5 特惠标清按秒计费，适合短中时长低成本试片",
        resolutions=["480p"],
        unit="second",
        credit_price=Decimal("1.9000"),
        min_duration=5,
        max_duration=30,
        ratios=ALL_RATIOS,
        max_ref_images=30,
        max_ref_videos=10,
        max_ref_audios=10,
        sort=20,
    ),
    SeedanceSpec(
        model_id="cc-sd2.5-720",
        upstream_model_id="cc-sd2.5-720",
        category="Seedance 2.5",
        display_name="Seedance 2.5 720p 按秒",
        description="2.5 特惠高清按秒计费，支持 30s 长镜头与多素材参考",
        resolutions=["720p"],
        unit="second",
        credit_price=Decimal("3.6000"),
        min_duration=5,
        max_duration=30,
        ratios=ALL_RATIOS,
        max_ref_images=30,
        max_ref_videos=10,
        max_ref_audios=10,
        sort=21,
    ),
    SeedanceSpec(
        model_id="sd-2.5-d2",
        upstream_model_id="sd-2.5-d2",
        category="Seedance 2.5",
        display_name="Seedance 2.5 D2 480p 按秒",
        description="标准标清按秒通道，支持 30 图与 10 音视频参考",
        resolutions=["480p"],
        unit="second",
        credit_price=Decimal("2.9000"),
        min_duration=5,
        max_duration=30,
        ratios=ALL_RATIOS,
        max_ref_images=30,
        max_ref_videos=10,
        max_ref_audios=10,
        sort=22,
    ),
    SeedanceSpec(
        model_id="sd-2.5-d3",
        upstream_model_id="sd-2.5-d3",
        category="Seedance 2.5",
        display_name="Seedance 2.5 D3 720p 按秒",
        description="标准高清按秒通道，适合 5–16 秒中短镜头",
        resolutions=["720p"],
        unit="second",
        credit_price=Decimal("3.9000"),
        min_duration=5,
        max_duration=30,
        ratios=ALL_RATIOS,
        max_ref_images=30,
        max_ref_videos=10,
        max_ref_audios=10,
        sort=23,
    ),
    SeedanceSpec(
        model_id="sd-2.5-d1-480",
        upstream_model_id="sd-2.5-d1-480",
        category="Seedance 2.5",
        display_name="Seedance 2.5 D1 480p 按秒",
        description="全天稳定按秒通道，支持 4 秒起生成",
        resolutions=["480p"],
        unit="second",
        credit_price=Decimal("4.7000"),
        min_duration=4,
        max_duration=30,
        ratios=ALL_RATIOS,
        max_ref_images=30,
        max_ref_videos=10,
        max_ref_audios=10,
        sort=24,
    ),
    SeedanceSpec(
        model_id="sd-2.5-d1-720",
        upstream_model_id="sd-2.5-d1-720",
        category="Seedance 2.5",
        display_name="Seedance 2.5 D1 720p 按秒",
        description="全天稳定高清按秒通道，支持 4–30 秒全范围",
        resolutions=["720p"],
        unit="second",
        credit_price=Decimal("5.4000"),
        min_duration=4,
        max_duration=30,
        ratios=ALL_RATIOS,
        max_ref_images=30,
        max_ref_videos=10,
        max_ref_audios=10,
        sort=25,
    ),
    SeedanceSpec(
        model_id="sd-2.5-f2-480",
        upstream_model_id="sd-2.5-f2-480",
        category="Seedance 2.5",
        display_name="Seedance 2.5 F2 480p 按条",
        description="长镜头按条计费更省钱（约 300s 出片，不支持视频参考）",
        resolutions=["480p"],
        unit="call",
        credit_price=Decimal("42.0000"),
        min_duration=5,
        max_duration=30,
        ratios=ALL_RATIOS,
        max_ref_images=10,
        max_ref_videos=0,
        max_ref_audios=5,
        sort=26,
    ),
    SeedanceSpec(
        model_id="sd-2.5-f2-720",
        upstream_model_id="sd-2.5-f2-720",
        category="Seedance 2.5",
        display_name="Seedance 2.5 F2 720p 按条",
        description="高清长镜头按条一口价（不支持参考视频）",
        resolutions=["720p"],
        unit="call",
        credit_price=Decimal("59.0000"),
        min_duration=5,
        max_duration=30,
        ratios=ALL_RATIOS,
        max_ref_images=10,
        max_ref_videos=0,
        max_ref_audios=5,
        sort=27,
    ),
    SeedanceSpec(
        model_id="sd-2.5-c2",
        upstream_model_id="sd-2.5-c2",
        category="Seedance 2.5",
        display_name="Seedance 2.5 C2 720p 按条",
        description="2.5 全功能高清按条一口价，超 18 秒长镜头首选",
        resolutions=["720p"],
        unit="call",
        credit_price=Decimal("62.0000"),
        min_duration=5,
        max_duration=30,
        ratios=ALL_RATIOS,
        max_ref_images=30,
        max_ref_videos=10,
        max_ref_audios=10,
        sort=28,
    ),
    SeedanceSpec(
        model_id="seedance-2.5",
        upstream_model_id="sd-2.5-c3",
        category="Seedance 2.5",
        display_name="Seedance 2.5 C3 720p 按条",
        description="2.5 全比例全功能按条通道，支持 4–30 秒长镜头",
        resolutions=["720p"],
        unit="call",
        credit_price=Decimal("77.0000"),
        min_duration=4,
        max_duration=30,
        ratios=ALL_RATIOS,
        max_ref_images=30,
        max_ref_videos=10,
        max_ref_audios=10,
        sort=29,
    ),
]


async def seed_all_seedance_models(session: AsyncSession) -> dict[str, int]:
    """幂等写入/更新全部 20 个 Seedance 模型与初始积分定价（1 元 = 10 积分）。"""
    provider = await session.scalar(select(AiProvider).where(AiProvider.key == "cc"))
    if provider is None:
        raise RuntimeError("CC provider (key='cc') not found in ai_providers")

    # 先清理原有视频默认标记，避免触发 uq_ai_models_default_media 冲突
    existing_videos = list(
        await session.scalars(select(AiModel).where(AiModel.media_type == "video"))
    )
    for row in existing_videos:
        row.is_default = False
    await session.flush()

    created = 0
    updated = 0
    for spec in SEEDANCE_SPECS:
        caps = {
            "description": spec.description,
            "resolutions": list(spec.resolutions),
            "minDuration": spec.min_duration,
            "maxDuration": spec.max_duration,
            "maxPromptChars": spec.max_prompt_chars,
            "ratios": list(spec.ratios),
            "maxReferenceImages": spec.max_ref_images,
            "maxReferenceVideos": spec.max_ref_videos,
            "maxReferenceAudios": spec.max_ref_audios,
        }
        defaults = {"resolution": spec.resolutions[0]}

        model = await session.scalar(select(AiModel).where(AiModel.id == spec.model_id))
        if model is None:
            model = AiModel(
                id=spec.model_id,
                provider_id=provider.id,
                media_type="video",
                category=spec.category,
                display_name=spec.display_name,
                upstream_model_id=spec.upstream_model_id,
                enabled=True,
                upstream_available=True,
                is_default=spec.is_default,
                sort=spec.sort,
                capabilities=caps,
                defaults=defaults,
            )
            session.add(model)
            created += 1
        else:
            model.provider_id = provider.id
            model.category = spec.category
            model.display_name = spec.display_name
            model.upstream_model_id = spec.upstream_model_id
            model.enabled = True
            model.upstream_available = True
            model.is_default = spec.is_default
            model.sort = spec.sort
            model.capabilities = caps
            model.defaults = defaults
            updated += 1

        await session.flush()

        price = await session.scalar(
            select(VideoModelPrice).where(
                VideoModelPrice.model_id == spec.model_id,
                VideoModelPrice.rule_key == "default",
            )
        )
        if price is None:
            session.add(
                VideoModelPrice(
                    model_id=spec.model_id,
                    rule_key="default",
                    unit=spec.unit,
                    credit_price=spec.credit_price,
                )
            )
        else:
            price.unit = spec.unit
            price.credit_price = spec.credit_price

    await session.commit()
    return {"created": created, "updated": updated, "total": len(SEEDANCE_SPECS)}
