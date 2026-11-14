"""The job table: one row per JSearch ad, keyed by its job_id."""

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    title TEXT,
    description TEXT,
    employer TEXT,
    location TEXT,
    posted_date TEXT,
    apply_link TEXT,
    first_seen TEXT NOT NULL,
    collected TEXT NOT NULL,
    region TEXT NOT NULL,
    employment_types TEXT NOT NULL,
    minimum_years INTEGER,
    industry TEXT NOT NULL,
    requirements TEXT NOT NULL,
    unverified INTEGER NOT NULL
)
"""
