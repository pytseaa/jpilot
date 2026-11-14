"""Ingestion: fill the job database from JSearch. Safe to run again."""
import json
from typing import get_args

from pydantic import ValidationError

from app import prompts
from app.jsearch import SearchFailed
from app.schemas.job import JobExtractionAnswer
from app.schemas.search_request import Industry

ROLES = [
    "accountant", "financial analyst", "data analyst", "marketing manager", "sales executive",
    "customer service officer", "human resources officer", "graphic designer", "registered nurse",
    "teacher", "mechanical engineer", "software developer", "administrative assistant",
    "logistics officer", "business analyst",
]
PAGES_PER_ROLE = 2  # 15 roles x 2 pages = the 30 requests the free quota plan allows
EXTRACTION_KEYS = ["region", "employment_types", "minimum_years", "industry", "requirements"]
INDUSTRIES = ", ".join(f'"{name}"' for name in get_args(Industry))
INSERT = """INSERT INTO jobs (job_id, title, description, employer, location, posted_date, apply_link,
    first_seen, collected, region, employment_types, minimum_years, industry, requirements, unverified)
    VALUES (:job_id, :title, :description, :employer, :location, :posted_date, :apply_link,
    :first_seen, :collected, :region, :employment_types, :minimum_years, :industry, :requirements,
    :unverified)"""


def fetch_ads(search):
    """Run the planned searches. Return the ads, each job_id once, and how many requests failed.

    A failed request ends that role's pages and the other roles are still searched."""
    ads, failed = {}, 0
    for role in ROLES:
        cursor = None
        for page in range(PAGES_PER_ROLE):
            try:
                found, cursor = search(f"{role} in Hong Kong", cursor)
            except SearchFailed:
                failed += 1
                break
            for ad in found:
                if ad.get("job_id"):  # the job_id is how a stored ad is recognised later
                    ads.setdefault(ad["job_id"], ad)
            if cursor is None:
                break
    return list(ads.values()), failed


def store_new_ads(ads, runner, conn, today):
    """Extract every ad in one submission, then store the ones whose extraction worked.

    An ad whose extraction fails stays unstored, so the next run tries it again. Return how many
    were stored and how many failed."""
    if not ads:
        return 0, 0
    submission = [{"id": f"ad-{i}", "required_keys": EXTRACTION_KEYS,
                   "prompt": prompts.JOB_EXTRACTION.format(
                       industries=INDUSTRIES, description=ad.get("job_description") or "")}
                  for i, ad in enumerate(ads)]
    records = runner(submission)
    stored = failed = 0
    for i, ad in enumerate(ads):
        answer = _extracted(records[f"ad-{i}"])
        if answer is None:
            failed += 1
            continue
        conn.execute(INSERT, _row(ad, answer, today))
        stored += 1
    conn.commit()
    return stored, failed


def _extracted(record):
    """The checked answer, or None when the call failed or the answer is not what the prompt asked for."""
    if record["status"] != "ok":
        return None
    try:
        return JobExtractionAnswer.model_validate(record["answer"])
    except ValidationError:
        return None


def _row(ad, answer, today):
    # A job is Unverified when its region or its employment type is unknown (the spec's rule).
    return {
        "job_id": ad["job_id"], "title": ad.get("job_title"),
        "description": ad.get("job_description") or "", "employer": ad.get("employer_name"),
        "location": ad.get("job_location"),
        "posted_date": (ad.get("job_posted_at_datetime_utc") or "")[:10] or None,
        "apply_link": ad.get("job_apply_link"), "first_seen": today, "collected": today,
        "region": answer.region, "employment_types": json.dumps(answer.employment_types),
        "minimum_years": answer.minimum_years, "industry": answer.industry,
        "requirements": json.dumps(answer.requirements),
        "unverified": int(answer.region == "unknown" or not answer.employment_types),
    }
