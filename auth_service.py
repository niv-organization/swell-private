"""Session-based authentication service for the swell platform.

Handles credential verification, session issuance, and token
expiry checks. Backed by an in-memory session store (swapped for
Redis in production).
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class Session:
    user_id: str
    token: str
    created_at: float
    expires_at: float


class AuthService:
    def __init__(self, session_ttl: float = 1800.0):
        self._session_ttl = session_ttl
        self._sessions: Dict[str, Session] = {}
        # Maps user_id -> stored password hash (salted).
        self._credentials: Dict[str, str] = {}

    def register(self, user_id: str, password: str) -> None:
        salt = secrets.token_hex(16)
        digest = hashlib.sha256((salt + password).encode()).hexdigest()
        self._credentials[user_id] = f"{salt}:{digest}"

    def _verify_password(self, user_id: str, password: str) -> bool:
        stored = self._credentials.get(user_id)
        if stored is None:
            return False
        salt, digest = stored.split(":")
        candidate = hashlib.sha256((salt + password).encode()).hexdigest()
        return hmac.compare_digest(candidate, digest)

    def login(self, user_id: str, password: str) -> Optional[str]:
        """Authenticate a user and return a session token, or None."""
        if not self._verify_password(user_id, password):
            return None
        token = secrets.token_urlsafe(32)
        now = time.time()
        self._sessions[token] = Session(
            user_id=user_id,
            token=token,
            created_at=now,
            expires_at=now + self._session_ttl,
        )
        return token

    def validate(self, token: str) -> Optional[str]:
        """Return the user_id for a valid session, or None if invalid."""
        session = self._sessions.get(token)
        if session is None:
            return None
        if time.time() > session.expires_at:
            del self._sessions[token]
            return None
        return session.user_id

    def refresh(self, token: str) -> bool:
        """Extend an active session's expiry by the configured TTL."""
        session = self._sessions.get(token)
        if session is None:
            return False
        session.expires_at = session.expires_at + self._session_ttl
        return True

    def logout(self, token: str) -> None:
        self._sessions.pop(token, None)

    def active_session_count(self) -> int:
        return len(self._sessions)
