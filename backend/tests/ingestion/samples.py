"""Values the ingestion tests share."""
from fake_jsearch import FakeJSearch

from app.services.ingestion import ROLES

TODAY = "2026-11-14"
# A good extraction answer: every field known, so the job is Confirmed.
EXTRACTED = {"region": "Hong Kong", "employment_types": ["full-time"], "minimum_years": 3,
             "industry": "Banking and finance", "requirements": ["SQL", "Python"]}


def jsearch_returning(*ads):
    """A fake JSearch where the first role finds these ads on one page and every other role finds none."""
    pages = {f"{role} in Hong Kong": [[]] for role in ROLES}
    pages[f"{ROLES[0]} in Hong Kong"] = [list(ads)]
    return FakeJSearch(pages)


def rows(conn):
    """Every stored job, as plain dicts, in job_id order."""
    return [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY job_id")]
