import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


@dataclass
class Settings:
    shopify_store_domain: str | None
    shopify_access_token: str | None
    cj_api_email: str | None
    cj_api_key: str | None
    anthropic_api_key: str | None

    markup_multiplier: float
    min_rating: float
    min_orders_count: int
    product_category: str | None
    sourcing_interval_hours: int
    fulfillment_interval_minutes: int

    @property
    def shopify_configured(self) -> bool:
        return bool(self.shopify_store_domain and self.shopify_access_token)

    @property
    def cj_configured(self) -> bool:
        return bool(self.cj_api_email and self.cj_api_key)

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)


def load_settings() -> Settings:
    return Settings(
        shopify_store_domain=os.getenv("SHOPIFY_STORE_DOMAIN") or None,
        shopify_access_token=os.getenv("SHOPIFY_ACCESS_TOKEN") or None,
        cj_api_email=os.getenv("CJ_API_EMAIL") or None,
        cj_api_key=os.getenv("CJ_API_KEY") or None,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        markup_multiplier=_float("MARKUP_MULTIPLIER", 2.5),
        min_rating=_float("MIN_SUPPLIER_RATING", 4.3),
        min_orders_count=_int("MIN_SUPPLIER_ORDERS", 500),
        product_category=os.getenv("PRODUCT_CATEGORY") or None,
        sourcing_interval_hours=_int("SOURCING_INTERVAL_HOURS", 24),
        fulfillment_interval_minutes=_int("FULFILLMENT_INTERVAL_MINUTES", 15),
    )
