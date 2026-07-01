import random
import uuid

from .base import SupplierClient, SupplierOrderResult, SupplierProduct

_CATALOG = [
    SupplierProduct(
        supplier_sku="CJ-1001",
        title="Wireless Bone Conduction Headphones",
        description="Open-ear sport headphones with 8h battery life and IPX5 waterproofing.",
        cost=11.40,
        currency="USD",
        image_urls=["https://example-cdn.test/products/cj-1001-1.jpg"],
        category="electronics",
        shipping_cost=2.10,
        rating=4.6,
        orders_count=8200,
    ),
    SupplierProduct(
        supplier_sku="CJ-1002",
        title="LED Galaxy Star Projector",
        description="Bluetooth-enabled night light projector with nebula and starfield modes.",
        cost=9.80,
        currency="USD",
        image_urls=["https://example-cdn.test/products/cj-1002-1.jpg"],
        category="home",
        shipping_cost=3.40,
        rating=4.4,
        orders_count=15300,
    ),
    SupplierProduct(
        supplier_sku="CJ-1003",
        title="Collapsible Silicone Food Storage Set",
        description="6-piece stackable, microwave and freezer safe food containers.",
        cost=6.20,
        currency="USD",
        image_urls=["https://example-cdn.test/products/cj-1003-1.jpg"],
        category="kitchen",
        shipping_cost=2.90,
        rating=4.2,
        orders_count=610,
    ),
    SupplierProduct(
        supplier_sku="CJ-1004",
        title="Magnetic Phone Car Mount",
        description="360-degree rotation dashboard mount with 6 N52 magnets.",
        cost=3.10,
        currency="USD",
        image_urls=["https://example-cdn.test/products/cj-1004-1.jpg"],
        category="electronics",
        shipping_cost=1.50,
        rating=4.7,
        orders_count=22100,
    ),
    SupplierProduct(
        supplier_sku="CJ-1005",
        title="Posture Corrector Back Brace",
        description="Adjustable clavicle support brace for upper back posture correction.",
        cost=5.90,
        currency="USD",
        image_urls=["https://example-cdn.test/products/cj-1005-1.jpg"],
        category="health",
        shipping_cost=2.20,
        rating=3.9,
        orders_count=310,
    ),
    SupplierProduct(
        supplier_sku="CJ-1006",
        title="Mini Portable Blender Bottle",
        description="USB-C rechargeable personal blender for smoothies, 380ml.",
        cost=13.50,
        currency="USD",
        image_urls=["https://example-cdn.test/products/cj-1006-1.jpg"],
        category="kitchen",
        shipping_cost=3.80,
        rating=4.5,
        orders_count=9700,
    ),
]


class MockSupplierClient(SupplierClient):
    """In-memory stand-in for AliExpress/CJ Dropshipping, used for sandbox/demo runs."""

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self._orders: dict[str, SupplierOrderResult] = {}

    def find_trending_products(
        self, category: str | None = None, limit: int = 10
    ) -> list[SupplierProduct]:
        products = _CATALOG
        if category:
            products = [p for p in products if p.category == category]
        ranked = sorted(
            products,
            key=lambda p: p.rating * (p.orders_count**0.5),
            reverse=True,
        )
        return ranked[:limit]

    def place_order(
        self, supplier_sku: str, quantity: int, shipping_address: dict
    ) -> SupplierOrderResult:
        order_id = f"CJORD-{uuid.uuid4().hex[:10].upper()}"
        result = SupplierOrderResult(
            supplier_order_id=order_id,
            status="processing",
            tracking_number=None,
            carrier=None,
        )
        self._orders[order_id] = result
        return result

    def get_order_status(self, supplier_order_id: str) -> SupplierOrderResult:
        result = self._orders.get(supplier_order_id)
        if result is None:
            raise KeyError(f"Unknown supplier order id: {supplier_order_id}")
        if result.status == "processing":
            result.status = "shipped"
            result.tracking_number = f"TRK{self._rng.randint(10**11, 10**12 - 1)}"
            result.carrier = "ePacket"
        return result
