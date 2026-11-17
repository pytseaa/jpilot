"""Ranking: the order of the checked jobs. Plain code, Qwen is not called."""

BANDS = {"0-2": (0, 2), "3-5": (3, 5), "6-9": (6, 9), "10+": (10, float("inf"))}


def rank(jobs, experience_band, industry):
    """The jobs best first. They arrive in keyword order, which a stable sort keeps as the last key."""
    return sorted(jobs, key=lambda job: (-job["grade"], job["unverified"], -len(job["claims"]),
                                         -_preferences_met(job, experience_band, industry)))


def _preferences_met(job, experience_band, industry):
    """How many of the two soft preferences the job meets. A blank preference or an unknown value counts as met."""
    years = job["minimum_years"]
    low, high = BANDS.get(experience_band, (0, float("inf")))
    return (industry is None or job["industry"] in (industry, "unknown")) + (
        years is None or low <= years <= high)
