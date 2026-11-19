"""Reference implementation for the pagination task."""


def paginate(fetch, page, per_page):
    """Return a bounded page and whether another row exists."""
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise ValueError("page must be a positive integer")
    if not isinstance(per_page, int) or isinstance(per_page, bool) or per_page < 1:
        raise ValueError("per_page must be a positive integer")
    rows = list(fetch(limit=per_page + 1, offset=(page - 1) * per_page))
    return {"items": rows[:per_page], "has_next": len(rows) > per_page}
