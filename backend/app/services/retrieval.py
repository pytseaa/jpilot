"""Retrieval: the hard filters, then the keyword match and BM25 ordering. Plain code, Qwen is not called."""
import json
import sqlite3
from datetime import date, timedelta

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]  # the package ships no type stubs

from app.stop_words import STOP_WORDS

OPEN_DAYS = 30  # a job counts as open for 30 days after the day ingestion last saw it
RESULT_LIMIT = 20
# "it" is off the CV stop list so the keyword "IT" survives the review, but matching ignores it.
MATCH_STOP_WORDS = STOP_WORDS | {"it"}
PUNCTUATION = ".,;:!?()[]\"'"


def tokens(text):
    """Lower-case words split on spaces, with end punctuation and stop words removed."""
    words = (word.strip(PUNCTUATION) for word in text.lower().split())
    return [word for word in words if word and word not in MATCH_STOP_WORDS]


def find_qualifying(conn, keywords, employment_types):
    """The jobs that pass the hard filters and match a keyword, best first, at most RESULT_LIMIT."""
    conn.row_factory = sqlite3.Row
    jobs = [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY job_id")]
    if not jobs:  # BM25 cannot score an empty corpus
        return []
    docs = [tokens(f"{job['title'] or ''} {job['description']}") for job in jobs]
    terms = set(tokens(" ".join(keywords)))
    # The scores use the whole database, so a narrow search does not change how a job scores.
    scores = BM25Okapi(docs).get_scores(sorted(terms))
    oldest_open = (date.today() - timedelta(days=OPEN_DAYS)).isoformat()
    # Region is fixed to Hong Kong: only "other" is removed, and "unknown" stays marked Unverified.
    picked = [(score, job) for job, doc, score in zip(jobs, docs, scores)
              if terms & set(doc) and job["collected"] >= oldest_open and job["region"] != "other"
              and _has_picked_type(job, employment_types)]
    picked.sort(key=lambda pair: (-pair[0], pair[1]["job_id"]))
    return [job for _, job in picked[:RESULT_LIMIT]]


def _has_picked_type(job, picked):
    """True if the job has any picked type. A job with no type listed is unknown, so it passes."""
    types = json.loads(job["employment_types"])
    return not types or bool(set(types) & set(picked))
