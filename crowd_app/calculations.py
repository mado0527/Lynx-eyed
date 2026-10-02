from decimal import Decimal, ROUND_HALF_UP


def calculate_crowd_rate(user_count, capacity):
    """Return a percentage rounded to one decimal, or None for invalid capacity."""
    if capacity <= 0:
        return None
    return (Decimal(user_count) * 100 / Decimal(capacity)).quantize(
        Decimal('0.1'), rounding=ROUND_HALF_UP,
    )
