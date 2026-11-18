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
PUNCTUATION = ".,;:!?()[]\"'“”‘’"


def tokens(text):
    """Lower-case words split on spaces, with end punctuation and stop words removed."""
    words = (word.strip(PUNCTUATION) for word in text.lower().split())
    return [word for word in words if word and word not in MATCH_STOP_WORDS]


def find_qualifying(conn, keywords, employment_types, earlier=frozenset()):
    """The jobs that pass the hard filters and match a keyword, best first, at most RESULT_LIMIT.

    When more than RESULT_LIMIT jobs qualify, jobs whose id is in `earlier`, found in a previous round,
    come before every other job, so the cut cannot drop them."""
    conn.row_factory = sqlite3.Row
    # shortcut: reads the whole table and rebuilds the BM25 index on every search, fine for about 300 jobs, cache the index when the database grows.
    jobs = [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY job_id")]
    docs = [tokens(f"{job['title'] or ''} {job['description']}") for job in jobs]
    if not any(docs):  # BM25 cannot score a corpus with no words, which covers an empty database too
        return []
    terms = set(tokens(" ".join(keywords)))
    # The scores use the whole database, so a narrow search does not change how a job scores.
    scores = BM25Okapi(docs).get_scores(sorted(terms))
    oldest_open = _oldest_open()
    picked = [(score, job) for job, doc, score in zip(jobs, docs, scores)
              if terms & set(doc) and _passes_hard_filters(job, oldest_open, employment_types)]
    picked.sort(key=lambda pair: (-pair[0], pair[1]["job_id"]))
    if len(picked) > RESULT_LIMIT:  # only a cut can drop a job, so only then do earlier jobs need the front
        picked.sort(key=lambda pair: pair[1]["job_id"] not in earlier)  # stable: score order stays within each group
    return [job for _, job in picked[:RESULT_LIMIT]]


def count_passing(conn, employment_types):
    """How many jobs pass the hard filters, whether or not they match a keyword."""
    # shortcut: reads every column of the whole table just to count, fine for about 300 jobs, select only the filter columns when the database grows.
    conn.row_factory = sqlite3.Row
    oldest_open = _oldest_open()
    return sum(_passes_hard_filters(job, oldest_open, employment_types)
               for job in conn.execute("SELECT * FROM jobs"))


def _oldest_open():
    # shortcut: counts the 30 days from today, so a frozen snapshot turns Closed 30 days on, take the date from the snapshot for the evaluation.
    return (date.today() - timedelta(days=OPEN_DAYS)).isoformat()


def _passes_hard_filters(job, oldest_open, employment_types):
    # Region is fixed to Hong Kong: only "other" is removed, and "unknown" stays marked Unverified.
    return (job["collected"] >= oldest_open and job["region"] != "other"
            and _has_picked_type(job, employment_types))


def _has_picked_type(job, picked):
    """True if the job has any picked type. A job with no type listed is unknown, so it passes."""
    types = json.loads(job["employment_types"])
    return not types or bool(set(types) & set(picked))
