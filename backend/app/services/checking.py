"""Checking: Qwen grades each qualifying job against the CV, and only claims whose quotes are found are kept."""
import re

from pydantic import ValidationError

from app import prompts
from app.schemas.check import CheckAnswer, Claim

CHECK_KEYS = ["grade", "claims"]


def check_jobs(jobs, cv_text, summary, runner):
    """One submission with one prompt per job. Return the jobs worth showing and the dropped-claim count.

    A job comes back with its grade and its verified claims. Grade 0 jobs, jobs whose call failed or whose
    answer is not what the prompt asked for, and jobs with no verified claim left are left out."""
    if not jobs:
        return [], 0
    submission = [{"id": f"check-{i}", "required_keys": CHECK_KEYS,
                   "prompt": prompts.CHECK.format(cv_summary=summary, cv_text=cv_text,
                                                  description=job["description"])}
                  for i, job in enumerate(jobs)]
    records = runner(submission)
    checked, dropped = [], 0
    for i, job in enumerate(jobs):
        answer = _answer(records[f"check-{i}"])
        if answer is None or answer.grade == 0:
            continue
        verified, unverified = _verified(answer.claims, cv_text, job["description"])
        dropped += unverified
        if verified:
            checked.append({**job, "grade": answer.grade, "claims": [c.model_dump() for c in verified]})
    return checked, dropped


def _answer(record):
    """The checked answer, or None when the call failed or the answer is not what the prompt asked for."""
    if record["status"] != "ok":
        return None
    try:
        return CheckAnswer.model_validate(record["answer"])
    except ValidationError:
        return None


def _verified(raw_claims, cv_text, description):
    """The claims whose quotes are found in the CV text and in the job's description, and how many were not.

    The CV summary and the requirements list never take part: only source text can verify a quote.
    A claim with a missing or unusable field is dropped, and Qwen is not asked to fix it."""
    verified, dropped = [], 0
    for raw in raw_claims:
        try:
            claim = Claim.model_validate(raw)
        except ValidationError:
            dropped += 1
            continue
        if _found(claim.cv_quote, cv_text) and _found(claim.job_quote, description):
            verified.append(claim)
        else:
            dropped += 1
    return verified, dropped


def _found(quote, source):
    """True when the quote is in the source as whole words, ignoring letter case and spacing."""
    words = " ".join(quote.lower().split())
    if not words:  # an empty quote would match at every gap, so it never counts as found
        return False
    return re.search(rf"(?<!\w){re.escape(words)}(?!\w)", " ".join(source.lower().split())) is not None
