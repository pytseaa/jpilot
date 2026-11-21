"""Candidate-facing outcomes depend on counts, never generated prose."""


def short_results(jobs, passing, qualifying, skipped):
    if len(jobs) >= 5:
        return None
    if not passing:
        return ("No current jobs pass your employment type and Hong Kong filters. "
                "Check the employment types on the form and upload your CV again to try another search.")
    if not qualifying:
        return ("No jobs matched your keywords after widening the search. "
                "Upload your CV again and review your target role and keywords on the form.")
    if not jobs:
        if skipped == qualifying:
            return ("No jobs could be checked successfully. No matches can be confirmed. "
                    "Please upload your CV again to retry.")
        return ("No job fits your CV with evidence we could verify. Your CV may be too brief, "
                "or this database may not cover your field. Jobs graded 0 are never shown to fill the list.")
    return ("Fewer than five jobs fit your CV with evidence we could verify. "
            "Only jobs with a fit are shown; jobs graded 0 are never added to fill the list.")
