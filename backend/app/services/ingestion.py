"""Ingestion: fill the job database from JSearch. Safe to run again."""
import json
import re
from dataclasses import dataclass
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
# widen it if the first real run's dropped jobs show a miscount.
CHINESE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
EXTRACTION_KEYS = ["region", "employment_types", "minimum_years", "industry", "requirements"]
INDUSTRIES = ", ".join(f'"{name}"' for name in get_args(Industry))
INSERT = """INSERT INTO jobs (job_id, title, description, employer, location, posted_date, apply_link,
    first_seen, collected, region, employment_types, minimum_years, industry, requirements, unverified)
    VALUES (:job_id, :title, :description, :employer, :location, :posted_date, :apply_link,
    :first_seen, :collected, :region, :employment_types, :minimum_years, :industry, :requirements,
    :unverified)"""


@dataclass
class Report:
    """What one run did, in jobs. The team reads it to check the 20% Chinese threshold."""
    fetched: int = 0
    stored: int = 0
    already_stored: int = 0
    dropped_chinese: int = 0
    dropped_no_description: int = 0
    failed_extraction: int = 0
    failed_requests: int = 0


def run(search, runner, conn, today):
    """One whole ingestion run. Return its Report."""
    jobs, failed_requests = fetch_jobs(search)
    known = {job_id for (job_id,) in conn.execute("SELECT job_id FROM jobs")}
    seen_again = [job for job in jobs if job["job_id"] in known]
    # first_seen is left alone: it is the day the job was first stored.
    conn.executemany("UPDATE jobs SET collected = ? WHERE job_id = ?",
                     [(today, job["job_id"]) for job in seen_again])
    conn.commit()
    new = [job for job in jobs if job["job_id"] not in known]
    # With nothing to read, Qwen would invent a region and requirements, so the job is not stored.
    described = [job for job in new if (job.get("job_description") or "").strip()]
    english = [job for job in described if not _mostly_chinese(job["job_description"])]
    stored, failed_extraction = store_new_jobs(english, runner, conn, today)
    return Report(fetched=len(jobs), stored=stored, already_stored=len(seen_again),
                  dropped_chinese=len(described) - len(english),
                  dropped_no_description=len(new) - len(described),
                  failed_extraction=failed_extraction, failed_requests=failed_requests)


def _mostly_chinese(text):
    """True when at least 20% of the characters are Chinese. Plain code: Qwen is not asked."""
    return len(CHINESE.findall(text)) * 5 >= len(text) > 0


def fetch_jobs(search):
    """Run the planned searches. Return the jobs, each job_id once, and how many requests failed.

    A failed request ends that role's pages and the other roles are still searched."""
    jobs, failed = {}, 0
    for role in ROLES:
        cursor = None
        for page in range(PAGES_PER_ROLE):
            try:
                found, cursor = search(f"{role} in Hong Kong", cursor)
            except SearchFailed:
                failed += 1
                break
            for job in found:
                if job.get("job_id"):  # the job_id is how a stored job is recognised later
                    jobs.setdefault(job["job_id"], job)
            if cursor is None:
                break
    return list(jobs.values()), failed


def store_new_jobs(jobs, runner, conn, today):
    """Extract every job in one submission, then store the ones whose extraction worked.

    A job whose extraction fails stays unstored, so the next run tries it again. Return how many
    were stored and how many failed."""
    if not jobs:
        return 0, 0
    # shortcut: all new jobs go in one submission with each full description and no length cap, so a
    # very long description fails its call (and is retried next run), and a large batch can pass the
    # 10-minute limit in tuxiv.conf; split into batches if the first real run hits either.
    submission = [{"id": f"job-{i}", "required_keys": EXTRACTION_KEYS,
                   "prompt": prompts.JOB_EXTRACTION.format(
                       industries=INDUSTRIES, description=job.get("job_description") or "")}
                  for i, job in enumerate(jobs)]
    records = runner(submission)
    stored = failed = 0
    for i, job in enumerate(jobs):
        answer = _extracted(records[f"job-{i}"])
        if answer is None:
            failed += 1
            continue
        conn.execute(INSERT, _row(job, answer, today))
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


def _row(job, answer, today):
    # A job is Unverified when its region or its employment type is unknown (the spec's rule).
    return {
        "job_id": job["job_id"], "title": job.get("job_title"),
        "description": job.get("job_description") or "", "employer": job.get("employer_name"),
        "location": job.get("job_location"),
        "posted_date": (job.get("job_posted_at_datetime_utc") or "")[:10] or None,
        "apply_link": job.get("job_apply_link"), "first_seen": today, "collected": today,
        "region": answer.region, "employment_types": json.dumps(answer.employment_types),
        "minimum_years": answer.minimum_years, "industry": answer.industry,
        "requirements": json.dumps(answer.requirements),
        "unverified": int(answer.region == "unknown" or not answer.employment_types),
    }
