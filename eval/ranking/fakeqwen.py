"""A stand-in for the TACC runner with varied but deterministic answers, so the whole evaluation pipeline can be
exercised offline. Its numbers mean nothing. Used by test_pipeline.py and by `systems.py --fake`."""
import hashlib
import re

from qwen import key_of  # noqa: F401  (re-exported for tests)


def _h(text, mod):
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % mod


def _words(text, n):
    return " ".join(text.split()[:n])


def _record(answer):
    return {"status": "ok", "answer": answer, "attempts": 1, "errors": [],
            "prompt_tokens": 100, "completion_tokens": 20, "elapsed_seconds": 0.1}


class FakeQwen:
    def __init__(self):
        self.submissions = 0

    def __call__(self, prompts):
        self.submissions += 1
        return {p["id"]: _record(self._answer(p["prompt"])) for p in prompts}

    def _answer(self, prompt):
        if prompt.startswith("Read the CV below"):
            cv = prompt.split("CV:\n", 1)[1]
            counts = {}
            for word in re.findall(r"[A-Za-z]{6,}", cv):
                counts[word.lower()] = counts.get(word.lower(), 0) + 1
            top = sorted(counts, key=lambda w: (-counts[w], w))[:8]
            return {"summary": f"Candidate summary: {_words(cv, 12)}", "keywords": top,
                    "target_role": top[0] if top else "analyst"}
        if prompt.startswith("A search of a job database"):
            return {"keywords": []}
        if prompt.startswith("Judge how well the CV"):
            cv = prompt.split("\nCV:\n", 1)[1].split("\n\nJob ad:\n", 1)[0]
            ad = prompt.split("\n\nJob ad:\n", 1)[1]
            grade = _h(ad, 3)
            quote = _words(ad, 3)
            return {"grade": grade, "claims": [{"requirement": quote, "cv_quote": _words(cv, 3), "job_quote": quote}],
                    "unmet_requirements": []}
        if prompt.startswith("You are shown one CV"):
            cv = prompt.split("CV:\n", 1)[1].split("\n\nJob ad 1:\n", 1)[0]
            ads = re.split(r"Job ad \d+:\n", prompt.split("CV:\n", 1)[1])[1:]
            order = sorted(range(len(ads)), key=lambda i: _h(cv + ads[i], 1000))[:5]
            return {"top": [{"job": i + 1, "claims": [{"requirement": "fit", "cv_quote": _words(cv, 3),
                                                       "job_quote": _words(ads[i].strip(), 3) if i % 4 else "made up words"}]}
                            for i in order]}
        raise ValueError("unknown prompt: " + prompt[:40])
