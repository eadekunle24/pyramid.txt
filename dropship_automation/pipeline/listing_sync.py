import logging

from dropship_automation.ai.content_generator import ContentGenerator
from dropship_automation.storefront.base import ProductListing, StorefrontClient
from dropship_automation.suppliers.base import SupplierProduct

from .pricing import calculate_price

logger = logging.getLogger(__name__)


def sync_listings(
    products: list[SupplierProduct],
    storefront: StorefrontClient,
    content_generator: ContentGenerator,
    markup_multiplier: float,
) -> list[ProductListing]:
    """Turn sourced supplier products into live storefront listings: AI-written
    copy, markup-based pricing, and inventory sync."""
    listings = []
    for product in products:
        copy = content_generator.generate_listing_copy(product)
        price = calculate_price(product.cost, product.shipping_cost, markup_multiplier)
        listing = ProductListing(
            sku=product.supplier_sku,
            title=copy.title,
            description_html=copy.description_html,
            price=price,
            image_urls=product.image_urls,
            tags=copy.tags,
        )
        storefront.upsert_product(listing)
        storefront.update_inventory(listing.sku, listing.inventory_quantity)
        logger.info("Synced listing %s (%s) at $%.2f", listing.sku, listing.title, price)
        listings.append(listing)
    return listings
