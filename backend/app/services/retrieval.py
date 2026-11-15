"""Retrieval: the hard filters, then the keyword match. Plain code, Qwen is not called."""
import json
import sqlite3
from datetime import date, timedelta

OPEN_DAYS = 30  # a job counts as open for 30 days after the day ingestion last saw it


def find_qualifying(conn, employment_types):
    """The jobs that qualify for a search, each as a dict of its stored columns."""
    conn.row_factory = sqlite3.Row
    oldest_open = (date.today() - timedelta(days=OPEN_DAYS)).isoformat()
    # Region is fixed to Hong Kong: only "other" is removed, and "unknown" stays marked Unverified.
    rows = conn.execute("SELECT * FROM jobs WHERE collected >= ? AND region != 'other' ORDER BY job_id",
                        (oldest_open,))
    return [dict(row) for row in rows if _has_picked_type(row, employment_types)]


def _has_picked_type(job, picked):
    """True if the job has any picked type. A job with no type listed is unknown, so it passes."""
    types = json.loads(job["employment_types"])
    return not types or bool(set(types) & set(picked))
