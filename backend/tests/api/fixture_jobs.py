"""A fixed set of jobs for the search tests. Each job's filters are known, so every result can be worked out by hand."""
import json
from datetime import date, timedelta


def make_job(job_id, *, region="Hong Kong", types=("full-time",), age=0, minimum_years=None,
             industry="unknown", title="Analyst",
             description="We need an analyst for monthly reporting."):
    """One stored job. `age` is how many days ago ingestion last saw it."""
    collected = (date.today() - timedelta(days=age)).isoformat()
    return {
        "job_id": job_id, "title": title, "description": description,
        "employer": f"Employer {job_id}", "location": "Central", "posted_date": None,
        "apply_link": f"https://jobs.example/{job_id}", "first_seen": collected,
        "collected": collected, "region": region, "employment_types": json.dumps(list(types)),
        "minimum_years": minimum_years, "industry": industry, "requirements": "[]",
        "unverified": int(region == "unknown" or not types),
    }


def fixture_jobs():
    # Nine more contractor jobs, which bring the fixed set to about 30.
    contractors = [make_job(f"c{n:02}", types=["contractor"]) for n in range(1, 10)]
    return [
        make_job("h01"),                                     # confirmed, collected today
        make_job("h02", age=29),
        make_job("h03", age=30),                             # still open: Closed means more than 30 days
        make_job("h04", age=31),                             # closed
        make_job("h05", age=90),                             # closed
        make_job("h06", types=["part-time"], age=5),
        make_job("h07", types=["contractor"], age=5),
        make_job("h08", types=["full-time", "contractor"], age=5),
        make_job("h09", region="other"),
        make_job("h10", region="other", types=["part-time"]),
        make_job("h11", region="unknown"),                   # unverified: region unknown
        make_job("h12", types=[]),                           # unverified: employment type unknown
        make_job("h13", region="unknown", types=[]),         # unverified: both unknown
        make_job("h14", region="unknown", types=["part-time"]),
        make_job("h15", region="unknown", age=40),           # unverified and closed
        make_job("h16", age=3, minimum_years=12, industry="Banking and finance"),
        make_job("h17", age=3),
        # Keyword jobs: full-time, Hong Kong, seen today. Each one tests a different matching rule.
        make_job("k-title", title="SQL developer", description="Data scripts weekly"),
        make_job("k-desc", title="Data developer", description="SQL, scripts weekly"),
        make_job("k-lower", title="Data developer", description="(python) reports weekly"),
        make_job("k-stop", title="Team lead", description="Our team cleans it weekly"),
    ] + contractors
