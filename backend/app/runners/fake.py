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
        return {item["id"]: self._record(self._answer(item["id"])) for item in prompts}

    def _answer(self, prompt_id):
        # shortcut: until the fake grades on its own, every check without a canned answer is "no fit", remove this once it does.
        if prompt_id.startswith("check-") and prompt_id not in self.answers:
            return {"grade": 0, "claims": []}
        return self.answers[prompt_id]

    @staticmethod
    def _record(answer):
        # An answer of None stands for a call that failed, as the TACC client records it.
        if answer is None:
            return {"status": "failed", "error_type": "invalid_json"}
        return {"status": "ok", "answer": answer}
