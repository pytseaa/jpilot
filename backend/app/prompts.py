"""Every prompt wording lives here and nowhere else. The TACC client holds none."""

CV_SUMMARY = """Read the CV below and reply with one JSON object that has these keys:
"summary": a short summary of the candidate in plain English (skills, experience, education),
"keywords": a list of search keywords for jobs that fit this CV, each a word or a short phrase.{target_role_key}

CV:
{cv_text}"""

# Added to CV_SUMMARY only when the candidate left the target role empty.
TARGET_ROLE_KEY = '\n"target_role": the one job title that best fits this CV, such as "data analyst".'

REFINEMENT = """A search of a job database with the keywords below found too few jobs. Reply with one JSON object that has this key:
"keywords": a list of new search keywords for jobs that fit this CV, each a word or a short phrase. Do not repeat a keyword that is already listed.

CV summary:
{cv_summary}

Target role:
{target_role}

Keywords so far:
{keywords}"""

CHECK = """Judge how well the CV below fits the job ad below, and reply with one JSON object that has these keys:
"grade": 0 if the CV is not a fit for the job, 1 if it is a plausible fit, 2 if it is a strong fit,
"claims": a list of reasons the CV fits the job, each an object with the keys "requirement" (the job requirement it meets, a short phrase), "cv_quote" (words copied exactly from the CV) and "job_quote" (words copied exactly from the job ad). Use an empty list if the CV fits nothing in the job.

Copy every quote exactly as written. Do not reword it.

CV summary:
{cv_summary}

CV:
{cv_text}

Job ad:
{description}"""

JOB_EXTRACTION = """Read the job ad below and reply with one JSON object that has these keys:
"region": "Hong Kong" if the job is in Hong Kong, "other" if it is clearly somewhere else, or "unknown".
"employment_types": a list with each type the ad states, from "full-time", "part-time" and "contractor"; an empty list if it states none.
"minimum_years": the years of experience the ad asks for, as one whole number: for a range such as "3-5", the lower figure; 0 for fresh graduate or entry-level wording; null if it says nothing about experience.
"industry": the industry the company works in, one of {industries}, or "unknown".
"requirements": a list of the skills and qualifications the ad asks for, each a short phrase.

Job ad:
{description}"""
