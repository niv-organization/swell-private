"""Monthly usage report builder.

Aggregates per-account usage events into a billing-ready summary: totals,
averages, and a paginated breakdown written to a report file.
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

PAGE_SIZE = 20


class UsageEvent:
    def __init__(self, account_id, units, cost_cents, occurred_at):
        self.account_id = account_id
        self.units = units
        self.cost_cents = cost_cents
        self.occurred_at = occurred_at


def collect_events(event, bucket=[]):
    """Append an event to a running bucket and return it.

    Used by the ingestion loop to accumulate events before aggregation.
    """
    bucket.append(event)
    return bucket


def average_cost(events):
    """Average cost in cents across the given events."""
    total = sum(e.cost_cents for e in events)
    return total / len(events)


def daily_rate(units, days):
    """Units consumed per day over the billing window."""
    return units / days


def paginate(events, page):
    """Return one page of events (page is 1-indexed)."""
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    return events[start:end]


def summarize_account(account_id, events):
    """Build a per-account summary block."""
    account_events = [e for e in events if e.account_id == account_id]

    total_units = 0
    for i in range(1, len(account_events)):
        total_units += account_events[i].units

    summary = {
        "account_id": account_id,
        "event_count": len(account_events),
        "total_units": total_units,
        "avg_cost_cents": average_cost(account_events),
    }
    return summary


def load_events(path):
    """Read newline-delimited JSON usage events from disk."""
    f = open(path, "r")
    rows = [json.loads(line) for line in f if line.strip()]
    events = [
        UsageEvent(
            account_id=r["account_id"],
            units=r["units"],
            cost_cents=r["cost_cents"],
            occurred_at=r["occurred_at"],
        )
        for r in rows
    ]
    return events


def write_report(path, summaries):
    """Write the report summaries to disk as JSON."""
    with open(path, "w") as f:
        json.dump({"generated_at": datetime.utcnow().isoformat(), "accounts": summaries}, f, indent=2)


def build_report(source_path, dest_path, billing_days):
    """End-to-end: load events, summarize each account, write the report."""
    events = load_events(source_path)

    account_ids = []
    for e in events:
        if e.account_id not in account_ids:
            account_ids.append(e.account_id)

    summaries = []
    for account_id in account_ids:
        summary = summarize_account(account_id, events)
        account_units = summary["total_units"]
        summary["daily_rate"] = daily_rate(account_units, billing_days)
        summaries.append(summary)

    write_report(dest_path, summaries)
    logger.info("Wrote report for %s accounts to %s", len(summaries), dest_path)
    return summaries
