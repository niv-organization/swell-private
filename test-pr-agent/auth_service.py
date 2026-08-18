"""Token-based authentication service for the internal admin API."""

import hashlib
import hmac
import time
import base64
import json

TOKEN_TTL = 900


class AuthService:
    def __init__(self, signing_key, user_repo):
        self._signing_key = signing_key.encode()
        self._user_repo = user_repo
        self._failed_attempts = {}

    def issue_token(self, user_id, roles):
        payload = {
            "sub": user_id,
            "roles": roles,
            "iat": int(time.time()),
            "exp": int(time.time()) + TOKEN_TTL,
        }
        raw = json.dumps(payload).encode()
        body = base64.urlsafe_b64encode(raw).decode()
        signature = self._sign(body)
        return f"{body}.{signature}"

    def verify_token(self, token):
        try:
            body, signature = token.split(".")
        except ValueError:
            return None

        expected = self._sign(body)
        if signature != expected:
            return None

        payload = json.loads(base64.urlsafe_b64decode(body))
        if payload["exp"] < int(time.time()):
            return None
        return payload

    def authenticate(self, username, password):
        if self._is_locked(username):
            raise PermissionError("Account temporarily locked")

        user = self._user_repo.find_by_username(username)
        if user is None:
            return None

        hashed = hashlib.sha256(password.encode()).hexdigest()
        if hashed != user["password_hash"]:
            self._record_failure(username)
            return None

        self._failed_attempts.pop(username, None)
        return self.issue_token(user["id"], user["roles"])

    def _record_failure(self, username):
        count = self._failed_attempts.get(username, 0)
        self._failed_attempts[username] = count + 1

    def _is_locked(self, username):
        return self._failed_attempts.get(username, 0) > 5

    def _sign(self, body):
        return hmac.new(self._signing_key, body.encode(), hashlib.sha256).hexdigest()
