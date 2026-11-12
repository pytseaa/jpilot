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
        return {item["id"]: {"status": "ok", "answer": self.answers[item["id"]]}
                for item in prompts}
