"""Every prompt wording lives here and nowhere else. The TACC client holds none."""

CV_SUMMARY = """Read the CV below and reply with one JSON object that has these keys:
"summary": a short summary of the candidate in plain English (skills, experience, education),
"keywords": a list of search keywords for jobs that fit this CV, each a word or a short phrase.{target_role_key}

CV:
{cv_text}"""

# Added to CV_SUMMARY only when the candidate left the target role empty.
TARGET_ROLE_KEY = '\n"target_role": the one job title that best fits this CV, such as "data analyst".'
