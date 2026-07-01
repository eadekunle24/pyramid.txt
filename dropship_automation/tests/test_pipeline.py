from dropship_automation.ai.content_generator import TemplateContentGenerator
from dropship_automation.config import Settings
from dropship_automation.pipeline.listing_sync import sync_listings
from dropship_automation.pipeline.order_fulfillment import process_new_orders
from dropship_automation.pipeline.pricing import calculate_price
from dropship_automation.pipeline.product_sourcing import source_products
from dropship_automation.pipeline.scheduler import Automation
from dropship_automation.storefront.mock_storefront import MockStorefrontClient
from dropship_automation.suppliers.mock_supplier import MockSupplierClient


def make_settings(**overrides) -> Settings:
    base = dict(
        shopify_store_domain=None,
        shopify_access_token=None,
        cj_api_email=None,
        cj_api_key=None,
        anthropic_api_key=None,
        markup_multiplier=2.5,
        min_rating=4.0,
        min_orders_count=500,
        product_category=None,
        sourcing_interval_hours=24,
        fulfillment_interval_minutes=15,
    )
    base.update(overrides)
    return Settings(**base)


def test_calculate_price_applies_markup_and_rounds_to_99_cents():
    price = calculate_price(cost=7.0, shipping_cost=1.0, markup_multiplier=3.0)
    assert price == 24.99


def test_source_products_filters_out_low_quality_candidates():
    supplier = MockSupplierClient()
    products = source_products(
        supplier, category=None, limit=10, min_rating=4.5, min_orders_count=1000
    )
    assert all(p.rating >= 4.5 and p.orders_count >= 1000 for p in products)
    assert len(products) > 0
    assert all(p.supplier_sku != "CJ-1003" for p in products)  # low rating/orders


def test_sync_listings_creates_storefront_products_with_markup_pricing():
    supplier = MockSupplierClient()
    storefront = MockStorefrontClient()
    generator = TemplateContentGenerator()

    products = source_products(supplier, None, limit=3, min_rating=4.0, min_orders_count=500)
    listings = sync_listings(products, storefront, generator, markup_multiplier=2.5)

    assert len(listings) == len(products)
    for listing in listings:
        assert listing.sku in storefront.products_by_sku
        assert storefront.products_by_sku[listing.sku].price == listing.price
        assert listing.title
        assert listing.description_html


def test_process_new_orders_places_supplier_order_and_fulfills_storefront_order():
    supplier = MockSupplierClient(seed=1)
    storefront = MockStorefrontClient()
    generator = TemplateContentGenerator()

    products = source_products(supplier, None, limit=1, min_rating=4.0, min_orders_count=500)
    sync_listings(products, storefront, generator, markup_multiplier=2.5)
    sku = products[0].supplier_sku

    order = storefront.simulate_customer_order(sku, quantity=2)
    assert order.fulfillment_status == "unfulfilled"

    results = process_new_orders(storefront, supplier)

    assert len(results) == 1
    fulfilled_order, supplier_result = results[0]
    assert fulfilled_order.order_id == order.order_id
    assert supplier_result.tracking_number is not None
    assert storefront.orders[order.order_id].fulfillment_status == "fulfilled"


def test_automation_run_once_sources_lists_and_fulfills_end_to_end():
    settings = make_settings()
    automation = Automation(
        supplier=MockSupplierClient(),
        storefront=MockStorefrontClient(),
        content_generator=TemplateContentGenerator(),
        settings=settings,
    )
    automation.run_sourcing_and_listing_cycle(limit=3)
    assert len(automation.storefront.products_by_sku) > 0

    sku = next(iter(automation.storefront.products_by_sku))
    automation.storefront.simulate_customer_order(sku)
    automation.run_fulfillment_cycle()

    assert all(o.fulfillment_status == "fulfilled" for o in automation.storefront.orders.values())
