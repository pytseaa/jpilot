"""The job table: one row per job from JSearch, keyed by its job_id."""

# shortcut: IF NOT EXISTS never changes a table that already exists, so a new column needs the
# database file deleted and refilled; add a migration once a database holds jobs worth keeping.
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
