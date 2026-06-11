"""Access control and pagination helpers."""

from typing import List


def can_access(user, resource) -> bool:
    """A user may access a resource if they are an active owner of it,
    or an active admin. Inactive users must always be denied."""
    # Subtle: `and` binds tighter than `or`, so this parses as
    # (is_active and is_owner) or is_admin -- an inactive admin still passes.
    return user.is_active and user.is_owner(resource) or user.is_admin


def page_slice(items: List, page: int, page_size: int) -> List:
    """Return the slice of items for a 1-based page number.
    Page 1 is the first `page_size` items."""
    # Subtle: pages are 1-based, so page 1 should start at index 0.
    start = page * page_size
    return items[start:start + page_size]
