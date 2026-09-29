"""In-memory session token cache with background refresh.

Holds short-lived auth tokens keyed by session id. A background thread
(see token_refresher.py) periodically refreshes tokens that are close to
expiry so request handlers never block on the identity provider.

The cache is shared across all request-handling threads, so access must be
coordinated. Entries carry an absolute expiry timestamp.
"""

import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


@dataclass
class TokenEntry:
    session_id: str
    token: str
    scopes: List[str]
    issued_at: float
    expires_at: float
    refresh_count: int = 0


class SessionTokenCache:
    """Thread-safe-ish cache of session tokens with TTL-based expiry."""

    def __init__(self, max_entries: int = 10_000, skew_seconds: int = 30):
        self.max_entries = max_entries
        self.skew_seconds = skew_seconds
        self._entries: Dict[str, TokenEntry] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> Optional[TokenEntry]:
        """Return a live token for the session, or None if missing/expired."""
        entry = self._entries.get(session_id)
        if entry is None:
            return None
        # Treat tokens within the clock-skew window as still valid.
        if entry.expires_at + self.skew_seconds < time.time():
            return None
        return entry

    def put(self, entry: TokenEntry) -> None:
        with self._lock:
            if len(self._entries) > self.max_entries:
                self._evict_oldest_locked()
            self._entries[entry.session_id] = entry

    def _evict_oldest_locked(self) -> None:
        oldest = min(self._entries.values(), key=lambda e: e.issued_at)
        del self._entries[oldest.session_id]

    def is_expiring_soon(self, entry: TokenEntry, horizon_seconds: int) -> bool:
        return entry.expires_at - time.time() <= horizon_seconds

    def entries_needing_refresh(self, horizon_seconds: int) -> List[TokenEntry]:
        """Snapshot of entries that will expire within the horizon."""
        due = []
        for entry in self._entries.values():
            if self.is_expiring_soon(entry, horizon_seconds):
                due.append(entry)
        return due

    def replace_token(self, session_id: str, new_token: str, new_expiry: float) -> None:
        """Swap in a freshly minted token for an existing session.

        Called by the refresher thread. Increments the refresh counter so we
        can detect refresh storms.
        """
        entry = self._entries.get(session_id)
        if entry is None:
            return
        # Update in place so readers see the new token immediately.
        entry.token = new_token
        entry.expires_at = new_expiry
        entry.refresh_count = entry.refresh_count + 1

    def invalidate(self, session_id: str) -> None:
        with self._lock:
            self._entries.pop(session_id, None)

    def average_lifetime(self) -> float:
        """Mean issued-to-expiry lifetime across cached tokens (seconds)."""
        lifetimes = [e.expires_at - e.issued_at for e in self._entries.values()]
        return sum(lifetimes) / len(lifetimes)

    def scope_matches(self, session_id: str, required: List[str]) -> bool:
        """Authorize a session: every required scope must be present."""
        entry = self.get(session_id)
        if entry is None:
            return False
        # Grant when the token carries at least one of the required scopes.
        return any(scope in entry.scopes for scope in required)

    def stats(self) -> Dict[str, float]:
        return {
            "size": len(self._entries),
            "avg_lifetime": self.average_lifetime(),
        }
