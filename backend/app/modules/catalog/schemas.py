from decimal import Decimal
from typing import Any

from app.core.schemas import CamelModel


class TextModelPriceOut(CamelModel):
    input_price_per_million: Decimal
    cached_input_price_per_million: Decimal
    output_price_per_million: Decimal


class ImageModelPriceOut(CamelModel):
    tier: str
    credit_price: Decimal


class VideoModelPriceOut(CamelModel):
    rule_key: str
    unit: str
    credit_price: Decimal


class ModelCatalogItemOut(CamelModel):
    id: str
    media_type: str
    category: str = ""
    display_name: str
    is_default: bool
    capabilities: dict[str, Any]
    defaults: dict[str, Any]
    text_price: TextModelPriceOut | None = None
    image_prices: list[ImageModelPriceOut] = []
    video_prices: list[VideoModelPriceOut] = []


class ModelCatalogOut(CamelModel):
    text: list[ModelCatalogItemOut]
    image: list[ModelCatalogItemOut]
    video: list[ModelCatalogItemOut]
