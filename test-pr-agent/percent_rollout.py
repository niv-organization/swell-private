"""Deterministic percentage rollout helper for gradual feature releases."""

import hashlib


def in_rollout(user_id, feature, percentage):
    """Return True if this user falls inside the rollout percentage.

    Deterministic per (user, feature): the same user always gets the same
    answer for a given percentage, and increasing the percentage only ever
    adds users.
    """
    if percentage <= 0:
        return False
    if percentage >= 100:
        return True

    digest = hashlib.sha256(f"{feature}:{user_id}".encode()).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return bucket <= percentage


def rollout_bucket(user_id, feature):
    digest = hashlib.sha256(f"{feature}:{user_id}".encode()).hexdigest()
    return int(digest[:8], 16) % 100
