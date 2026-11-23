# What the raters and the auditor must do

Files are in `eval/out/ranking/`. Do not open `key.json` or `audit-key.json`: they name the system behind each job, and opening them ruins the blind rating. Keep the key files out of the rater's reach (the team lead holds them).

## Before anyone starts (team lead)

1. In `eval/ranking/settings.json`, fill in `author` for all 8 CVs (who wrote each). **A person may not rate a CV they wrote.** Split the 8 CVs between the two raters so each rater avoids their own, then tell each rater which CVs are theirs to rate.
2. Replace the made-up examples in `eval/ranking/GRADING_GUIDE.md` with two real jobs per grade from the snapshot, and give both raters the guide. Do this before anyone sees a result, and do not pick examples from the pooled jobs of the CVs being rated.
3. Copy `rater1.csv` to rater 1 and `rater2.csv` to rater 2 (one file each, not both). Keep `key.json`, `audit-key.json`, `systems.json` and `results.md` away from them.

## Rater 1 and rater 2 (each alone)

- **File:** your own `raterN.csv`, opened in Excel or a text editor that keeps UTF-8 (the file has a byte-order mark so Excel reads the Chinese text correctly).
- **Rows:** 99 jobs, 11 to 14 per CV, grouped by CV but shuffled within it. The `cv` column names the CV; its PDF is `eval/cvs/<cv>.pdf`. Read that CV first.
- **Task:** for each row, read `title`, `employer`, `location` and `description`, then write `0`, `1` or `2` in the `grade` column, using `GRADING_GUIDE.md`. Grade **only how well the CV fits the job ad**. Ignore the experience band, the industry, the employer's fame, and anything about how the job was found.
- **Do not skip a row.** An empty or any other value stops the scoring.
- **Do not discuss, compare or look up** which system returned a job. The files do not say.
- **Time:** the 99 descriptions total about 243,000 characters (median 1,900 per job). Plan roughly 3 to 4 hours each, and rate in more than one sitting if you tire, since grades slip when you do.
- When done, save and return the file. Do not edit another rater's file.

## After both files are back (team lead)

1. Run `python eval/ranking/labels.py agreement`. It prints the raw agreement and the weighted kappa (quadratic and linear) computed from the two original files, and writes `disagreements.csv`. **Write the kappa down now, before the raters talk.** Do not rerun it later and report that number: it would be the same, but the record must come from before the meeting.
2. Hand `disagreements.csv` to the two raters. They talk **only** about those jobs and settle each one.
3. Write `eval/out/ranking/resolved.csv` with the columns `item_id,grade`: one row for each job they disagreed on (`disagreements.csv` has the ids). If they still disagree after talking, leave `grade` empty, and the job gets the lower of their two grades.
4. Run `python eval/ranking/labels.py finalise`. It prints the agreement, the number settled by talking and the number the lower-grade rule applied to, and writes `labels.json`.

## Claim audit (one person, alone)

- **File:** `audit.csv`, 100 rows: 50 claims from each of two systems, not labelled. Any team member can audit. Where possible, pick someone who did not write the CV of the claim they judge.
- **Task:** for each row, read the requirement, the CV quote, the job-ad quote and the job description. Write `yes` in `supported` if the two quotes together show the CV meets that requirement, `no` if they do not. Use `note` for anything odd.
- **Not your concern:** whether the quote is copied exactly. The code checked that. You judge whether the claim is *true*.
- **Do not open `audit-key.json`.**

## Then (team lead)

```bash
python eval/ranking/score.py        # writes eval/out/ranking/results.md
```

Report with every number: the nDCG gain used, that the settings were drafted after the CVs had been searched, the number of CVs with a different top 5 under A and B, and the kappa before and after talking.
