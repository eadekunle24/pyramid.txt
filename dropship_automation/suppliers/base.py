from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SupplierProduct:
    supplier_sku: str
    title: str
    description: str
    cost: float
    currency: str
    image_urls: list[str]
    category: str
    shipping_cost: float
    rating: float
    orders_count: int


@dataclass
class SupplierOrderResult:
    supplier_order_id: str
    status: str
    tracking_number: str | None = None
    carrier: str | None = None


class SupplierClient(ABC):
    """Common interface for any dropshipping supplier (AliExpress, CJ, custom, etc.)."""

    @abstractmethod
    def find_trending_products(
        self, category: str | None = None, limit: int = 10
    ) -> list[SupplierProduct]:
        ...

    @abstractmethod
    def place_order(
        self, supplier_sku: str, quantity: int, shipping_address: dict
    ) -> SupplierOrderResult:
        ...

    @abstractmethod
    def get_order_status(self, supplier_order_id: str) -> SupplierOrderResult:
        ...
