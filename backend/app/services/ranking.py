"""Ranking: the order of the checked jobs. Plain code, Qwen is not called."""

# A blank band (None) has no limits, so every job meets it. Any other key not listed here is a bug, so it raises.
BANDS = {None: (0, float("inf")), "0-2": (0, 2), "3-5": (3, 5), "6-9": (6, 9), "10+": (10, float("inf"))}


def rank(jobs, experience_band, industry):
    """The jobs best first. They arrive in keyword order, which a stable sort keeps as the last key."""
    return sorted(jobs, key=lambda job: (-job["grade"], job["unverified"], -len(job["claims"]),
                                         _preference_fit(job, experience_band, industry)))


def _preference_fit(job, experience_band, industry):
    """Preference fit as a sort key: the preferences met (most first), then the years gap (smallest first).

    A blank preference or an unknown value counts as met and has no gap. The gap is 0 inside the band."""
    years = job["minimum_years"]
    low, high = BANDS[experience_band]
    met = (industry is None or job["industry"] in (industry, "unknown")) + (years is None or low <= years <= high)
    gap = 0 if years is None else max(low - years, years - high, 0)
    return -met, gap
