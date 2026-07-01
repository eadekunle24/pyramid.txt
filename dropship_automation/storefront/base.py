from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ProductListing:
    sku: str
    title: str
    description_html: str
    price: float
    image_urls: list[str]
    tags: list[str] = field(default_factory=list)
    inventory_quantity: int = 999
    external_id: str | None = None


@dataclass
class OrderLineItem:
    sku: str
    quantity: int


@dataclass
class StoreOrder:
    order_id: str
    customer_email: str
    shipping_address: dict
    line_items: list[OrderLineItem]
    fulfillment_status: str = "unfulfilled"


class StorefrontClient(ABC):
    """Common interface for any storefront (Shopify, WooCommerce, custom, etc.)."""

    @abstractmethod
    def upsert_product(self, listing: ProductListing) -> str:
        """Create or update a product listing, returning the storefront's product id."""

    @abstractmethod
    def update_inventory(self, sku: str, quantity: int) -> None:
        ...

    @abstractmethod
    def get_new_orders(self) -> list[StoreOrder]:
        ...

    @abstractmethod
    def mark_order_fulfilled(
        self, order_id: str, tracking_number: str, carrier: str
    ) -> None:
        ...
