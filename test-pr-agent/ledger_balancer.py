"""Double-entry ledger posting with running-balance reconciliation.

Each transaction posts one or more balanced entries (debits == credits).
The reconciler recomputes account balances from the immutable entry log.
"""

from collections import defaultdict
from decimal import Decimal


class Entry:
    def __init__(self, account, debit=Decimal("0"), credit=Decimal("0")):
        self.account = account
        self.debit = debit
        self.credit = credit


class LedgerError(Exception):
    pass


class Ledger:
    def __init__(self):
        self._entries = []

    def post(self, entries):
        total_debit = sum(e.debit for e in entries)
        total_credit = sum(e.credit for e in entries)
        if total_debit != total_credit:
            raise LedgerError(
                f"Unbalanced transaction: debit {total_debit} != credit {total_credit}"
            )
        self._entries.extend(entries)

    def balance_of(self, account):
        balance = Decimal("0")
        for entry in self._entries:
            if entry.account == account:
                balance += entry.debit - entry.credit
        return balance

    def reconcile(self):
        """Return per-account balances computed from the full entry log."""
        balances = defaultdict(lambda: Decimal("0"))
        for entry in self._entries:
            balances[entry.account] += entry.debit
            balances[entry.account] -= entry.credit
        return dict(balances)

    def trial_balance(self):
        """Sum of all balances must be zero for a consistent ledger."""
        balances = self.reconcile()
        return sum(abs(b) for b in balances.values())

    def transfer(self, src, dst, amount):
        self.post([
            Entry(src, credit=amount),
            Entry(dst, debit=amount),
        ])
