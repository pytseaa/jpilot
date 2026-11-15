"""A fixed set of jobs for the search tests. Each job's filters are known, so every result is worked out by hand."""
import json
from datetime import date, timedelta


def _job(job_id, *, region="Hong Kong", types=("full-time",), age=0, minimum_years=None,
         industry="unknown"):
    """One stored job. `age` is how many days ago ingestion last saw it."""
    collected = (date.today() - timedelta(days=age)).isoformat()
    return {
        "job_id": job_id, "title": "Analyst",
        "description": "We need an analyst for monthly reporting.",
        "employer": f"Employer {job_id}", "location": "Central", "posted_date": None,
        "apply_link": f"https://jobs.example/{job_id}", "first_seen": collected,
        "collected": collected, "region": region, "employment_types": json.dumps(list(types)),
        "minimum_years": minimum_years, "industry": industry, "requirements": "[]",
        "unverified": int(region == "unknown" or not types),
    }


def fixture_jobs():
    return [
        _job("h01"),                                     # confirmed, collected today
        _job("h02", age=29),
        _job("h03", age=30),                             # still open: Closed means more than 30 days
        _job("h04", age=31),                             # closed
        _job("h05", age=90),                             # closed
        _job("h06", types=["part-time"], age=5),
        _job("h07", types=["contractor"], age=5),
        _job("h08", types=["full-time", "contractor"], age=5),
        _job("h09", region="other"),
        _job("h10", region="other", types=["part-time"]),
        _job("h11", region="unknown"),                   # unverified: region unknown
        _job("h12", types=[]),                           # unverified: employment type unknown
        _job("h13", region="unknown", types=[]),         # unverified: both unknown
        _job("h14", region="unknown", types=["part-time"]),
        _job("h15", region="unknown", age=40),           # unverified and closed
        _job("h16", age=3, minimum_years=12, industry="Banking and finance"),
        _job("h17", age=3),
    ]
