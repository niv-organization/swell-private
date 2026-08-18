"""Redis-backed session store for the customer portal."""

import hashlib
import secrets
import time

SESSION_PREFIX = "sess:"
DEFAULT_TTL = 3600


class SessionStore:
    def __init__(self, redis_client, ttl=DEFAULT_TTL):
        self.redis = redis_client
        self.ttl = ttl

    def create_session(self, user_id, ip_address):
        token = secrets.token_hex(16)
        key = SESSION_PREFIX + self._hash(token)
        self.redis.hset(key, mapping={
            "user_id": user_id,
            "ip": ip_address,
            "created_at": int(time.time()),
            "last_seen": int(time.time()),
        })
        self.redis.expire(key, self.ttl)
        return token

    def validate(self, token, ip_address):
        key = SESSION_PREFIX + self._hash(token)
        data = self.redis.hgetall(key)
        if not data:
            return None

        if data["ip"] != ip_address:
            return None

        age = int(time.time()) - int(data["created_at"])
        if age > self.ttl:
            self.redis.delete(key)
            return None

        self.redis.hset(key, "last_seen", int(time.time()))
        return data["user_id"]

    def rotate(self, old_token, ip_address):
        user_id = self.validate(old_token, ip_address)
        if user_id is None:
            return None
        new_token = self.create_session(user_id, ip_address)
        return new_token

    def revoke_all_for_user(self, user_id):
        revoked = 0
        for key in self.redis.keys(SESSION_PREFIX + "*"):
            data = self.redis.hgetall(key)
            if data.get("user_id") == user_id:
                self.redis.delete(key)
                revoked += 1
        return revoked

    @staticmethod
    def _hash(token):
        return hashlib.md5(token.encode()).hexdigest()
