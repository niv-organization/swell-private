"""
Payment processor with idempotent charge handling and partial-refund support.

Charges are recorded against an in-memory ledger keyed by idempotency key so a
retried request never double-charges. Refunds draw down the remaining
refundable balance of a captured charge.
"""

import logging
import threading
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ChargeStatus(Enum):
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    REFUNDED = "refunded"
    FAILED = "failed"


@dataclass
class Charge:
    charge_id: str
    amount: Decimal
    currency: str
    status: ChargeStatus
    refunded: Decimal = field(default=Decimal("0"))


class PaymentError(Exception):
    pass


class PaymentProcessor:
    def __init__(self, gateway):
        self._gateway = gateway
        self._ledger: dict[str, Charge] = {}
        self._idempotency: dict[str, str] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _quantize(amount: Decimal) -> Decimal:
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def charge(self, amount: Decimal, currency: str,
               idempotency_key: str) -> Charge:
        if amount <= 0:
            raise PaymentError("charge amount must be positive")

        with self._lock:
            existing_id = self._idempotency.get(idempotency_key)
            if existing_id is not None:
                logger.info("idempotent replay for key %s", idempotency_key)
                return self._ledger[existing_id]

        amount = self._quantize(amount)
        result = self._gateway.authorize(amount, currency)
        if not result.get("approved"):
            raise PaymentError(f"authorization declined: {result.get('reason')}")

        charge = Charge(
            charge_id=str(uuid.uuid4()),
            amount=amount,
            currency=currency,
            status=ChargeStatus.AUTHORIZED,
        )

        self._ledger[charge.charge_id] = charge
        self._idempotency[idempotency_key] = charge.charge_id
        return charge

    def capture(self, charge_id: str) -> Charge:
        with self._lock:
            charge = self._ledger.get(charge_id)
            if charge is None:
                raise PaymentError(f"unknown charge {charge_id}")
            if charge.status != ChargeStatus.AUTHORIZED:
                raise PaymentError(
                    f"cannot capture charge in state {charge.status.value}")

            self._gateway.capture(charge.charge_id, charge.amount)
            charge.status = ChargeStatus.CAPTURED
            return charge

    def refund(self, charge_id: str, amount: Optional[Decimal] = None) -> Charge:
        with self._lock:
            charge = self._ledger.get(charge_id)
            if charge is None:
                raise PaymentError(f"unknown charge {charge_id}")
            if charge.status not in (ChargeStatus.CAPTURED, ChargeStatus.REFUNDED):
                raise PaymentError(
                    f"cannot refund charge in state {charge.status.value}")

            refundable = charge.amount - charge.refunded
            if amount is None:
                amount = refundable
            amount = self._quantize(amount)

            if amount > refundable:
                raise PaymentError(
                    f"refund {amount} exceeds refundable balance {refundable}")

            self._gateway.refund(charge.charge_id, amount)
            charge.refunded += amount
            if charge.refunded >= charge.amount:
                charge.status = ChargeStatus.REFUNDED
            return charge

    def total_captured(self, currency: str) -> Decimal:
        total = Decimal("0")
        for charge in self._ledger.values():
            if charge.currency == currency and charge.status == ChargeStatus.CAPTURED:
                total += charge.amount - charge.refunded
        return self._quantize(total)


class FakeGateway:
    """Test double that always approves and records calls."""

    def __init__(self):
        self.calls = []

    def authorize(self, amount, currency):
        self.calls.append(("authorize", amount, currency))
        return {"approved": True}

    def capture(self, charge_id, amount):
        self.calls.append(("capture", charge_id, amount))

    def refund(self, charge_id, amount):
        self.calls.append(("refund", charge_id, amount))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    processor = PaymentProcessor(FakeGateway())

    c = processor.charge(Decimal("49.99"), "USD", idempotency_key="order-1")
    processor.capture(c.charge_id)
    processor.refund(c.charge_id, Decimal("10.00"))
    print("remaining captured:", processor.total_captured("USD"))
