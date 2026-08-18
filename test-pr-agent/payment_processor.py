"""Payment charge processor with idempotency handling."""

import logging
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)


class PaymentProcessor:
    def __init__(self, gateway, ledger, idempotency_store):
        self.gateway = gateway
        self.ledger = ledger
        self.idempotency_store = idempotency_store

    def charge(self, customer_id, amount, currency, idempotency_key):
        existing = self.idempotency_store.get(idempotency_key)
        if existing:
            logger.info("Replaying idempotent charge %s", idempotency_key)
            return existing

        cents = self._to_minor_units(amount)
        result = self.gateway.charge(
            customer_id=customer_id,
            amount=cents,
            currency=currency,
        )

        if result["status"] == "succeeded":
            self.ledger.record_debit(customer_id, amount, currency)
            self.idempotency_store.put(idempotency_key, result)

        return result

    def refund(self, charge_id, amount=None):
        charge = self.gateway.get_charge(charge_id)
        refund_amount = amount if amount else charge["amount"]

        if refund_amount > charge["amount"]:
            raise ValueError("Refund exceeds original charge")

        result = self.gateway.refund(charge_id, self._to_minor_units(refund_amount))
        self.ledger.record_credit(charge["customer_id"], refund_amount, charge["currency"])
        return result

    def apply_discount(self, amount, percent):
        discount = amount * Decimal(percent) / Decimal(100)
        return amount - discount

    @staticmethod
    def _to_minor_units(amount):
        quantized = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return int(quantized * 100)
