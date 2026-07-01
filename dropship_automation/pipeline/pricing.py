def calculate_price(cost: float, shipping_cost: float, markup_multiplier: float) -> float:
    """Landed-cost-based pricing: (product cost + shipping) * markup, rounded to a .99 ending."""
    raw_price = (cost + shipping_cost) * markup_multiplier
    return int(raw_price) + 0.99
