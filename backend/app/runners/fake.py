"""A stand-in for a TACC submission: canned answers keyed by prompt id. Needs no TACC or Qwen."""

DEMO_ANSWERS = {
    "cv-summary": {
        "summary": "Data analyst with five years in retail banking. Strong in SQL, Python "
                   "and dashboards, and has led a small reporting team.",
        "keywords": ["data analyst", "SQL", "Python", "reporting", "experience", "team"],
        "target_role": "Data analyst",
    },
}


class FakeRunner:
    """Takes the prompt list a submission would hold; returns records like the answer file's."""

    def __init__(self, answers=None):
        self.answers = DEMO_ANSWERS if answers is None else answers
        self.submissions = []

    def __call__(self, prompts):
        self.submissions.append(prompts)
        return {item["id"]: self._record(self._answer(item)) for item in prompts}

    def _answer(self, item):
        # A check with no canned answer grades 2 and quotes the start of its own CV text and ad, so both verify.
        # A refinement with no canned answer adds no keywords.
        if item["id"] not in self.answers:
            if item["id"].startswith("check-"):
                return _grade_by_quoting(item["prompt"])
            if item["id"].startswith("refine-"):
                return {"keywords": []}
        return self.answers[item["id"]]

    @staticmethod
    def _record(answer):
        # An answer of None stands for a call that failed, as the TACC client records it.
        if answer is None:
            return {"status": "failed", "error_type": "invalid_json"}
        return {"status": "ok", "answer": answer}


def _grade_by_quoting(prompt):
    # Quotes the first three words of the CV text and the ad, read back from the prompt so both verify; the labels are prompts.CHECK's.
    cv_text = prompt.split("\nCV:\n", 1)[1].split("\n\nJob ad:\n", 1)[0]
    ad = prompt.split("\n\nJob ad:\n", 1)[1]
    cv_quote, job_quote = " ".join(cv_text.split()[:3]), " ".join(ad.split()[:3])
    return {"grade": 2, "claims": [{"requirement": job_quote, "cv_quote": cv_quote, "job_quote": job_quote}]}
