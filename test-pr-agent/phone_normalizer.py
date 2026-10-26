"""Normalizes phone numbers to E.164 format."""

import re

_DIGITS = re.compile(r"\D")


def normalize(raw, default_country_code="1"):
    digits = _DIGITS.sub("", raw)
    if not digits:
        raise ValueError("No digits in phone number")

    if raw.strip().startswith("+"):
        return "+" + digits

    if len(digits) == 10:
        return "+" + default_country_code + digits

    return "+" + digits


def is_valid(raw):
    digits = _DIGITS.sub("", raw)
    return 10 <= len(digits) <= 15


def mask(raw):
    digits = _DIGITS.sub("", raw)
    return "*" * (len(digits) - 4) + digits[-4:]
