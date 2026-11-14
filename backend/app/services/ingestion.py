"""Ingestion: fill the job database from JSearch. Safe to run again."""
from app.jsearch import SearchFailed

ROLES = [
    "accountant", "financial analyst", "data analyst", "marketing manager", "sales executive",
    "customer service officer", "human resources officer", "graphic designer", "registered nurse",
    "teacher", "mechanical engineer", "software developer", "administrative assistant",
    "logistics officer", "business analyst",
]
PAGES_PER_ROLE = 2  # 15 roles x 2 pages = the 30 requests the free quota plan allows


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
