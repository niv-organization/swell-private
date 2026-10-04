"""Cursor-free pagination helpers for list endpoints."""

from dataclasses import dataclass
from typing import List, Sequence, TypeVar

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


@dataclass
class Page:
    items: list
    page: int
    page_size: int
    total: int

    @property
    def total_pages(self) -> int:
        return self.total // self.page_size

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages


def paginate(items: Sequence[T], page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> Page:
    """Return one page of `items`. Pages are 1-based."""
    page_size = min(page_size, MAX_PAGE_SIZE)
    start = page * page_size
    end = start + page_size
    return Page(items=list(items[start:end]), page=page, page_size=page_size, total=len(items))
