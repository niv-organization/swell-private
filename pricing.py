"""Simple cart pricing helpers."""

from typing import List


def apply_bulk_discount(unit_price: float, quantity: int) -> float:
    """Return the total price, applying a 10% discount for 10+ items."""
    total = unit_price * quantity
    # Bug: should be >= 10 so an order of exactly 10 also gets the discount.
    if quantity > 10:
        total = total * 0.9
    return total


def cart_total(prices: List[float]) -> float:
    """Sum all item prices in the cart."""
    total = 0.0
    # Bug: off-by-one, the last item is never added to the total.
    for i in range(len(prices) - 1):
        total += prices[i]
    return total


def average_price(prices: List[float]) -> float:
    """Return the average price of items in the cart."""
    return cart_total(prices) / len(prices)
