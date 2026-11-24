"""将本地已压缩的 18 张 WebP 画风图幂等上传至阿里云 OSS，并同步写入 art_styles 表。

运行方式（在 backend/ 目录）：
    uv run --locked python -m scripts.sync_art_styles_to_oss
"""

import asyncio
import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.db.session import create_engine, dispose_engine
from app.modules.art_styles.defaults import SEED_ART_STYLES
from app.modules.art_styles.models import ArtStyle
from app.modules.art_styles.service import SYSTEM_ART_STYLES_CATEGORY
from app.modules.storage.oss import load_storage

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = REPO_ROOT / "frontend" / "public" / "images" / "art-styles"


async def sync_art_styles(source_dir: Path = SOURCE_DIR) -> None:
    cfg = Settings()
    engine = create_engine(cfg)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with sessions() as session:
            storage = await load_storage(session)

            uploaded = 0
            updated = 0
            for item in SEED_ART_STYLES:
                file_path = source_dir / f"{item.code}.webp"
                if not file_path.is_file():
                    raise FileNotFoundError(f"缺少本地画风 WebP 文件：{file_path}")

                body = file_path.read_bytes()
                digest = hashlib.sha256(body).hexdigest()[:10]
                oss_key = storage.make_system_key(
                    SYSTEM_ART_STYLES_CATEGORY,
                    f"{item.code}-{digest}.webp",
                )
                oss_url = storage.public_url(oss_key)

                existing = await session.scalar(select(ArtStyle).where(ArtStyle.code == item.code))
                if existing is None or existing.image_key != oss_key:
                    storage.put_bytes(oss_key, body, "image/webp")
                    uploaded += 1

                if existing is None:
                    session.add(
                        ArtStyle(
                            code=item.code,
                            label=item.label,
                            prompt=item.prompt,
                            image_key=oss_key,
                            image_url=oss_url,
                            is_enabled=True,
                            is_default=item.is_default,
                            sort_order=item.sort_order,
                        )
                    )
                else:
                    existing.image_key = oss_key
                    existing.image_url = oss_url
                    updated += 1

            await session.commit()
            prefix_path = f"{storage.config.prefix}/system/{SYSTEM_ART_STYLES_CATEGORY}/"
            print(
                f"Synced {len(SEED_ART_STYLES)} art styles "
                f"(uploaded={uploaded}, updated={updated}, prefix={prefix_path})"
            )
    finally:
        await dispose_engine(engine)


if __name__ == "__main__":
    asyncio.run(sync_art_styles())
