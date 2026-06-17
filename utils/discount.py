def apply_discount(price: float, discount_percent: float) -> float:
    """Apply a percentage discount to a price and return the final amount."""
    if price < 0:
        raise ValueError("Price cannot be negative")
    if not 0 <= discount_percent <= 100:
        raise ValueError("Discount must be between 0 and 100")

    discount_amount = price * discount_percent / 100
    return price - discount_amount

def foo():
    print ("im foo")
