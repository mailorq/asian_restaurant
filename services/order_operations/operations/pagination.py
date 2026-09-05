"""bounded listing for API endpoints"""

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


def paginate(queryset, page: int, page_size: int) -> dict:
    """
    one page of a queryset, with the client's numbers clamped to a range worth serving

    the ceiling belongs here rather than in the query string: an unbounded list costs whatever
    the table has grown to, and the caller is the one paying for it least
    """
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)
    start = (page - 1) * page_size
    return {
        "items": list(queryset[start : start + page_size]),
        "total": queryset.count(),
        "page": page,
        "page_size": page_size,
    }
