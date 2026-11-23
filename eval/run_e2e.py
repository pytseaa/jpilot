"""End-to-end runs: upload each synthetic CV to the running backend, search, and record the numbers.

    python eval/run_e2e.py [--base http://127.0.0.1:8000] [--repeats 10] [--out eval/out/e2e]

--repeats is the total number of runs. If <out>/runs.csv already holds runs, the script continues
after them, so the service's one-hour limit can split the runs into two windows.

Needs the backend running with the real TACC runner and the Qwen service up. It uses only the
public API, the same calls as the browser, and writes one row per run to <out>/runs.csv.
The CV text is never written: only timings, counts and the trace numbers.
"""
import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
EMPLOYMENT = ["full-time"]
COLUMNS = ["run", "cv", "request_id", "outcome", "upload_seconds", "search_seconds", "total_seconds",
           "jobs_shown", "skipped_jobs", "dropped_claims", "scheduled_calls", "calls", "retries",
           "prompt_tokens", "completion_tokens", "graded_jobs", "grade_2", "grade_1", "grade_0",
           "claims_kept", "claims_dropped", "error"]


def one_run(client, pdf, run, trace_dir):
    row = dict.fromkeys(COLUMNS, "")
    row.update(run=run, cv=pdf.stem)
    started = time.perf_counter()
    try:
        with pdf.open("rb") as f:
            upload = client.post("/api/search-requests", files={"cv": (pdf.name, f, "application/pdf")},
                                 data={"employment_types": EMPLOYMENT})
        row["upload_seconds"] = round(time.perf_counter() - started, 2)
        row["request_id"] = upload.headers.get("X-Request-ID", "")
        if upload.status_code != 200:
            # The detail is the app's own message for the candidate, never CV text.
            row.update(outcome="upload_failed", error=f"HTTP {upload.status_code}: {upload.json().get('detail', '')}"[:160])
            return row
        review = upload.json()
        reviewed = {k: review[k] for k in ("summary", "keywords", "target_role", "employment_types",
                                          "experience_band", "industry")}
        searched = time.perf_counter()
        client.post(f"/api/search-requests/{review['id']}/search", json=reviewed).raise_for_status()
        while True:
            status = client.get(f"/api/search-requests/{review['id']}/status").json()
            if status.get("error") or status["stage"] in ("done", "failed"):
                break
            time.sleep(3)
        row["search_seconds"] = round(time.perf_counter() - searched, 2)
        if status.get("error") or status["stage"] != "done":
            row.update(outcome="search_failed", error=status.get("error", "")[:120])
        else:
            results = client.get(f"/api/search-requests/{review['id']}/results").json()
            row.update(outcome="done", jobs_shown=len(results["jobs"]), skipped_jobs=results["skipped_jobs"],
                       dropped_claims=results["dropped_claims"])
    except httpx.HTTPError as exc:
        row.update(outcome="client_error", error=type(exc).__name__)
    row["total_seconds"] = round(time.perf_counter() - started, 2)
    add_trace_numbers(row, trace_dir)
    return row


def add_trace_numbers(row, trace_dir):
    path = trace_dir / f"{row['request_id']}.json"
    if not row["request_id"] or not path.exists():
        return
    trace = json.loads(path.read_text(encoding="utf-8"))
    totals = trace.get("totals", {})
    for key in ("scheduled_calls", "calls", "retries", "prompt_tokens", "completion_tokens"):
        row[key] = totals.get(key, "")
    graded = [job for job in trace["jobs"] if job.get("grade") is not None]
    row["graded_jobs"] = len(graded)
    for grade in (2, 1, 0):
        row[f"grade_{grade}"] = sum(job["grade"] == grade for job in graded)
    decisions = [d for job in trace["jobs"] for d in job.get("claims", [])]
    row["claims_kept"] = sum(d.get("kept") is True for d in decisions)
    row["claims_dropped"] = sum(d.get("kept") is False for d in decisions)


def read_rows(path):
    """Runs already in the table, so a second service window continues it instead of starting over."""
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key, value in row.items():
            if key not in ("cv", "request_id", "outcome", "error") and value != "":
                row[key] = float(value) if "." in value else int(value)
    return rows


def percentile(values, q):
    values = sorted(values)
    index = (len(values) - 1) * q
    lo, hi = int(index), min(int(index) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def summarise(rows):
    done = [r for r in rows if r["outcome"] == "done"]
    lines = [f"runs: {len(rows)}, done: {len(done)}, failed: {len(rows) - len(done)}"]
    if done:
        totals = [r["total_seconds"] for r in done]
        lines.append(f"total seconds  median {statistics.median(totals):.1f}  p95 {percentile(totals, .95):.1f}  "
                     f"min {min(totals):.1f}  max {max(totals):.1f}")
        for key in ("scheduled_calls", "retries", "prompt_tokens", "completion_tokens", "jobs_shown",
                    "graded_jobs", "grade_2", "grade_1", "grade_0", "claims_kept", "claims_dropped"):
            values = [r[key] for r in done if r[key] != ""]
            if values:
                lines.append(f"{key:18} mean {statistics.mean(values):.1f}  sum {sum(values)}")
        kept, dropped = sum(r["claims_kept"] or 0 for r in done), sum(r["claims_dropped"] or 0 for r in done)
        if kept + dropped:
            lines.append(f"claims verified against source text: {kept} of {kept + dropped} ({kept / (kept + dropped):.0%})")
    return "\n".join(lines)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--cvs", default=str(HERE / "cvs"))
    parser.add_argument("--traces", default=str(HERE.parent / "backend" / "data" / "traces"))
    parser.add_argument("--out", default=str(HERE / "out" / "e2e"))
    args = parser.parse_args(argv)
    pdfs = sorted(Path(args.cvs).glob("*.pdf"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    table = out / "runs.csv"
    rows = read_rows(table) if table.exists() else []
    with httpx.Client(base_url=args.base, timeout=600) as client, table.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, COLUMNS)
        if not rows:
            writer.writeheader()
        for run in range(len(rows) + 1, args.repeats + 1):
            pdf = pdfs[(run - 1) % len(pdfs)]
            row = one_run(client, pdf, run, Path(args.traces))
            rows.append(row)
            writer.writerow(row)
            f.flush()
            print(f"run {run}/{args.repeats} {pdf.stem}: {row['outcome']} in {row['total_seconds']}s, "
                  f"{row['jobs_shown']} jobs, {row['calls']} calls", flush=True)
    summary = summarise(rows)
    (out / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary)
    return 0 if all(r["outcome"] == "done" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
