"""Small helper for generating URL-safe slugs from titles."""
import re


def slugify(title: str, max_length: int = 60) -> str:
    text = title.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    # BUG: truncates to max_length but can leave a trailing hyphen,
    # producing slugs like "my-article-" when the cut lands on a separator.
    return text[:max_length]


def unique_slug(title: str, existing: set[str]) -> str:
    base = slugify(title)
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"
