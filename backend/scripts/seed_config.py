"""初始化 FrameDrama 默认供应商、模型目录、定价与系统配置；可选从 Moonflow 数据库导入 OSS/沧元/CC 凭证。"""

import argparse
import asyncio
import os
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.session import create_engine, dispose_engine
from app.modules.catalog.models import (
    AiModel,
    AiProvider,
    ImageModelPrice,
    TextModelPrice,
    VideoModelPrice,
)
from app.modules.settings.service import (
    DEFAULT_OSS_SETTINGS,
    DEFAULT_REGISTRATION_SETTINGS,
    get_setting,
    upsert_setting,
)


async def _upsert_provider(
    session,
    *,
    key: str,
    display_name: str,
    base_url: str,
    adapter: str,
    api_key: str = "",
    auth_type: str = "bearer",
    auth_header: str | None = None,
    configuration: dict | None = None,
    overwrite_endpoint: bool = False,
) -> AiProvider:
    row = await session.scalar(select(AiProvider).where(AiProvider.key == key))
    if row is None:
        row = AiProvider(
            key=key,
            display_name=display_name,
            base_url=base_url,
            api_key=api_key,
            adapter=adapter,
            auth_type=auth_type,
            auth_header=auth_header,
            configuration=configuration or {},
        )
        session.add(row)
        await session.flush()
        return row
    if api_key:
        row.api_key = api_key
    if base_url and (overwrite_endpoint or not row.base_url or row.base_url.endswith(".example")):
        row.base_url = base_url
    if overwrite_endpoint:
        row.display_name = display_name
        row.auth_type = auth_type
        row.auth_header = auth_header
    if configuration:
        row.configuration = {**row.configuration, **configuration}
    await session.flush()
    return row


async def _upsert_model(
    session,
    *,
    model_id: str,
    provider_id: int,
    media_type: str,
    display_name: str,
    upstream_model_id: str,
    is_default: bool,
    sort: int,
    capabilities: dict,
    defaults: dict,
    parameter_bindings: dict | None = None,
) -> AiModel:
    row = await session.scalar(select(AiModel).where(AiModel.id == model_id))
    if row is None:
        row = AiModel(
            id=model_id,
            provider_id=provider_id,
            media_type=media_type,
            display_name=display_name,
            upstream_model_id=upstream_model_id,
            is_default=is_default,
            sort=sort,
            capabilities=capabilities,
            defaults=defaults,
            parameter_bindings=parameter_bindings or {},
        )
        session.add(row)
        await session.flush()
    return row


async def _import_from_moonflow(moonflow_url: str) -> dict:
    """只读读取 Moonflow 新表中的 OSS、沧元、CC 配置（不打印任何密钥）。"""
    engine = create_async_engine(moonflow_url, pool_pre_ping=True)
    imported: dict = {"oss": None, "providers": {}}
    try:
        async with engine.connect() as conn:
            oss_row = (
                await conn.execute(text("SELECT value FROM system_settings WHERE key = 'storage.oss'"))
            ).first()
            if oss_row and isinstance(oss_row[0], dict):
                oss_cfg = dict(oss_row[0])
                oss_cfg["prefix"] = "framedrama"
                imported["oss"] = oss_cfg

            provider_rows = (
                await conn.execute(
                    text(
                        "SELECT key, display_name, base_url, api_key, adapter, "
                        "auth_type, auth_header, configuration FROM ai_providers"
                    )
                )
            ).all()
            for row in provider_rows:
                adapter = row[4] or ""
                if adapter == "cangyuanImageV1":
                    imported["providers"]["cangyuan"] = {
                        "display_name": row[1] or "沧元图片",
                        "base_url": row[2],
                        "api_key": row[3] or "",
                        "auth_type": row[5] or "bearer",
                        "auth_header": row[6],
                        "configuration": row[7] or {},
                    }
                elif adapter == "ccVideoV1":
                    imported["providers"]["cc"] = {
                        "display_name": row[1] or "CC 视频",
                        "base_url": row[2],
                        "api_key": row[3] or "",
                        "auth_type": row[5] or "bearer",
                        "auth_header": row[6],
                        "configuration": row[7] or {},
                    }
    finally:
        await engine.dispose()
    return imported


async def run_seed(moonflow_url: str | None = None) -> None:
    settings = Settings()
    imported = await _import_from_moonflow(moonflow_url) if moonflow_url else {"oss": None, "providers": {}}

    engine = create_engine(settings)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            # 1. 系统配置（注册策略 + OSS）
            reg = await get_setting(session, "registration", DEFAULT_REGISTRATION_SETTINGS)
            await upsert_setting(session, "registration", reg)

            if imported["oss"]:
                await upsert_setting(session, "storage.oss", imported["oss"])
            else:
                oss = await get_setting(session, "storage.oss", DEFAULT_OSS_SETTINGS)
                await upsert_setting(session, "storage.oss", oss)

            # 2. 三大供应商：DeepSeek（文本）/ 沧元（图片）/ CC（视频）
            deepseek = await _upsert_provider(
                session,
                key="deepseek",
                display_name="DeepSeek",
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
                adapter="openai_compat",
                api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            )
            cy_cfg = imported["providers"].get("cangyuan", {})
            cangyuan = await _upsert_provider(
                session,
                key="cangyuan",
                display_name=cy_cfg.get("display_name", "沧元图片"),
                base_url=cy_cfg.get("base_url", "https://api.cangyuan.example").rstrip("/"),
                adapter="cangyuanImageV1",
                api_key=cy_cfg.get("api_key", ""),
                auth_type=cy_cfg.get("auth_type", "bearer"),
                auth_header=cy_cfg.get("auth_header"),
                configuration=cy_cfg.get("configuration", {"timeoutMs": 30000}),
                overwrite_endpoint=bool(cy_cfg),
            )
            cc_cfg = imported["providers"].get("cc", {})
            cc = await _upsert_provider(
                session,
                key="cc",
                display_name=cc_cfg.get("display_name", "CC 视频"),
                base_url=cc_cfg.get("base_url", "https://api.cc.example").rstrip("/"),
                adapter="ccVideoV1",
                api_key=cc_cfg.get("api_key", ""),
                auth_type=cc_cfg.get("auth_type", "bearer"),
                auth_header=cc_cfg.get("auth_header"),
                configuration=cc_cfg.get("configuration", {"timeoutMs": 30000}),
                overwrite_endpoint=bool(cc_cfg),
            )

            # 3. 模型目录（与确认的 V1 范围 1:1 对齐）
            ds_model = await _upsert_model(
                session,
                model_id="deepseek-flash",
                provider_id=deepseek.id,
                media_type="text",
                display_name="DeepSeek V4.1 Flash",
                upstream_model_id=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
                is_default=True,
                sort=10,
                capabilities={"billing": "token_postpaid"},
                defaults={"maxTokens": 8192},
            )
            if (
                await session.scalar(select(TextModelPrice).where(TextModelPrice.model_id == ds_model.id))
                is None
            ):
                session.add(
                    TextModelPrice(
                        model_id=ds_model.id,
                        input_price_per_million=Decimal("2.000000"),
                        cached_input_price_per_million=Decimal("0.200000"),
                        output_price_per_million=Decimal("3.000000"),
                    )
                )

            img_models = [
                ("gpt-image-2", "GPT Image 2", "gpt-image-2", True, 10),
                ("gpt-image-2.5", "GPT Image 2.5", "gpt-image-2.5", False, 20),
            ]
            default_img_prices = {
                "gpt-image-2": {"web": "1.0000", "1k": "2.0000", "2k": "4.0000", "4k": "8.0000"},
                "gpt-image-2.5": {"web": "1.5000", "1k": "3.0000", "2k": "6.0000", "4k": "12.0000"},
            }
            for model_id, name, upstream, is_def, sort in img_models:
                await _upsert_model(
                    session,
                    model_id=model_id,
                    provider_id=cangyuan.id,
                    media_type="image",
                    display_name=name,
                    upstream_model_id=upstream,
                    is_default=is_def,
                    sort=sort,
                    capabilities={
                        "tiers": ["web", "1k", "2k", "4k"],
                        "aspectRatios": {"character": "16:9", "scene": "16:9", "prop": "1:1"},
                    },
                    defaults={"tier": "1k"},
                )
                for tier, price_str in default_img_prices[model_id].items():
                    exists = await session.scalar(
                        select(ImageModelPrice).where(
                            ImageModelPrice.model_id == model_id,
                            ImageModelPrice.tier == tier,
                        )
                    )
                    if exists is None:
                        session.add(
                            ImageModelPrice(
                                model_id=model_id,
                                tier=tier,
                                credit_price=Decimal(price_str),
                            )
                        )

            vid_models = [
                ("seedance-2.0", "Seedance 2.0", "sd-2-c4", True, 10, 15, ["720p"], "720p", "2.0000"),
                ("seedance-2.5", "Seedance 2.5", "sd-2.5-c3", False, 20, 30, ["720p"], "720p", "3.0000"),
            ]
            for (
                model_id,
                name,
                upstream,
                is_def,
                sort,
                max_sec,
                resolutions,
                def_res,
                sec_price,
            ) in vid_models:
                await _upsert_model(
                    session,
                    model_id=model_id,
                    provider_id=cc.id,
                    media_type="video",
                    display_name=name,
                    upstream_model_id=upstream,
                    is_default=is_def,
                    sort=sort,
                    capabilities={
                        "maxDuration": max_sec,
                        "resolutions": resolutions,
                        "ratios": ["16:9", "9:16", "1:1"],
                    },
                    defaults={"resolution": def_res, "duration": max_sec},
                )
                exists = await session.scalar(
                    select(VideoModelPrice).where(
                        VideoModelPrice.model_id == model_id,
                        VideoModelPrice.rule_key == "default",
                    )
                )
                if exists is None:
                    session.add(
                        VideoModelPrice(
                            model_id=model_id,
                            rule_key="default",
                            unit="second",
                            credit_price=Decimal(sec_price),
                        )
                    )

            await session.commit()
    finally:
        await dispose_engine(engine)

    cy_tag = "已导入" if "cangyuan" in imported["providers"] else "模板"
    cc_tag = "已导入" if "cc" in imported["providers"] else "模板"
    print("FrameDrama 初始化配置完成：")
    print(f"- OSS 导入自 Moonflow: {'是（前缀 framedrama）' if imported['oss'] else '否（已写入空模板）'}")
    print(f"- 供应商：deepseek / cangyuan({cy_tag}) / cc({cc_tag})")
    print(
        "- 模型目录：deepseek-flash、gpt-image-2、gpt-image-2.5、seedance-2.0（≤15s）、seedance-2.5（≤30s）"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed FrameDrama providers, models, prices, and OSS config.")
    parser.add_argument(
        "--from-moonflow-url", default=None, help="可选：只读导入 Moonflow 的 OSS/沧元/CC 配置"
    )
    args = parser.parse_args()
    asyncio.run(run_seed(args.from_moonflow_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
