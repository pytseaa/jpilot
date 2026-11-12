"""Every prompt wording lives here and nowhere else. The TACC client holds none."""

CV_SUMMARY = """Read the CV below and reply with one JSON object that has these keys:
"summary": a short summary of the candidate in plain English (skills, experience, education),
"keywords": a list of search keywords for jobs that fit this CV, each a word or a short phrase.

CV:
{cv_text}"""
