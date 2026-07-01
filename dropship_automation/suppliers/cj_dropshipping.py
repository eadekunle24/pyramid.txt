import requests

from .base import SupplierClient, SupplierOrderResult, SupplierProduct

API_BASE_URL = "https://developers.cjdropshipping.com/api2.0/v1"


class CJDropshippingClient(SupplierClient):
    """Live CJ Dropshipping open API client.

    Requires a CJ account with API access enabled (email + API key from
    the CJ developer portal). CJ's API surface changes over time -
    verify endpoint paths and payload shapes against the current docs
    before relying on this in production.
    """

    def __init__(self, api_email: str, api_key: str):
        self._api_email = api_email
        self._api_key = api_key
        self._session = requests.Session()
        self._access_token: str | None = None

    def _authenticate(self) -> str:
        if self._access_token:
            return self._access_token
        resp = self._session.post(
            f"{API_BASE_URL}/authentication/getAccessToken",
            json={"email": self._api_email, "password": self._api_key},
        )
        resp.raise_for_status()
        self._access_token = resp.json()["data"]["accessToken"]
        self._session.headers.update({"CJ-Access-Token": self._access_token})
        return self._access_token

    def find_trending_products(
        self, category: str | None = None, limit: int = 10
    ) -> list[SupplierProduct]:
        self._authenticate()
        params = {"pageSize": limit}
        if category:
            params["categoryName"] = category
        resp = self._session.get(f"{API_BASE_URL}/product/list", params=params)
        resp.raise_for_status()
        products = []
        for raw in resp.json().get("data", {}).get("list", []):
            products.append(
                SupplierProduct(
                    supplier_sku=raw["pid"],
                    title=raw["productNameEn"],
                    description=raw.get("description", ""),
                    cost=float(raw["sellPrice"]),
                    currency="USD",
                    image_urls=[raw.get("productImage", "")],
                    category=category or raw.get("categoryName", ""),
                    shipping_cost=float(raw.get("shippingPrice", 0)),
                    rating=float(raw.get("rating", 0)),
                    orders_count=int(raw.get("orderCount", 0)),
                )
            )
        return products

    def place_order(
        self, supplier_sku: str, quantity: int, shipping_address: dict
    ) -> SupplierOrderResult:
        self._authenticate()
        resp = self._session.post(
            f"{API_BASE_URL}/shopping/order/createOrder",
            json={
                "products": [{"vid": supplier_sku, "quantity": quantity}],
                "shippingAddress": shipping_address,
            },
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return SupplierOrderResult(
            supplier_order_id=data["orderId"],
            status=data.get("orderStatus", "processing"),
        )

    def get_order_status(self, supplier_order_id: str) -> SupplierOrderResult:
        self._authenticate()
        resp = self._session.get(
            f"{API_BASE_URL}/shopping/order/getOrderDetail",
            params={"orderId": supplier_order_id},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return SupplierOrderResult(
            supplier_order_id=supplier_order_id,
            status=data.get("orderStatus", "processing"),
            tracking_number=data.get("trackNumber"),
            carrier=data.get("logisticName"),
        )
