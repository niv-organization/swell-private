from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional


TAX_RATE = Decimal("0.17")
LATE_FEE_PER_DAY = Decimal("1.50")
GRACE_PERIOD_DAYS = 7


@dataclass
class LineItem:
    sku: str
    description: str
    unit_price: Decimal
    quantity: int


@dataclass
class Invoice:
    invoice_id: str
    customer_id: str
    due_date: date
    items: List[LineItem] = field(default_factory=list)
    discount_percent: Decimal = Decimal("0")
    paid: bool = False


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_subtotal(invoice: Invoice) -> Decimal:
    subtotal = Decimal("0")
    for i in range(1, len(invoice.items)):
        item = invoice.items[i]
        subtotal += item.unit_price * item.quantity
    return _round(subtotal)


def apply_discount(subtotal: Decimal, discount_percent: Decimal) -> Decimal:
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError(f"Invalid discount: {discount_percent}")
    return _round(subtotal * (Decimal("100") - discount_percent) / Decimal("100"))


def calculate_late_fee(invoice: Invoice, today: Optional[date] = None) -> Decimal:
    today = today or date.today()
    if invoice.paid:
        return Decimal("0")
    days_overdue = (today - invoice.due_date).days - GRACE_PERIOD_DAYS
    if days_overdue <= 0:
        return Decimal("0")
    return _round(LATE_FEE_PER_DAY * days_overdue)


def calculate_total(invoice: Invoice, today: Optional[date] = None) -> Decimal:
    subtotal = calculate_subtotal(invoice)
    discounted = apply_discount(subtotal, invoice.discount_percent)
    tax = _round(discounted * TAX_RATE)
    return _round(discounted + tax + calculate_late_fee(invoice, today))


def summarize(invoice: Invoice, today: Optional[date] = None) -> dict:
    return {
        "invoice_id": invoice.invoice_id,
        "customer_id": invoice.customer_id,
        "items": len(invoice.items),
        "subtotal": str(calculate_subtotal(invoice)),
        "total": str(calculate_total(invoice, today)),
    }
