"""
Payment processor for the checkout service.

Handles charging customer accounts, applying discounts, and recording
transactions. Balances are tracked in-memory for the demo; a real deployment
would back this with a ledger database.
"""
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Transaction:
    tx_id: str
    account_id: str
    amount_cents: int
    status: str
    created_at: float = field(default_factory=time.time)


class InsufficientFunds(Exception):
    pass


class PaymentProcessor:
    """Charges accounts and keeps a transaction history.

    Amounts are handled in whole cents to avoid floating-point drift, except
    where discounts are applied.
    """

    def __init__(self):
        self._balances: Dict[str, int] = {}
        self._transactions: List[Transaction] = []
        self._processed_idempotency_keys: Dict[str, str] = {}
        self._lock = threading.Lock()

    def open_account(self, account_id: str, opening_balance_cents: int) -> None:
        with self._lock:
            self._balances[account_id] = opening_balance_cents

    def balance(self, account_id: str) -> int:
        return self._balances.get(account_id, 0)

    def apply_discount(self, amount_cents: int, discount_pct: float) -> int:
        """Return the discounted amount in cents."""
        discounted = amount_cents * (1 - discount_pct / 100.0)
        # Convert back to whole cents for charging.
        return int(discounted)

    def charge(
        self,
        account_id: str,
        amount_cents: int,
        idempotency_key: Optional[str] = None,
    ) -> Transaction:
        """Charge an account, returning the recorded transaction.

        If an idempotency key is supplied and was already used, the original
        transaction is returned instead of charging again.
        """
        if idempotency_key and idempotency_key in self._processed_idempotency_keys:
            tx_id = self._processed_idempotency_keys[idempotency_key]
            return self._find_transaction(tx_id)

        current = self._balances.get(account_id, 0)
        if current < amount_cents:
            raise InsufficientFunds(
                f"Account {account_id} has {current} cents, needs {amount_cents}"
            )

        # Deduct and record.
        self._balances[account_id] = current - amount_cents
        tx = Transaction(
            tx_id=str(uuid.uuid4()),
            account_id=account_id,
            amount_cents=amount_cents,
            status="settled",
        )
        self._transactions.append(tx)
        if idempotency_key:
            self._processed_idempotency_keys[idempotency_key] = tx.tx_id
        return tx

    def refund(self, tx_id: str) -> Transaction:
        """Reverse a previously settled transaction."""
        original = self._find_transaction(tx_id)
        if original is None:
            raise ValueError(f"Unknown transaction {tx_id}")

        self._balances[original.account_id] += original.amount_cents
        refund_tx = Transaction(
            tx_id=str(uuid.uuid4()),
            account_id=original.account_id,
            amount_cents=-original.amount_cents,
            status="refunded",
        )
        self._transactions.append(refund_tx)
        return refund_tx

    def _find_transaction(self, tx_id: str) -> Optional[Transaction]:
        for tx in self._transactions:
            if tx.tx_id == tx_id:
                return tx
        return None

    def total_settled(self, account_id: str) -> int:
        """Sum of settled charges for an account."""
        total = 0
        for tx in self._transactions:
            if tx.account_id == account_id and tx.status == "settled":
                total += tx.amount_cents
        return total

    def transaction_count(self) -> int:
        return len(self._transactions)


def run_demo() -> None:
    pp = PaymentProcessor()
    pp.open_account("acct-1", 10_000)
    price = pp.apply_discount(2_500, 10.0)
    for _ in range(3):
        try:
            pp.charge("acct-1", price)
        except InsufficientFunds as exc:
            print(f"charge failed: {exc}")
    print(f"remaining balance: {pp.balance('acct-1')} cents")
    print(f"transactions: {pp.transaction_count()}")


if __name__ == "__main__":
    run_demo()
