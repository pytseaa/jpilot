"""Baseline B2: one Qwen call that gets the CV and the whole candidate pool and ranks it.

Settled design (docs/AGENT_LOOP.md, 2026-11-10): the pool is the top 20 qualifying jobs by keyword score after the hard
filters and before any refinement; the call returns a top 5 with reasons and quotes; the app's quote checker audits the
claims. B2 does not drop a claim whose quote is missing, so its claim audit counts those failures.

The wording is here and not in backend/app/prompts.py on purpose: it belongs to the evaluation, not to the app."""
from pydantic import ValidationError

from app.schemas.check import Claim
from app.services import checking

B2_PROMPT = """You are shown one CV and {n} job ads. Choose the 5 ads that fit the CV best, best first, and reply with one JSON object that has this key:
"top": a list of 5 objects, best first, each with the keys "job" (the number of the ad), and "claims": a list of reasons the CV fits that ad, each an object with the keys "requirement" (the job requirement it meets, a short phrase), "cv_quote" (words copied exactly from the CV) and "job_quote" (words copied exactly from that ad).

Copy every quote exactly as written. Do not reword it.

CV:
{cv_text}

{ads}"""

REPLY_TOKENS = 3000
# Measured on 2026-11-22: 4.16 to 4.69 characters per token on the real check prompts. 10% margin on the mean.
CHARS_PER_TOKEN = 4.43 * 0.9
CONTEXT_TOKENS = 32768
MAX_INPUT_TOKENS = CONTEXT_TOKENS - REPLY_TOKENS - 500


def build(cv_text, jobs):
    """The B2 prompt item and its estimated input size in tokens."""
    ads = "\n\n".join(f"Job ad {i}:\n{job['description']}" for i, job in enumerate(jobs, 1))
    prompt = B2_PROMPT.format(n=len(jobs), cv_text=cv_text, ads=ads)
    item = {"id": "b2", "required_keys": ["top"], "max_tokens": REPLY_TOKENS, "prompt": prompt}
    return item, len(prompt) / CHARS_PER_TOKEN


def parse(answer, cv_text, jobs, k=5):
    """Ranked job ids and one record per claim, with whether each quote is found in its source text.

    An ad number outside the pool, or repeated, is ignored and counted. A claim missing a field cannot show anything,
    so it is kept as a claim whose quotes are both not found."""
    ranked, claims, ignored = [], [], 0
    entries = answer.get("top") if isinstance(answer, dict) else None
    for entry in entries if isinstance(entries, list) else []:
        number = entry.get("job") if isinstance(entry, dict) else None
        if isinstance(number, str) and number.strip().isdigit():
            number = int(number)
        if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= len(jobs) \
                or jobs[number - 1]["job_id"] in ranked or len(ranked) == k:
            ignored += 1
            continue
        job = jobs[number - 1]
        ranked.append(job["job_id"])
        for raw in entry.get("claims") if isinstance(entry.get("claims"), list) else []:
            try:
                claim = Claim.model_validate(raw)
            except ValidationError:
                claims.append({"job_id": job["job_id"], "requirement": "", "cv_quote": "", "job_quote": "",
                               "cv_found": False, "job_found": False, "valid": False})
                continue
            claims.append({"job_id": job["job_id"], "requirement": claim.requirement, "cv_quote": claim.cv_quote,
                           "job_quote": claim.job_quote, "valid": True,
                           "cv_found": checking._found(claim.cv_quote, cv_text),
                           "job_found": checking._found(claim.job_quote, job["description"])})
    return ranked, claims, ignored
