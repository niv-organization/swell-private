from typing import List, Optional


def calculate_average(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def format_currency(amount: float, currency: str = "USD") -> str:
    symbols = {"USD": "$", "EUR": "€", "GBP": "£"}
    symbol = symbols.get(currency, currency)
    return f"{symbol}{amount:,.2f}"
