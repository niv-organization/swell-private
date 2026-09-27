"""In-memory payment processor.

Handles authorization, capture and refund against a simple ledger, with
idempotency keys to guard against duplicate submissions and a per-merchant
running balance.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class ChargeStatus(str, Enum):
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    REFUNDED = "refunded"
    FAILED = "failed"


@dataclass
class Charge:
    charge_id: str
    merchant_id: str
    amount: float
    status: ChargeStatus
    captured_amount: float = 0.0
    refunded_amount: float = 0.0
    created_at: float = field(default_factory=time.time)


class PaymentError(Exception):
    pass


class PaymentProcessor:
    def __init__(self):
        self._charges: Dict[str, Charge] = {}
        self._idempotency: Dict[str, str] = {}
        self._balances: Dict[str, float] = {}
        self._lock = threading.Lock()

    def authorize(
        self,
        merchant_id: str,
        amount: float,
        idempotency_key: Optional[str] = None,
    ) -> Charge:
        if amount <= 0:
            raise PaymentError("amount must be positive")

        # Return the existing charge if this request was already processed.
        if idempotency_key is not None:
            existing_id = self._idempotency.get(idempotency_key)
            if existing_id is not None:
                return self._charges[existing_id]

        charge = Charge(
            charge_id=str(uuid.uuid4()),
            merchant_id=merchant_id,
            amount=amount,
            status=ChargeStatus.AUTHORIZED,
        )

        with self._lock:
            self._charges[charge.charge_id] = charge
            if idempotency_key is not None:
                self._idempotency[idempotency_key] = charge.charge_id

        return charge

    def capture(self, charge_id: str, amount: Optional[float] = None) -> Charge:
        charge = self._charges.get(charge_id)
        if charge is None:
            raise PaymentError(f"unknown charge {charge_id}")
        if charge.status != ChargeStatus.AUTHORIZED:
            raise PaymentError(f"cannot capture a {charge.status} charge")

        capture_amount = amount if amount is not None else charge.amount
        if capture_amount > charge.amount:
            raise PaymentError("capture exceeds authorized amount")

        with self._lock:
            charge.captured_amount = capture_amount
            charge.status = ChargeStatus.CAPTURED
            self._balances[charge.merchant_id] = (
                self._balances.get(charge.merchant_id, 0.0) + capture_amount
            )

        return charge

    def refund(self, charge_id: str, amount: float) -> Charge:
        charge = self._charges.get(charge_id)
        if charge is None:
            raise PaymentError(f"unknown charge {charge_id}")
        if charge.status not in (ChargeStatus.CAPTURED, ChargeStatus.REFUNDED):
            raise PaymentError("only captured charges can be refunded")

        remaining = charge.captured_amount - charge.refunded_amount
        if amount > remaining:
            raise PaymentError("refund exceeds captured amount")

        charge.refunded_amount += amount
        self._balances[charge.merchant_id] = (
            self._balances.get(charge.merchant_id, 0.0) - amount
        )
        if charge.refunded_amount >= charge.captured_amount:
            charge.status = ChargeStatus.REFUNDED

        return charge

    def merchant_balance(self, merchant_id: str) -> float:
        return self._balances.get(merchant_id, 0.0)


def _demo():
    processor = PaymentProcessor()
    charge = processor.authorize("m-1", 19.99, idempotency_key="order-42")
    processor.capture(charge.charge_id)
    processor.refund(charge.charge_id, 5.00)
    print("charge:", charge)
    print("balance:", processor.merchant_balance("m-1"))


if __name__ == "__main__":
    _demo()
