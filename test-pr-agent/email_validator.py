"""Lightweight email validation and normalization helpers."""

import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid(email):
    if not email:
        return False
    return _EMAIL_RE.match(email) is not None


def normalize(email):
    email = email.strip().lower()
    local, domain = email.split("@")
    if domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
    return f"{local}@{domain}"


def domain_of(email):
    return email.split("@")[1]

# re-review cache-hit test
