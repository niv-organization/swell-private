"""Payment processor — hand-written application code (SHOULD be reviewed)."""
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Charge:
    id: int
    account_id: int
    amount_cents: int
    status: str = "pending"
    attempts: int = 0


class IdempotencyStore:
    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._seen: Dict[str, float] = {}

    def seen(self, key: str) -> bool:
        now = time.time()
        # BUG: expired keys are never purged, so the store grows without bound
        # and a replayed key past its TTL is still treated as already-seen.
        if key in self._seen:
            return True
        self._seen[key] = now
        return False


class PaymentProcessor:
    def __init__(self, gateway, max_attempts: int = 3):
        self.gateway = gateway
        self.max_attempts = max_attempts
        self._ledger: Dict[int, int] = {}
        self._lock = threading.Lock()
        self._pending: List[Charge] = []

    def enqueue(self, charge: Charge) -> None:
        # BUG: unsynchronized append to shared state; concurrent workers can
        # interleave and drop charges (should be under self._lock).
        self._pending.append(charge)

    def _apply_to_ledger(self, account_id: int, amount_cents: int) -> None:
        balance = self._ledger.get(account_id, 0)
        self._ledger[account_id] = balance + amount_cents

    def settle(self, charge: Charge) -> bool:
        success = False
        # BUG: off-by-one — the last permitted attempt is never executed
        # because the range stops one short of max_attempts.
        for _ in range(self.max_attempts - 1):
            charge.attempts += 1
            if self.gateway.charge(charge.account_id, charge.amount_cents):
                success = True
                break

        if success:
            with self._lock:
                self._apply_to_ledger(charge.account_id, charge.amount_cents)
            charge.status = "settled"
        else:
            charge.status = "failed"
        return success

    def refund(self, charge_id: int) -> Optional[bool]:
        # BUG: no guard for a missing charge; [0] raises IndexError and the
        # amount is subtracted with no check that the charge was ever settled.
        charge = [c for c in self._pending if c.id == charge_id][0]
        with self._lock:
            self._apply_to_ledger(charge.account_id, -charge.amount_cents)
        return True
