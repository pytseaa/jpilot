# JobPilot (CSIT6000V course project)

JobPilot reads a text-based PDF CV and searches a database of Hong Kong job ads. For each candidate job, the Qwen model
on TACC compares the CV with the ad. The app shows up to 5 jobs. Each job comes with quotes from the CV and from the ad
as evidence, and with the skills the CV does not show.

## What is in the repository

```text
backend/                   FastAPI app: routes, schemas, and one service per step of a search
backend/tacc_qwen_client/  the small program the backend sends to TACC (standard library only)
frontend/                  React + TypeScript web page
tacc_qwen_serve/           the job that starts the Qwen service on TACC. You start it by hand
eval/                      synthetic CVs and the scripts for the evaluation (see Detailed Instructions)
```

Two folders are not in the repository: `backend/data/` (the job database and request traces) and `eval/out/`
(evaluation outputs, rater files and audit files). They hold job ad text and ratings.

---

## Getting Started Instructions

### Prerequisites

- **Python 3.10** (3.10.6 was used) and **Node.js 22.13+ or 24** (24.13.0 was used).
- **To run on TACC:**
  - A TACC account for the course, with 2 GPUs.
  - The course tool `tcloud` (0.4.1 was used), set up with the course's `setup-sdk-account.sh`.
  - `tcloud` only runs on Linux. On Windows, use WSL (Ubuntu 22.04 was used) for the backend and for every TACC command.
- **To fill the job database:** a JSearch API key in the environment variable `JSEARCH_API_KEY`. The free plan allows
  200 requests a month, and one run uses 30.

### Setup

Run these in a Linux shell, from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend && npm ci && cd ..
```

Notes:
- On Ubuntu, `python3 -m venv` can fail until you run `sudo apt install python3-venv`. It failed on the WSL used here and
  this fix was not tried, so the venv step itself is untested.
- On Windows with the repository on a Windows drive, a `.venv` made by Windows has `Scripts/` and cannot run in WSL. Make the
  venv inside WSL (for example `~/jpilot-venv`) and use its `bin/python` wherever this README says `.venv/bin/python`.
  Every TACC run below used such a venv.
- The frontend commands ran with Node.js on Windows, and the backend ran in WSL. The web page only needs the backend on
  port 8000.

### Check that it works without TACC (about 1.5 minutes)

```bash
.venv/bin/python -m pytest backend
cd frontend && npm run typecheck && npm test
```

Expected output:
- The backend tests end with `268 passed, 1 warning` (about 50 seconds).
- The typecheck prints no errors.
- The frontend tests end with `Test Files  2 passed (2)` and `Tests  10 passed (10)`.

These tests use a fake `tcloud` and a fake Qwen, so they never reach TACC.

### Check that it works with TACC: a small end-to-end example

This sends one question to Qwen through the real code path: backend runner, `tcloud submit`, a TACC job, the Qwen
service, and back. Run it in WSL or Linux, from the repository root.

**1. Start the Qwen service.** It prints a job number.

```bash
cd tacc_qwen_serve && tcloud submit && cd ..
```

**2. Wait until the service is ready.** Repeat these two commands until the log shows `Application startup complete`.
Once the job was running this took about 5 minutes. Waiting in the queue before that took from under a minute to about an hour.

```bash
tcloud ps
tcloud cat slurm_log/qwen-public-serve-<job number>.log
```

The log also prints a line like `SERVICE_BASE_URL=http://10-0-3-11:8000/v1`.

**3. Put the service address in `backend/tacc_qwen_client/server-url.txt`.** Write the node's IP address, not its name:
`10-0-3-11` becomes `10.0.3.11`, so the file holds `http://10.0.3.11:8000/v1`. Some nodes cannot look up the
name (`Name or service not known`), and then the client wrongly reports that the service is unreachable.

**4. Send one question.** This starts one small TACC job and takes about 20 to 40 seconds.

```bash
cd backend
PYTHONPATH=. ../.venv/bin/python - <<'EOF'
import json
from app.runners.tacc import TaccRunner

records = TaccRunner()([{"id": "smoke-1", "required_keys": ["answer"],
                         "prompt": 'What is 37 plus 58? Reply with only this JSON: {"answer": <number>}'}])
print(json.dumps(records, indent=2))
EOF
cd ..
```

Expected output (seen on 2026-11-22; `elapsed_seconds` was between 0.33 and 0.69 over four runs, the other values did not change):

```json
{
  "smoke-1": {
    "status": "ok",
    "answer": {
      "answer": 95
    },
    "attempts": 1,
    "errors": [],
    "prompt_tokens": 34,
    "completion_tokens": 8,
    "elapsed_seconds": 0.333
  }
}
```

**5. Stop the service when you are done:** `tcloud cancel -j <job number>`. It also stops by itself after 1 hour,
and then the address no longer works. Every new service has a new address.

### Run the whole app

Run the backend in Linux or WSL, and the web page next to it:

```bash
# backend, with Qwen on TACC (needs the service from the steps above)
.venv/bin/python -m uvicorn --app-dir backend app.main:create_app --factory --port 8000

# or backend with a fake Qwen, no TACC needed
JPILOT_RUNNER=fake .venv/bin/python -m uvicorn --app-dir backend app.main:create_app --factory --port 8000

# web page, in another terminal
cd frontend && npm run dev        # open http://localhost:5173
```

- If the backend runs in WSL and the web page on Windows, the web page reaches it on `127.0.0.1:8000`. We started the backend
  with `--host 0.0.0.0` in that setup and it worked. Whether the default `127.0.0.1` also works was not tested.
- `JPILOT_RUNNER` can be `tacc` (the default) or `fake`. Any other value stops the app at start.
- The job database starts empty. With an empty database every search ends with "No current jobs pass your employment type and
  Hong Kong filters." Fill it first (Detailed Instructions, step 1).
- Upload a text-based PDF, pick an employment type, press the send button, check the summary and keywords, then press Search.
  A search took about 3 to 6 minutes on TACC in most runs.

---

## Detailed Instructions

### What the evaluation covers

| Part | What it measures | Where the result is |
|---|---|---|
| A. Speed and cost | Time per search, number of model calls and tokens, over 10 searches | Table 1 |
| B. Ranking quality | How good the top 5 jobs are, for the full system and three comparison systems | Tables 2 and 3 |
| C. Evidence | How many shown claims a person judges unsupported, and how many break a hard filter | Table 4 |
| D. Odd inputs | What happens with a scanned CV, a CV with 3 lines, no matching jobs, bad model output, a crash, an unreachable service | Table 5 |

The project report is not in this repository. Table numbers here are the ones to copy into the report. The
proposal (`JobPilot_Proposal_v4.pdf`, section 3) sets the targets; it is in the folder above the repository.

The four systems compared in part B:
- **Full:** the app as it runs.
- **Ablation A:** the app with the "widen the search" step switched off.
- **B1:** keyword ranking (BM25) over the same filtered jobs.
- **B2:** one Qwen call that sees the CV and the top 20 keyword matches and picks the best 5.

### Data, test cases and settings

| Item | What it is |
|---|---|
| Job snapshot | `backend/data/snapshots/jpilot-2026-11-22.db`: 276 jobs from JSearch (284 fetched, 8 dropped because they were mostly Chinese). 203 are marked Unverified because the region (88) or the employment type (184) is not stated. A job counts as open for 30 days |
| CVs | 8 made-up CVs in `eval/cvs/`, each as a `.txt` source and a text-based `.pdf`. Names: `e1` to `e3` experienced workers, `g1` to `g3` graduates, `s1` and `s2` career switchers. Odd-input CVs are in `eval/cvs/edge/` |
| Search settings | Employment type `full-time` only. The 10 speed runs set no experience band or industry. The ranking runs use the settings in `eval/ranking/settings.json` |
| Preference settings | `eval/ranking/settings.json` gives each CV two settings: **A** is its own experience band and industry, **B** is a neighbouring band and a related industry. They were approved on 2026-11-23 and not changed afterwards |
| Qwen service | `tacc_qwen_serve/tuxiv.conf`: 1 node, 2 GPUs, 1 hour. Its `exclude=10-0-4-10,10-0-1-10` line skips two nodes whose GPUs were already about half full on 2026-11-22. Delete the line if those nodes are fine when you run it |
| Model | `qwen3.8-27b` from the course service: 32K context, 4 calls at the same time |
| Client job | `backend/tacc_qwen_client/tuxiv.conf`: 1 CPU, 10 minutes |

The evaluation scripts read the snapshot by its exact name, `jpilot-2026-11-22.db`. A new ingestion saves
`jpilot-<today>.db` and finds different jobs, so copy it to the old name to use it, and expect different numbers.
To get the exact numbers in this README you need the original snapshot, which is not in the repository.

### How to rerun

Run everything from the repository root. Steps 1 to 4 need a running Qwen service (see Getting Started, steps 1 to 3).

**Step 1. Fill the job database and freeze a copy** (about 8 minutes, uses 30 JSearch requests):

```bash
cd backend
JSEARCH_API_KEY=<your key> ../.venv/bin/python -m app.ingest --snapshot
cd ..
```

Expected output (2026-11-22):

```text
Jobs fetched: 284
Stored: 276
Already stored: 0
Dropped as mostly Chinese: 8
Dropped with no description: 0
Failed at extraction: 0
Failed JSearch requests: 0
Snapshot: <full path>/backend/data/snapshots/jpilot-2026-11-22.db
```

The last line shows the full path of the saved snapshot on your machine.

Running it again is safe: a job that is already stored only gets a new collection date. The key is read from the
environment and is never written to a file. A second snapshot on the same day is refused.

**Step 2. Speed and cost (part A).** Start the backend (see "Run the whole app"), then in another terminal:

```bash
.venv/bin/python eval/run_e2e.py --repeats 10
```

It uploads the 8 CVs in turn (runs 9 and 10 reuse `e1` and `e2`), waits for each search and writes
`eval/out/e2e/runs.csv` and `eval/out/e2e/summary.txt`. The ten runs took 66 minutes in total, so they do not fit in one
service hour. If the service ends, start a new one, update `server-url.txt` and run the same command: it continues after
the rows already saved. A failed run is saved with its error and still counts toward `--repeats`, so remove failed rows
from `runs.csv` before you rerun or report numbers.

**Step 3. Ranking and evidence (parts B and C).** The first command needs the service. The middle steps need people.

```bash
.venv/bin/python eval/ranking/systems.py        # runs the 4 systems on 16 queries; about 13 minutes; can be resumed
.venv/bin/python eval/ranking/labels.py pack    # makes rater1.csv and rater2.csv (99 jobs each) and a key
```

Two raters then grade every job 0, 1 or 2 on their own, using `eval/ranking/GRADING_GUIDE.md`, by writing the grade in the
last column of their own file. `eval/ranking/RATER_INSTRUCTIONS.md` lists the steps for the raters, the team lead and the auditor.

```bash
.venv/bin/python eval/ranking/labels.py agreement   # agreement before they talk, and disagreements.csv
```

The raters settle only the disagreements and write the agreed grade into `disagreements.csv` (write `lower` for a job they
cannot settle: it then gets the lower of the two grades).

```bash
.venv/bin/python eval/ranking/labels.py resolve     # disagreements.csv -> resolved.csv
.venv/bin/python eval/ranking/labels.py finalise    # final grades in labels.json
.venv/bin/python eval/ranking/audit.py              # makes audit.csv: 100 claims for one person to judge
# the auditor writes yes or no in the `supported` column of audit.csv
.venv/bin/python eval/ranking/score.py              # writes eval/out/ranking/results.md with the tables
```

**Step 4. Odd inputs (part D).** The cases that use a scanned or short CV need only the app and a CV from `eval/cvs/edge/`.
Two cases break the model's answer on purpose and need no TACC:

```bash
FAULT=invalid_output .venv/bin/python -m uvicorn --app-dir eval inject_faults:create --factory --port 8000
FAULT=search_crash   .venv/bin/python -m uvicorn --app-dir eval inject_faults:create --factory --port 8000
```

They replay saved Qwen answers for CV `e2` from `eval/out/replay/` (the answer files `job-30771.json` and `job-30773.json` of
the first successful search, copied from TACC with `tcloud download`). They work only with the 2026-11-22 snapshot.

**Check the scripts themselves, without TACC:**

```bash
.venv/bin/python -m pytest eval/ranking
```

Expected: `48 passed`. Without the snapshot file, 6 of these tests are skipped (`42 passed, 6 skipped`).

---

### Main results

All numbers are from 2026-11-22 and 2026-11-23. Settings and sample sizes are small, so read the limitations below.

#### Table 1. Speed and cost: 10 searches (Step 2)

All 10 searches finished. Searches 1 to 5 used one Qwen service, and 6 to 10 used another.

| Run | CV | Total s | Reading the CV s | Search s | Jobs shown | Qwen grades 2 / 1 / 0 | Claims kept / dropped |
|---|---|---|---|---|---|---|---|
| 1 | e1 marketing | 221.6 | 62.2 | 159.3 | 5 | 4 / 11 / 5 | 94 / 5 |
| 2 | e2 customer admin | 175.8 | 22.5 | 153.3 | 5 | 5 / 11 / 4 | 102 / 7 |
| 3 | e3 logistics | 181.2 | 21.9 | 159.3 | 5 | 8 / 7 / 5 | 107 / 4 |
| 4 | g1 finance | 313.5 | 21.9 | 291.6 | 5 | 1 / 10 / 9 | 79 / 5 |
| 5 | g2 software | 1450.7 | 272.3 | 1178.4 | 5 | 0 / 12 / 8 | 85 / 1 |
| 6 | g3 data analyst | 288.0 | 146.7 | 141.3 | 5 | 0 / 13 / 7 | 81 / 4 |
| 7 | s1 teacher to HR | 330.0 | 35.5 | 294.6 | 5 | 0 / 13 / 7 | 86 / 2 |
| 8 | s2 marketing to design | 330.0 | 35.4 | 294.6 | 5 | 1 / 16 / 3 | 83 / 1 |
| 9 | e1 marketing | 330.0 | 35.4 | 294.6 | 5 | 4 / 11 / 5 | 93 / 6 |
| 10 | e2 customer admin | 335.9 | 41.3 | 294.6 | 5 | 5 / 11 / 4 | 103 / 6 |

| Measure | Value |
|---|---|
| Total time per search | middle value (median) 321.7 s; 95th percentile 949.0 s; fastest 175.8 s; slowest 1450.7 s. Without run 5: median 313.5 s, slowest 335.9 s |
| Reading the CV | median 35.4 s; 95th percentile 215.8 s |
| Search | median 293.1 s; 95th percentile 780.7 s |
| Qwen calls per search | 21 every time (1 CV summary and 20 job checks); 0 retries; 210 in total |
| Tokens | 265,388 prompt and 85,613 completion in total; about 26,500 and 8,600 per search |
| Slowest single call | 15.9 s |
| Claims | 954 claims checked; 913 kept; 41 dropped because their quote is not in the CV or the ad (4.3%) |

The 95th percentile uses only 10 values, so run 5 sets it.

#### Table 2. Ranking quality: the four systems

16 queries (8 CVs, each with settings A and B). Two raters graded 99 jobs, the union of what the systems returned. **nDCG@5** is
a score from 0 to 1 for the top 5 list: 1 means the best 5 of the graded jobs in the best order. **Precision@5** is the
share of the 5 jobs graded 1 or 2.

| System | nDCG@5 | Precision@5 | Average grade of its top 5 (0 to 2) | Top-5 jobs graded 2 / 1 / 0 (80 jobs) |
|---|---|---|---|---|
| Full | 0.804 | 0.838 | 1.21 | 30 / 37 / 13 |
| Ablation A | 0.804 | 0.838 | 1.21 | 30 / 37 / 13 |
| B1 keyword | 0.567 | 0.650 | 0.88 | 18 / 34 / 28 |
| B2 one call | **0.924** | **0.975** | 1.32 | 28 / 50 / 2 |

#### Table 3. Ranking quality: differences with a 95% range

The range comes from resampling the 8 CVs 10,000 times. If it includes 0, the data cannot tell the two systems apart.

| Comparison | nDCG@5 difference | 95% range |
|---|---|---|
| Full minus B1 | +0.237 | +0.023 to +0.452 |
| Full minus B2 (the stronger comparison system) | **-0.120** | -0.282 to +0.018 |
| Full minus Ablation A | 0.000 | 0.000 to 0.000 |

**The proposal's goal was +0.05 over the stronger comparison system. It was not met.** Full scored 0.12 below B2, and the
range includes 0. Full beat B1 by 0.24, and that range does not include 0.

How to read it:
- Across the 8 CVs, Full was ahead on 1, equal on 2 and behind on 5. The `s1` CV (teacher to HR) has the biggest gap
  (Full 0.40, B2 1.00). Without it, the gap is -0.052.
- Full and B2 start from the same 20 keyword matches, so this compares how they rank those 20, not how they search.
- The order Full < B2 and Full > B1 stays the same if you use rater 1 alone, rater 2 alone, the lower of the two grades or the
  higher of the two (Full minus B2 between -0.140 and -0.163).
- Ablation A equals Full on every query. The search never needed widening, so the widening step had no effect here.
- The raters agreed on 87 of 99 jobs (87.9%). Weighted Cohen's kappa, computed before they talked, was 0.896 (quadratic weights)
  and 0.853 (linear weights). All 12 disagreements were one grade apart, and the raters settled every one at grade 1.
  Final grades: 29 graded 0, 47 graded 1, 23 graded 2.
- Qwen's own grades and the raters' grades agree on 72 of the 99 jobs that both graded. Qwen gave grade 1 to 15 jobs the raters
  graded 0, and to 8 jobs the raters graded 2. Qwen never gave grade 0 to a job a rater liked.
- For the Full system, settings A and B gave a different set of 5 jobs for 5 of the 8 CVs.

#### Table 4. Evidence: claims and filters

One person judged 100 shown claims without knowing which system produced them (50 from Full, 50 from B2, from 52 different
jobs). For each claim they wrote `yes` if the CV quote and the ad quote together show that the CV meets the requirement, and
`no` if not. The 95% range resamples whole jobs, because claims from one job are not independent.

| System | Claims judged | Judged unsupported | Rate | 95% range |
|---|---|---|---|---|
| Full | 50 | 21 | **42.0%** | 27.7% to 56.8% |
| B2 | 50 | 18 | 36.0% | 23.9% to 48.9% |

**The proposal's target was at most 5% unsupported claims. It was not met.** Even the low end of the Full range is more than
five times the target. The two systems cannot be told apart on this measure.

- The auditor's notes on the 39 `no` answers mostly say the same thing: the quote is real but shows only part of the
  requirement. Examples: "Excel" for an ad asking "Word and Excel"; "Linux" for "comfortable in the terminal and SSH".
  The code only checks that a quote exists, so it passes these claims.
- Separately, the code dropped 38 claims from the Full system before display because a quote was not found (275 distinct claims shown).
- **Hard filters:** 0 of 320 shown jobs broke a filter (region, employment type, open for 30 days). This is true by design,
  because the filters are plain code. 228 of the 320 are marked Unverified because a field is unknown, which the design keeps.

#### Table 5. Odd inputs

| Case | How it was run | What happened |
|---|---|---|
| Scanned CV (no text) | `eval/cvs/edge/scanned-no-text.pdf`, real stack | Refused before any Qwen call: "We could not read any text from this file. Please upload a text-based PDF, not a scan or an image." |
| CV with 3 lines | `eval/cvs/edge/sparse.pdf`, real stack | 5 jobs shown, all "Plausible fit". Qwen graded 7 of 20 checked jobs 1 and 13 graded 0 |
| CV outside the database's fields | `eval/cvs/edge/outside-field-chef.pdf` (a pastry chef), real stack | All 20 checked jobs graded 0. "Done. No jobs to show." and "No job fits your CV with evidence we could verify." |
| Keywords that match no job | Same chef CV, keywords replaced by `zzqx`, summary and role cleared, real stack | None of the 249 jobs that pass the filters matched. One widening round ran and added no keywords. "No jobs matched your keywords after widening the search." |
| Bad model output | Injected (Step 4). Not seen on the real service in 210 calls | 5 jobs shown and "1 job was skipped because the check failed. The results may be incomplete." |
| Crash during the search | Injected (Step 4) | "Search ended: The search failed. No partial results are shown. Your CV has been deleted." |
| Service stopped, node still up | The service reached its 1-hour limit during a batch | The call is refused at once. "The Qwen service could not be reached. Please restart the service, then update its address in server-url.txt." |
| Service address with nothing behind it | `server-url.txt` set to `http://10.0.9.250:8000/v1` | The call waits 129 s and times out. "The CV could not be matched because no usable CV summary was returned." |

"Employment type" alone cannot empty the results here, because 184 of the 276 jobs list no employment type and pass every
filter. A search for contractor jobs only returned the same 5 jobs as full-time.

---

### Known limitations and expected variation

**Speed**
- Time is mostly waiting for TACC, not the model. The slowest call took 15.9 s, and a search makes 21 calls with 4 at a time,
  so the model needs about 1 minute. Searches took 3 to 24 minutes.
- The same CV gave the same grade counts both times (`e1` 4/11/5, `e2` 5/11/4). The claim counts moved by one
  (94/5 and 93/6; 102/7 and 103/6), and the times differed by 108 s and 160 s. Expect times to vary a lot between runs.
- We did not find out why run 5 took 24 minutes. Its checking step took 1,175 s, while other runs took 140 to 295 s.
- Eight attempts failed and are not in Table 1 (`eval/out/e2e/runs-failed-attempts.csv`). Three were the service reaching its
  1-hour limit. Five said "The TACC submission failed". When we ran `tcloud submit` by hand right after, the upload failed with
  `No space left on device`. The error went away later without us deleting anything, and we did not find the cause.
- The service stops after 1 hour and each new one has a new address. Two nodes (`10-0-4-10`, `10-0-1-10`) could not start it
  on 2026-11-22 because their GPU memory was already used. This may be different when you run it.

**Data and method**
- **The snapshot expires.** A job counts as open for 30 days from today, not from the snapshot date. After 2026-12-22 the saved
  snapshot has no open jobs and every search says "No current jobs pass your employment type and Hong Kong filters."
- **Small and made-up.** 8 made-up CVs, 16 queries that are 8 pairs, 99 graded jobs, 100 judged claims and one auditor.
  The auditor's strictness sets the 42%, and there is no second auditor to measure it.
- **Settings A and B were written after the CVs had been searched** (10 searches on 2026-11-22, then the settings on 2026-11-23).
  They came from the CV texts only and were not changed after the four systems ran. The plan was to fix them first.
- **The grade scale is a choice.** nDCG@5 here uses the grade itself (0, 1, 2) as the gain. Using 2^grade - 1 instead
  gives Full 0.796, B1 0.518, B2 0.907, and the same order.
- **The raters' top 7.** The graded pool holds each system's top 7 jobs (B2's 5), not only the top 5 the app shows, so the
  comparison has some depth beyond 5.
- **Not checked:** the `author` of each CV is in `settings.json`, but we did not record which rater is which person, so the rule
  "nobody grades a CV they wrote" is not confirmed. The grading guide still has made-up examples instead of real ones.
- **Not done:** skill-extraction accuracy, learning-link usefulness and link validity (secondary items in the proposal).
- **CV copies on TACC.** The backend deletes its own copies of the prompt and answer files after each search, but copies may
  stay in the course's TACC storage.

### Fixes this work needed

Three problems showed up on the first real TACC run. They are fixed in the code:
- `tcloud ps -j` prints an error for a finished job but still exits with 0. The runner now looks for the job's row instead
  of trusting the exit code (`backend/app/runners/tacc.py`).
- A `tcloud` call that stalls past its time limit is tried once more.
- A `job.sh` saved with Windows line endings fails on TACC with `set: pipefail: invalid option name`. `.gitattributes` keeps
  `*.sh` files on Unix line endings.

### Request traces

Each search writes a trace to `backend/data/traces/`. It holds timings, call, token and retry counts, grades and
quote-check results. It holds no CV text, prompts, answers or quotes. A failed upload returns an `X-Request-ID` header
that names its trace.
