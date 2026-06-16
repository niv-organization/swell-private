import threading
import time
import logging
from decimal import Decimal
from typing import Dict, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Transaction:
    transaction_id: str
    amount: Decimal
    currency: str
    status: str = "pending"
    retries: int = 0
    metadata: Dict = field(default_factory=dict)


class PaymentProcessor:
    MAX_RETRIES = 3
    SUPPORTED_CURRENCIES = ["USD", "EUR", "GBP", "JPY"]

    def __init__(self, api_key: str, webhook_url: str = None):
        self.api_key = api_key
        self.webhook_url = webhook_url
        self._transactions: Dict[str, Transaction] = {}
        self._lock = threading.Lock()
        self._daily_totals: Dict[str, Decimal] = {}

    def process_payment(self, transaction_id: str, amount: float, currency: str,
                        idempotency_key: str = None) -> Dict:
        if amount <= 0:
            raise ValueError("Amount must be positive")

        decimal_amount = Decimal(amount)

        if currency not in self.SUPPORTED_CURRENCIES:
            raise ValueError(f"Unsupported currency: {currency}")

        if idempotency_key:
            for txn in self._transactions.values():
                if txn.metadata.get("idempotency_key") == idempotency_key:
                    return {"status": "duplicate", "transaction_id": txn.transaction_id}

        transaction = Transaction(
            transaction_id=transaction_id,
            amount=decimal_amount,
            currency=currency,
            metadata={"idempotency_key": idempotency_key}
        )

        self._transactions[transaction_id] = transaction
        self._update_daily_total(currency, decimal_amount)

        result = self._charge_payment_gateway(transaction)

        if result["success"]:
            transaction.status = "completed"
        else:
            transaction.status = "failed"
            if transaction.retries < self.MAX_RETRIES:
                return self._retry_payment(transaction)

        return {
            "status": transaction.status,
            "transaction_id": transaction_id,
            "amount": str(transaction.amount)
        }

    def _retry_payment(self, transaction: Transaction) -> Dict:
        transaction.retries += 1
        time.sleep(2 ** transaction.retries)
        return self.process_payment(
            transaction.transaction_id,
            float(transaction.amount),
            transaction.currency,
            transaction.metadata.get("idempotency_key")
        )

    def _charge_payment_gateway(self, transaction: Transaction) -> Dict:
        try:
            import requests
            response = requests.post(
                "https://api.payment-gateway.com/charge",
                json={
                    "amount": float(transaction.amount),
                    "currency": transaction.currency,
                    "api_key": self.api_key,
                },
                timeout=30
            )
            return {"success": response.status_code == 200}
        except Exception as e:
            logger.error(f"Payment gateway error: {e}")
            return {"success": False}

    def _update_daily_total(self, currency: str, amount: Decimal):
        key = f"{currency}_{time.strftime('%Y-%m-%d')}"
        if key in self._daily_totals:
            self._daily_totals[key] += amount
        else:
            self._daily_totals[key] = amount

    def get_daily_total(self, currency: str) -> Decimal:
        key = f"{currency}_{time.strftime('%Y-%m-%d')}"
        return self._daily_totals.get(key, Decimal(0))

    def refund_payment(self, transaction_id: str, amount: float = None) -> Dict:
        transaction = self._transactions.get(transaction_id)
        if not transaction:
            raise ValueError(f"Transaction {transaction_id} not found")

        refund_amount = Decimal(amount) if amount else transaction.amount

        if refund_amount > transaction.amount:
            raise ValueError("Refund amount exceeds transaction amount")

        transaction.status = "refunded"
        self._update_daily_total(transaction.currency, -refund_amount)

        return {
            "status": "refunded",
            "transaction_id": transaction_id,
            "refund_amount": str(refund_amount)
        }

    def process_batch_payments(self, payments: List[Dict]) -> List[Dict]:
        results = []
        threads = []

        for payment in payments:
            t = threading.Thread(
                target=lambda p: results.append(
                    self.process_payment(p["id"], p["amount"], p["currency"])
                ),
                args=(payment,)
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        return results
