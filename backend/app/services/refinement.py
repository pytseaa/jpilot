"""Refinement: Qwen adds keywords when a search finds too few jobs. Keywords are only ever added."""
from pydantic import ValidationError

from app import prompts, stop_words
from app.schemas.search_request import RefinementAnswer
from app.services import retrieval

MAX_ROUNDS = 2


def widen(conn, keywords, summary, target_role, employment_types, runner, on_round):
    """The qualifying jobs after the search has been widened as far as it needs. on_round gets each round's number.

    A round runs only while fewer than RESULT_LIMIT jobs qualify and some job that passes the hard filters
    still does not. Refining also stops when a round adds no new keyword. The candidate's keywords are never changed."""
    keywords = list(keywords)
    qualifying = retrieval.find_qualifying(conn, keywords, employment_types)
    for round_number in range(1, MAX_ROUNDS + 1):
        # find_qualifying cuts at RESULT_LIMIT, so below that its length is the whole count of qualifying jobs.
        if (len(qualifying) >= retrieval.RESULT_LIMIT
                or len(qualifying) == retrieval.count_passing(conn, employment_types)):
            break
        on_round(round_number)
        added = _new_keywords(round_number, keywords, summary, target_role, runner)
        if not added:  # the same keywords would find the same jobs, and another round would only cost a submission
            break
        keywords += added
        # A round below RESULT_LIMIT is uncut, so none of the earlier jobs can be pushed out of the next one.
        qualifying = retrieval.find_qualifying(
            conn, keywords, employment_types, {job["job_id"] for job in qualifying})
    return qualifying


def _new_keywords(round_number, keywords, summary, target_role, runner):
    """One runner submission. The keywords Qwen adds, or [] when its call or answer is unusable.

    The stop list is applied, and a keyword already listed (in any letter case) is not added again."""
    prompt_id = f"refine-{round_number}"
    prompt = prompts.REFINEMENT.format(cv_summary=summary, target_role=target_role, keywords=", ".join(keywords))
    record = runner([{"id": prompt_id, "required_keys": ["keywords"], "prompt": prompt}])[prompt_id]
    if record["status"] != "ok":
        return []
    try:
        proposed = RefinementAnswer.model_validate(record["answer"]).keywords
    except ValidationError:
        return []
    # shortcut: a repeat is judged by the whole keyword, so a phrase whose words are all searched already still counts as new, compare matching words if rounds are wasted.
    known = {keyword.lower() for keyword in keywords}
    added = []
    for keyword in stop_words.remove(proposed):
        if keyword.lower() not in known:
            known.add(keyword.lower())
            added.append(keyword)
    return added
