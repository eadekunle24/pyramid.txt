import logging

from dropship_automation.storefront.base import StorefrontClient, StoreOrder
from dropship_automation.suppliers.base import SupplierClient, SupplierOrderResult

logger = logging.getLogger(__name__)


def process_new_orders(
    storefront: StorefrontClient, supplier: SupplierClient
) -> list[tuple[StoreOrder, SupplierOrderResult]]:
    """For every unfulfilled storefront order, place the matching order with the
    supplier and mark the storefront order fulfilled once a tracking number
    is available."""
    results = []
    for order in storefront.get_new_orders():
        supplier_result = None
        for item in order.line_items:
            supplier_result = supplier.place_order(
                item.sku, item.quantity, order.shipping_address
            )
        if supplier_result is None:
            continue

        status = supplier.get_order_status(supplier_result.supplier_order_id)
        if status.tracking_number:
            storefront.mark_order_fulfilled(
                order.order_id, status.tracking_number, status.carrier or "Standard"
            )
            logger.info(
                "Order %s fulfilled via supplier order %s (tracking %s)",
                order.order_id,
                status.supplier_order_id,
                status.tracking_number,
            )
        else:
            logger.info(
                "Order %s placed with supplier (order %s), awaiting tracking number",
                order.order_id,
                status.supplier_order_id,
            )
        results.append((order, status))
    return results
