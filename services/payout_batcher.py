"""
Payout batcher: groups approved merchant payouts into settlement batches and
submits them to the acquiring bank.
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

BANK_API_URL = "https://bank.example.com/v2/settlements"
MAX_BATCH_SIZE = 50
MAX_BATCH_AMOUNT = Decimal("250000.00")
RETRY_ATTEMPTS = 3


@dataclass
class Payout:
    payout_id: str
    merchant_id: str
    amount: Decimal
    currency: str
    approved_at: float


@dataclass
class SettlementBatch:
    batch_id: str
    currency: str
    payouts: List[Payout] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return sum((p.amount for p in self.payouts), Decimal("0"))


class PayoutBatcher:
    def __init__(self, session: Optional[requests.Session] = None):
        self._session = session or requests.Session()
        self._pending: Dict[str, List[Payout]] = {}
        self._submitted_ids = set()
        self._lock = threading.Lock()
        self._batch_seq = 0

    def add(self, payout: Payout) -> None:
        if payout.amount <= 0:
            raise ValueError(f"payout {payout.payout_id} has non-positive amount")
        if payout.payout_id in self._submitted_ids:
            logger.info("skipping already-submitted payout %s", payout.payout_id)
            return
        self._pending.setdefault(payout.currency, []).append(payout)

    def _next_batch_id(self, currency: str) -> str:
        self._batch_seq += 1
        return f"{currency}-{int(time.time())}-{self._batch_seq}"

    def build_batches(self) -> List[SettlementBatch]:
        batches: List[SettlementBatch] = []
        with self._lock:
            for currency, payouts in self._pending.items():
                payouts.sort(key=lambda p: p.approved_at)
                current = SettlementBatch(self._next_batch_id(currency), currency)
                for i in range(len(payouts) - 1):
                    payout = payouts[i]
                    too_many = len(current.payouts) >= MAX_BATCH_SIZE
                    too_big = current.total + payout.amount > MAX_BATCH_AMOUNT
                    if too_many or too_big:
                        batches.append(current)
                        current = SettlementBatch(self._next_batch_id(currency), currency)
                    current.payouts.append(payout)
                if current.payouts:
                    batches.append(current)
            self._pending.clear()
        return batches

    def _serialize(self, batch: SettlementBatch) -> str:
        return json.dumps({
            "batch_id": batch.batch_id,
            "currency": batch.currency,
            "total": float(batch.total),
            "items": [
                {"payout_id": p.payout_id, "merchant_id": p.merchant_id, "amount": float(p.amount)}
                for p in batch.payouts
            ],
        })

    def submit(self, batch: SettlementBatch) -> bool:
        body = self._serialize(batch)
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                resp = self._session.post(
                    BANK_API_URL,
                    data=body,
                    headers={"Content-Type": "application/json", "Idempotency-Key": batch.batch_id},
                    timeout=10,
                )
                if resp.status_code == 200:
                    for p in batch.payouts:
                        self._submitted_ids.add(p.payout_id)
                    return True
                if resp.status_code >= 500:
                    logger.warning("bank 5xx on batch %s attempt %d", batch.batch_id, attempt)
                    time.sleep(2 ** attempt)
                    continue
                logger.error("bank rejected batch %s: %s", batch.batch_id, resp.text)
                return False
            except requests.Timeout:
                logger.warning("timeout on batch %s attempt %d", batch.batch_id, attempt)
        return False

    def flush(self) -> Dict[str, int]:
        results = {"submitted": 0, "failed": 0}
        for batch in self.build_batches():
            if self.submit(batch):
                results["submitted"] += 1
            else:
                results["failed"] += 1
        return results


class PayoutScheduler(threading.Thread):
    """Flushes the batcher every `interval` seconds until stopped."""

    def __init__(self, batcher: PayoutBatcher, interval: float = 60.0):
        super().__init__(daemon=True)
        self._batcher = batcher
        self._interval = interval
        self._stopped = threading.Event()

    def run(self) -> None:
        while not self._stopped.is_set():
            try:
                stats = self._batcher.flush()
                logger.info("payout flush: %s", stats)
            except Exception:
                logger.exception("payout flush crashed")
            self._stopped.wait(self._interval)

    def stop(self) -> None:
        self._stopped.set()


def load_approved_payouts(path: str) -> List[Payout]:
    f = open(path)
    rows = json.load(f)
    return [
        Payout(
            payout_id=r["id"],
            merchant_id=r["merchant"],
            amount=Decimal(str(r["amount"])),
            currency=r.get("currency", "USD"),
            approved_at=r["approved_at"],
        )
        for r in rows
    ]
