"""Checking: Qwen grades each qualifying job against the CV, and only claims whose quotes are found are kept."""
import re

from pydantic import ValidationError

from app import learning_links, prompts
from app.schemas.check import CheckAnswer, Claim, UnmetRequirement
from app.services import ranking

CHECK_KEYS = ["grade", "claims"]  # unmet_requirements is optional: a missing field degrades to empty skill gaps
SHORTLIST_SIZE = 5


def check_jobs(jobs, cv_text, summary, runner, experience_band, industry, trace=None):
    """One submission with one prompt per job. Return shortlist, dropped claims and skipped jobs.

    The preferences only order the shortlist, so they never reach a prompt."""
    if not jobs:
        return [], 0, 0
    links_text = _learning_links_text()
    submission = [{"id": f"check-{i}", "required_keys": CHECK_KEYS,
                   "prompt": prompts.CHECK.format(cv_summary=summary, cv_text=cv_text,
                                                  description=job["description"],
                                                  learning_links=links_text)}
                  for i, job in enumerate(jobs)]
    records = runner(submission)
    checked, dropped, skipped = [], 0, 0
    for i, job in enumerate(jobs):
        record = records[f"check-{i}"]
        answer = _answer(record)
        if answer is None:
            skipped += 1
            if trace:
                trace.job(job["job_id"], None, [], record.get("error_type", "invalid_answer"))
            continue
        verified, not_found, decisions = _verified(answer.claims, cv_text, job["description"])
        if trace:
            trace.job(job["job_id"], answer.grade, decisions)
        dropped += not_found
        if answer.grade > 0 and verified:
            checked.append({**job, "grade": answer.grade,
                            "claims": [c.model_dump() for c in verified],
                            "skill_gaps": _skill_gaps(answer.unmet_requirements)})
    return ranking.rank(checked, experience_band, industry)[:SHORTLIST_SIZE], dropped, skipped


def _answer(record):
    """The checked answer, or None when the call failed or the answer is not what the prompt asked for."""
    if record["status"] != "ok":
        return None
    try:
        return CheckAnswer.model_validate(record["answer"])
    except ValidationError:
        return None


def _verified(raw_claims, cv_text, description):
    """Verified claims, dropped count and text-free decisions. Only source texts verify quotes (ADR 0003)."""
    verified, dropped, decisions = [], 0, []
    for index, raw in enumerate(raw_claims):
        try:
            claim = Claim.model_validate(raw)
        except ValidationError:
            dropped += 1
            decisions.append({"index": index, "kept": False, "reason": "invalid_claim"})
            continue
        cv_found = _found(claim.cv_quote, cv_text)
        job_found = _found(claim.job_quote, description)
        decisions.append({"index": index, "kept": cv_found and job_found,
                          "cv_quote_found": cv_found, "job_quote_found": job_found,
                          "reason": "verified" if cv_found and job_found else "quote_not_found"})
        if cv_found and job_found:
            verified.append(claim)
        else:
            dropped += 1
    return verified, dropped, decisions


def _skill_gaps(raw_unmet):
    """Skill gaps from the unmet requirements, dropping any link id not in the curated list.

    A requirement with no surviving link is still shown as a skill gap, just without a link.
    A made-up URL never reaches the candidate, because only ids in the curated list resolve."""
    gaps = []
    for raw in raw_unmet:
        try:
            unmet = UnmetRequirement.model_validate(raw)
        except ValidationError:
            continue
        links = []
        for raw_id in unmet.link_ids:
            if not isinstance(raw_id, str):
                continue
            link = learning_links.BY_ID.get(raw_id)
            if link is not None:
                links.append({"id": link["id"], "title": link["title"], "url": link["url"]})
        gaps.append({"requirement": unmet.requirement, "learning_links": links})
    return gaps


def _learning_links_text():
    """The id and title of every curated link, for the check prompt. Never a URL."""
    return "\n".join(f"{link['id']}: {link['title']}" for link in learning_links.LEARNING_LINKS)


def _found(quote, source):
    """True when the quote is in the source as whole words, ignoring letter case and spacing."""
    words = " ".join(quote.lower().split())
    if not re.search(r"\w", words):  # an empty or punctuation-only quote says nothing, so it is never found
        return False
    return re.search(rf"(?<!\w){re.escape(words)}(?!\w)", " ".join(source.lower().split())) is not None
