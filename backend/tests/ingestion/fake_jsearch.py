"""A stand-in for JSearch that needs no network: pages of jobs by query, and a log of the requests."""
from app.jsearch import SearchFailed


def job(job_id, **fields):
    """A job shaped like the ones in a real JSearch response."""
    return {"job_id": job_id, "job_title": "Data Analyst", "employer_name": "Acme",
            "job_description": "Build reports.", **fields}


class FakeJSearch:
    """Same contract as the real search: takes (query, cursor), returns (jobs, next cursor).

    A query missing from `pages` gets three pages of two jobs, so a test sees the run stop at two."""

    def __init__(self, pages=None, failing=()):
        self.pages = pages or {}
        self.failing = set(failing)  # (query, cursor) pairs that raise SearchFailed
        self.calls = []

    def __call__(self, query, cursor=None):
        self.calls.append((query, cursor))
        if (query, cursor) in self.failing:
            raise SearchFailed("the fake was told to fail")
        pages = self.pages.get(query) or [[job(f"{query}#{p}.{i}") for i in range(2)] for p in range(3)]
        index = int(cursor or 0)
        return pages[index], str(index + 1) if index + 1 < len(pages) else None
