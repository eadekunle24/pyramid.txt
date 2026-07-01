import requests

from .base import OrderLineItem, ProductListing, StorefrontClient, StoreOrder

API_VERSION = "2024-04"


class ShopifyClient(StorefrontClient):
    """Live Shopify Admin REST API client.

    Requires a custom app access token with read/write scopes for
    products, inventory, and orders. Verify endpoint paths against the
    current Shopify Admin API docs before relying on this in production;
    Shopify revs API_VERSION regularly and deprecates old versions.
    """

    def __init__(self, store_domain: str, access_token: str):
        self._base_url = f"https://{store_domain}/admin/api/{API_VERSION}"
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-Shopify-Access-Token": access_token,
                "Content-Type": "application/json",
            }
        )

    def _find_product_by_sku(self, sku: str) -> dict | None:
        resp = self._session.get(
            f"{self._base_url}/products.json", params={"limit": 250}
        )
        resp.raise_for_status()
        for product in resp.json().get("products", []):
            for variant in product.get("variants", []):
                if variant.get("sku") == sku:
                    return product
        return None

    def upsert_product(self, listing: ProductListing) -> str:
        existing = self._find_product_by_sku(listing.sku)
        payload = {
            "product": {
                "title": listing.title,
                "body_html": listing.description_html,
                "tags": ", ".join(listing.tags),
                "images": [{"src": url} for url in listing.image_urls],
                "variants": [
                    {
                        "sku": listing.sku,
                        "price": f"{listing.price:.2f}",
                        "inventory_management": "shopify",
                        "inventory_quantity": listing.inventory_quantity,
                    }
                ],
            }
        }
        if existing:
            resp = self._session.put(
                f"{self._base_url}/products/{existing['id']}.json", json=payload
            )
        else:
            resp = self._session.post(f"{self._base_url}/products.json", json=payload)
        resp.raise_for_status()
        product_id = str(resp.json()["product"]["id"])
        listing.external_id = product_id
        return product_id

    def update_inventory(self, sku: str, quantity: int) -> None:
        product = self._find_product_by_sku(sku)
        if not product:
            return
        for variant in product["variants"]:
            if variant.get("sku") != sku:
                continue
            inventory_item_id = variant["inventory_item_id"]
            levels_resp = self._session.get(
                f"{self._base_url}/inventory_levels.json",
                params={"inventory_item_ids": inventory_item_id},
            )
            levels_resp.raise_for_status()
            levels = levels_resp.json().get("inventory_levels", [])
            if not levels:
                return
            location_id = levels[0]["location_id"]
            self._session.post(
                f"{self._base_url}/inventory_levels/set.json",
                json={
                    "location_id": location_id,
                    "inventory_item_id": inventory_item_id,
                    "available": quantity,
                },
            ).raise_for_status()

    def get_new_orders(self) -> list[StoreOrder]:
        resp = self._session.get(
            f"{self._base_url}/orders.json",
            params={"status": "open", "fulfillment_status": "unfulfilled"},
        )
        resp.raise_for_status()
        orders = []
        for raw in resp.json().get("orders", []):
            orders.append(
                StoreOrder(
                    order_id=str(raw["id"]),
                    customer_email=raw.get("email", ""),
                    shipping_address=raw.get("shipping_address") or {},
                    line_items=[
                        OrderLineItem(sku=li.get("sku", ""), quantity=li["quantity"])
                        for li in raw.get("line_items", [])
                    ],
                    fulfillment_status=raw.get("fulfillment_status") or "unfulfilled",
                )
            )
        return orders

    def mark_order_fulfilled(self, order_id: str, tracking_number: str, carrier: str) -> None:
        resp = self._session.post(
            f"{self._base_url}/orders/{order_id}/fulfillments.json",
            json={
                "fulfillment": {
                    "notify_customer": True,
                    "tracking_info": {
                        "number": tracking_number,
                        "company": carrier,
                    },
                }
            },
        )
        resp.raise_for_status()
