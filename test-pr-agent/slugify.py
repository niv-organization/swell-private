"""Utility helpers for turning titles into URL-safe slugs."""

import re

_NON_WORD = re.compile(r"[^a-z0-9]+")


def slugify(title, max_length=60):
    lowered = title.lower().strip()
    slug = _NON_WORD.sub("-", lowered)
    slug = slug.strip("-")
    if len(slug) > max_length:
        slug = slug[:max_length]
    return slug


def unique_slug(title, existing):
    base = slugify(title)
    if base not in existing:
        return base
    counter = 1
    while f"{base}-{counter}" in existing:
        counter += 1
    return f"{base}-{counter}"
