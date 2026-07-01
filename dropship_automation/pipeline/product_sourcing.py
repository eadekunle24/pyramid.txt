import logging

from dropship_automation.suppliers.base import SupplierClient, SupplierProduct

logger = logging.getLogger(__name__)


def source_products(
    supplier: SupplierClient,
    category: str | None,
    limit: int,
    min_rating: float,
    min_orders_count: int,
) -> list[SupplierProduct]:
    """Pull trending products from the supplier and filter out anything too
    unproven to sell reliably (low rating or low order volume)."""
    candidates = supplier.find_trending_products(category=category, limit=limit * 3)
    qualified = [
        p
        for p in candidates
        if p.rating >= min_rating and p.orders_count >= min_orders_count
    ]
    logger.info(
        "Sourced %d/%d candidates passed quality filters (min_rating=%.1f, min_orders=%d)",
        len(qualified),
        len(candidates),
        min_rating,
        min_orders_count,
    )
    return qualified[:limit]
