import logging
import time
from dataclasses import dataclass

import schedule

from dropship_automation.ai.content_generator import ContentGenerator
from dropship_automation.config import Settings
from dropship_automation.storefront.base import StorefrontClient
from dropship_automation.suppliers.base import SupplierClient

from .listing_sync import sync_listings
from .order_fulfillment import process_new_orders
from .product_sourcing import source_products

logger = logging.getLogger(__name__)


@dataclass
class Automation:
    supplier: SupplierClient
    storefront: StorefrontClient
    content_generator: ContentGenerator
    settings: Settings

    def run_sourcing_and_listing_cycle(self, limit: int = 5) -> None:
        products = source_products(
            self.supplier,
            category=self.settings.product_category,
            limit=limit,
            min_rating=self.settings.min_rating,
            min_orders_count=self.settings.min_orders_count,
        )
        sync_listings(products, self.storefront, self.content_generator, self.settings.markup_multiplier)

    def run_fulfillment_cycle(self) -> None:
        process_new_orders(self.storefront, self.supplier)

    def run_once(self, listing_limit: int = 5) -> None:
        self.run_sourcing_and_listing_cycle(limit=listing_limit)
        self.run_fulfillment_cycle()

    def run_forever(self) -> None:
        schedule.every(self.settings.sourcing_interval_hours).hours.do(
            self.run_sourcing_and_listing_cycle
        )
        schedule.every(self.settings.fulfillment_interval_minutes).minutes.do(
            self.run_fulfillment_cycle
        )
        logger.info(
            "Automation loop started: sourcing every %dh, fulfillment every %dm",
            self.settings.sourcing_interval_hours,
            self.settings.fulfillment_interval_minutes,
        )
        self.run_once()
        while True:
            schedule.run_pending()
            time.sleep(1)
