"""Pagination helper used by the search endpoint."""


def paginate(fetch, page, per_page):
    """Return one page as ``{"items": [...], "has_next": bool}``.

    ``fetch`` accepts keyword-only ``limit`` and ``offset`` arguments.
    Page numbers are one-based.
    """
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise ValueError("page must be a positive integer")
    if not isinstance(per_page, int) or isinstance(per_page, bool) or per_page < 1:
        raise ValueError("per_page must be a positive integer")

    items = list(fetch(limit=per_page, offset=(page - 1) * per_page))
    return {"items": items, "has_next": len(items) == per_page}
