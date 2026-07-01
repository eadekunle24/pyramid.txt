import uuid

from .base import OrderLineItem, ProductListing, StorefrontClient, StoreOrder


class MockStorefrontClient(StorefrontClient):
    """In-memory stand-in for Shopify, used for sandbox/demo runs."""

    def __init__(self):
        self.products_by_sku: dict[str, ProductListing] = {}
        self.orders: dict[str, StoreOrder] = {}

    def upsert_product(self, listing: ProductListing) -> str:
        existing = self.products_by_sku.get(listing.sku)
        listing.external_id = existing.external_id if existing else f"PROD-{uuid.uuid4().hex[:8]}"
        self.products_by_sku[listing.sku] = listing
        return listing.external_id

    def update_inventory(self, sku: str, quantity: int) -> None:
        if sku in self.products_by_sku:
            self.products_by_sku[sku].inventory_quantity = quantity

    def get_new_orders(self) -> list[StoreOrder]:
        return [o for o in self.orders.values() if o.fulfillment_status == "unfulfilled"]

    def mark_order_fulfilled(self, order_id: str, tracking_number: str, carrier: str) -> None:
        order = self.orders.get(order_id)
        if order is None:
            raise KeyError(f"Unknown order id: {order_id}")
        order.fulfillment_status = "fulfilled"

    def simulate_customer_order(
        self, sku: str, quantity: int = 1, customer_email: str = "demo.customer@example.test"
    ) -> StoreOrder:
        """Test/demo helper: injects a fake incoming order, as if a customer just checked out."""
        order = StoreOrder(
            order_id=f"ORD-{uuid.uuid4().hex[:8].upper()}",
            customer_email=customer_email,
            shipping_address={
                "name": "Demo Customer",
                "address1": "123 Main St",
                "city": "Springfield",
                "province": "IL",
                "zip": "62701",
                "country": "US",
            },
            line_items=[OrderLineItem(sku=sku, quantity=quantity)],
        )
        self.orders[order.order_id] = order
        return order
