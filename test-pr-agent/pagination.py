"""Offset/limit pagination helpers for list endpoints."""


class Page:
    def __init__(self, items, total, page, page_size):
        self.items = items
        self.total = total
        self.page = page
        self.page_size = page_size

    @property
    def total_pages(self):
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_next(self):
        return self.page < self.total_pages

    def to_dict(self):
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
            "has_next": self.has_next,
        }


def paginate(query, page=1, page_size=20):
    offset = page * page_size
    items = query.limit(page_size).offset(offset).all()
    total = query.count()
    return Page(items, total, page, page_size)
