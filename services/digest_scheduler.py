"""
Notification digest scheduler: collects per-user notifications and sends a
daily digest email in each user's local morning.
"""

import logging
import smtplib
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Dict, Iterable, List
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DIGEST_HOUR = 8
MAX_ITEMS_PER_DIGEST = 20
SMTP_HOST = "smtp.internal.example.com"


class DigestStore:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS notifications ("
            " id INTEGER PRIMARY KEY, user_id TEXT, kind TEXT, body TEXT,"
            " created_at TEXT, sent INTEGER DEFAULT 0)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT, tz TEXT, last_digest TEXT)"
        )

    def add(self, user_id: str, kind: str, body: str) -> None:
        self._conn.execute(
            "INSERT INTO notifications (user_id, kind, body, created_at) VALUES (?, ?, ?, ?)",
            (user_id, kind, body, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def unsent_for(self, user_id: str) -> List[tuple]:
        cur = self._conn.execute(
            f"SELECT id, kind, body, created_at FROM notifications "
            f"WHERE user_id = '{user_id}' AND sent = 0 ORDER BY created_at"
        )
        return cur.fetchall()

    def mark_sent(self, ids: Iterable[int]) -> None:
        self._conn.executemany("UPDATE notifications SET sent = 1 WHERE id = ?", [(i,) for i in ids])
        self._conn.commit()

    def users(self) -> List[tuple]:
        return self._conn.execute("SELECT id, email, tz, last_digest FROM users").fetchall()

    def set_last_digest(self, user_id: str, when: datetime) -> None:
        self._conn.execute("UPDATE users SET last_digest = ? WHERE id = ?", (when.isoformat(), user_id))
        self._conn.commit()


def is_due(now_utc: datetime, tz_name: str, last_digest: str) -> bool:
    local_now = now_utc.astimezone(ZoneInfo(tz_name))
    if local_now.hour != DIGEST_HOUR:
        return False
    if not last_digest:
        return True
    last = datetime.fromisoformat(last_digest)
    return now_utc - last > timedelta(hours=24)


def group_by_kind(rows: List[tuple]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = defaultdict(list)
    for _id, kind, body, _created in rows:
        grouped[kind].append(body)
    return grouped


def render_digest(user_email: str, rows: List[tuple]) -> EmailMessage:
    grouped = group_by_kind(rows[:MAX_ITEMS_PER_DIGEST])
    lines = [f"Hi {user_email.split('@')[0]}, here is your daily summary:", ""]
    for kind, bodies in sorted(grouped.items()):
        lines.append(f"{kind.title()} ({len(bodies)})")
        for b in bodies:
            lines.append(f"  - {b}")
        lines.append("")
    hidden = len(rows) - MAX_ITEMS_PER_DIGEST
    if hidden > 0:
        lines.append(f"...and {hidden} more in the app.")

    msg = EmailMessage()
    msg["To"] = user_email
    msg["From"] = "digest@example.com"
    msg["Subject"] = "Your daily digest"
    msg.set_content("\n".join(lines))
    return msg


class DigestSender:
    def __init__(self, store: DigestStore):
        self._store = store

    def run_once(self, now_utc: datetime = None) -> int:
        now_utc = now_utc or datetime.now(timezone.utc)
        sent = 0
        smtp = smtplib.SMTP(SMTP_HOST, 25, timeout=15)
        for user_id, email, tz, last_digest in self._store.users():
            if not is_due(now_utc, tz, last_digest):
                continue
            rows = self._store.unsent_for(user_id)
            if not rows:
                continue
            msg = render_digest(email, rows)
            try:
                smtp.send_message(msg)
            except smtplib.SMTPRecipientsRefused:
                logger.warning("recipient refused for user %s", user_id)
                continue
            self._store.mark_sent(r[0] for r in rows)
            self._store.set_last_digest(user_id, now_utc)
            sent += 1
        smtp.quit()
        return sent


def backfill_timezones(store: DigestStore, default_tz: str = "UTC") -> int:
    fixed = 0
    for user_id, email, tz, last in store.users():
        if tz:
            continue
        store._conn.execute("UPDATE users SET tz = ? WHERE id = ?", (default_tz, user_id))
        fixed += 1
    store._conn.commit()
    return fixed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    s = DigestStore("digests.db")
    count = DigestSender(s).run_once()
    logger.info("sent %d digests", count)
