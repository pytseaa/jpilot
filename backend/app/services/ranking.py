"""Ranking: the order of the checked jobs. Plain code, Qwen is not called."""


def rank(jobs):
    """The jobs best first. They arrive in keyword order, which a stable sort keeps as the last key."""
    return sorted(jobs, key=lambda job: (-job["grade"], job["unverified"], -len(job["claims"])))
