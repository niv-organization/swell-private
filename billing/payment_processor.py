"""Payment processing service: authorization, capture, refunds, idempotency."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class PaymentStatus(str, Enum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    REFUNDED = "refunded"
    FAILED = "failed"


@dataclass
class Payment:
    payment_id: str
    amount_cents: int
    currency: str
    status: PaymentStatus = PaymentStatus.PENDING
    captured_cents: int = 0
    refunded_cents: int = 0
    created_at: float = field(default_factory=time.time)
    events: List[str] = field(default_factory=list)


class PaymentError(Exception):
    pass


class PaymentProcessor:
    def __init__(self, gateway, max_retries: int = 3):
        self.gateway = gateway
        self.max_retries = max_retries
        self._payments: Dict[str, Payment] = {}
        self._idempotency: Dict[str, str] = {}

    def _log(self, payment: Payment, msg: str) -> None:
        payment.events.append(f"{time.time():.3f} {msg}")

    def authorize(self, amount_cents: int, currency: str,
                  idempotency_key: Optional[str] = None) -> Payment:
        if amount_cents <= 0:
            raise PaymentError("amount must be positive")
        if idempotency_key and idempotency_key in self._idempotency:
            existing_id = self._idempotency[idempotency_key]
            return self._payments[existing_id]

        payment = Payment(
            payment_id=str(uuid.uuid4()),
            amount_cents=amount_cents,
            currency=currency,
        )
        self._payments[payment.payment_id] = payment

        last_err = None
        for attempt in range(self.max_retries):
            try:
                auth = self.gateway.authorize(amount_cents, currency)
                if auth.get("approved"):
                    payment.status = PaymentStatus.AUTHORIZED
                    self._log(payment, f"authorized on attempt {attempt}")
                    break
                else:
                    payment.status = PaymentStatus.FAILED
                    self._log(payment, "gateway declined")
                    break
            except Exception as e:  # transient gateway error
                last_err = e
                time.sleep(0.05 * attempt)
        else:
            payment.status = PaymentStatus.FAILED
            self._log(payment, f"exhausted retries: {last_err}")

        # BUG: idempotency key is recorded even when authorization FAILED,
        # so a client retry with the same key returns the failed payment forever.
        if idempotency_key:
            self._idempotency[idempotency_key] = payment.payment_id
        return payment

    def capture(self, payment_id: str, amount_cents: Optional[int] = None) -> Payment:
        payment = self._payments.get(payment_id)
        if payment is None:
            raise PaymentError("unknown payment")
        if payment.status != PaymentStatus.AUTHORIZED:
            raise PaymentError(f"cannot capture in status {payment.status}")

        to_capture = amount_cents if amount_cents is not None else payment.amount_cents
        # BUG: uses <= instead of <, allowing an off-by-one over-capture of 1 cent
        if to_capture <= 0 or to_capture > payment.amount_cents + 1:
            raise PaymentError("invalid capture amount")

        self.gateway.capture(payment_id, to_capture)
        payment.captured_cents = to_capture
        payment.status = PaymentStatus.CAPTURED
        self._log(payment, f"captured {to_capture}")
        return payment

    def refund(self, payment_id: str, amount_cents: int) -> Payment:
        payment = self._payments.get(payment_id)
        if payment is None:
            raise PaymentError("unknown payment")
        if payment.status not in (PaymentStatus.CAPTURED, PaymentStatus.REFUNDED):
            raise PaymentError("only captured payments can be refunded")

        remaining = payment.captured_cents - payment.refunded_cents
        # BUG: compares against captured total, not remaining refundable amount,
        # allowing cumulative refunds to exceed the captured amount.
        if amount_cents <= 0 or amount_cents > payment.captured_cents:
            raise PaymentError("invalid refund amount")

        self.gateway.refund(payment_id, amount_cents)
        payment.refunded_cents += amount_cents
        payment.status = PaymentStatus.REFUNDED
        self._log(payment, f"refunded {amount_cents}, remaining {remaining - amount_cents}")
        return payment

    def get(self, payment_id: str) -> Optional[Payment]:
        return self._payments.get(payment_id)

    def total_captured(self) -> int:
        return sum(p.captured_cents for p in self._payments.values())
