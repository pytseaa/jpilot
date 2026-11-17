"""Checking: Qwen grades each qualifying job against the CV, and only claims whose quotes are found are kept."""
import re

from pydantic import ValidationError

from app import prompts
from app.schemas.check import CheckAnswer, Claim
from app.services import ranking

CHECK_KEYS = ["grade", "claims"]
SHORTLIST_SIZE = 5


def check_jobs(jobs, cv_text, summary, runner):
    """One submission with one prompt per job. Return the shortlist and the dropped-claim count."""
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
        verified, not_found = _verified(answer.claims, cv_text, job["description"])
        dropped += not_found
        if verified:
            checked.append({**job, "grade": answer.grade, "claims": [c.model_dump() for c in verified]})
    return ranking.rank(checked)[:SHORTLIST_SIZE], dropped


def _answer(record):
    """The checked answer, or None when the call failed or the answer is not what the prompt asked for."""
    if record["status"] != "ok":
        return None
    try:
        return CheckAnswer.model_validate(record["answer"])
    except ValidationError:
        return None


def _verified(raw_claims, cv_text, description):
    """The claims with both quotes found, and how many were dropped. Only the source texts verify a quote (ADR 0003)."""
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
    if not re.search(r"\w", words):  # an empty or punctuation-only quote says nothing, so it is never found
        return False
    return re.search(rf"(?<!\w){re.escape(words)}(?!\w)", " ".join(source.lower().split())) is not None
