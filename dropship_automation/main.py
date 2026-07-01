import argparse
import logging

from dropship_automation.ai.content_generator import get_content_generator
from dropship_automation.config import Settings, load_settings
from dropship_automation.pipeline.scheduler import Automation
from dropship_automation.storefront.base import StorefrontClient
from dropship_automation.storefront.mock_storefront import MockStorefrontClient
from dropship_automation.suppliers.base import SupplierClient
from dropship_automation.suppliers.mock_supplier import MockSupplierClient


def build_supplier(settings: Settings) -> SupplierClient:
    if settings.cj_configured:
        from dropship_automation.suppliers.cj_dropshipping import CJDropshippingClient

        return CJDropshippingClient(settings.cj_api_email, settings.cj_api_key)
    return MockSupplierClient()


def build_storefront(settings: Settings) -> StorefrontClient:
    if settings.shopify_configured:
        from dropship_automation.storefront.shopify_client import ShopifyClient

        return ShopifyClient(settings.shopify_store_domain, settings.shopify_access_token)
    return MockStorefrontClient()


def build_automation(settings: Settings) -> Automation:
    return Automation(
        supplier=build_supplier(settings),
        storefront=build_storefront(settings),
        content_generator=get_content_generator(settings.anthropic_api_key),
        settings=settings,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="AI dropshipping backend automation")
    parser.add_argument(
        "--once", action="store_true", help="Run one sourcing+listing+fulfillment cycle and exit"
    )
    parser.add_argument(
        "--loop", action="store_true", help="Run continuously on the configured schedule"
    )
    parser.add_argument(
        "--simulate-order",
        metavar="SKU",
        help="Inject a fake customer order for SKU into the mock storefront (sandbox mode only)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = load_settings()
    mode = "LIVE" if (settings.shopify_configured or settings.cj_configured) else "SANDBOX"
    print(f"Running in {mode} mode "
          f"(shopify_configured={settings.shopify_configured}, cj_configured={settings.cj_configured}, "
          f"anthropic_configured={settings.anthropic_configured})")

    automation = build_automation(settings)

    if args.simulate_order:
        if not isinstance(automation.storefront, MockStorefrontClient):
            raise SystemExit("--simulate-order only works against the mock storefront (sandbox mode)")
        if args.simulate_order not in automation.storefront.products_by_sku:
            automation.run_sourcing_and_listing_cycle()
        order = automation.storefront.simulate_customer_order(args.simulate_order)
        print(f"Simulated customer order {order.order_id} for SKU {args.simulate_order}")

    if args.loop:
        automation.run_forever()
    elif args.once:
        automation.run_once()
        print_summary(automation)
    elif args.simulate_order:
        automation.run_fulfillment_cycle()
        print_summary(automation)
    else:
        parser.print_help()


def print_summary(automation: Automation) -> None:
    if not isinstance(automation.storefront, MockStorefrontClient):
        return
    print("\n--- Storefront listings ---")
    for listing in automation.storefront.products_by_sku.values():
        print(f"  [{listing.sku}] {listing.title} - ${listing.price:.2f} (stock: {listing.inventory_quantity})")
    print("\n--- Orders ---")
    for order in automation.storefront.orders.values():
        items = ", ".join(f"{li.sku} x{li.quantity}" for li in order.line_items)
        print(f"  {order.order_id} [{order.fulfillment_status}] {items}")


if __name__ == "__main__":
    main()
