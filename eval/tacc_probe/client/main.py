"""TACC probe client: shows what a TACC submission can do. It makes no Qwen calls.

It prints timestamped lines (flushed) so the wrapper can test whether `tcloud cat`
shows a log while the job runs, and it writes one JSON file to TACC_USERDIR.
"""
import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BEATS = int(os.environ.get("PROBE_BEATS", "12"))
BEAT_SECONDS = float(os.environ.get("PROBE_BEAT_SECONDS", "5"))
RESULTS_DIR = "CSIT6000V-project-results"


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def log(message):
    print(f"[{now_utc()}] {message}", flush=True)


def read_input():
    """The wrapper writes input.json into the job folder; echo its nonce back."""
    try:
        return json.loads(Path("input.json").read_text(encoding="utf-8"))["nonce"]
    except (OSError, ValueError, KeyError):
        return None


def own_siblings(workdir):
    """Count the entries beside this job's folder that belong to us, and the age of the oldest.

    If old job folders are still there, TACC does not clean them. Names are not reported.
    """
    parent = Path(workdir).parent
    ages = []
    try:
        for entry in parent.iterdir():
            info = entry.stat()
            if info.st_uid == os.getuid():
                ages.append((time.time() - info.st_mtime) / 3600)
    except OSError as exc:
        return {"parent": str(parent), "error": repr(exc)}
    return {"parent": str(parent), "count": len(ages),
            "oldest_age_hours": round(max(ages), 1) if ages else None}


def main():
    started = now_utc()
    job_id = os.environ["SLURM_JOB_ID"]
    workdir = os.environ["TACC_WORKDIR"]
    userdir = Path(os.environ["TACC_USERDIR"])
    log(f"PROBE_START job={job_id} host={socket.gethostname()} python={sys.version.split()[0]}")
    log(f"TACC_WORKDIR={workdir}")

    nonce = read_input()
    log(f"INPUT_NONCE={nonce}")

    # A file made in USERDIR now should be visible from outside while the job runs.
    results = userdir / RESULTS_DIR
    results.mkdir(parents=True, exist_ok=True)
    delete_me = results / f"probe-{job_id}-delete-me.txt"
    delete_me.write_text("probe\n", encoding="utf-8")

    beats = []
    for number in range(1, BEATS + 1):
        time.sleep(BEAT_SECONDS)
        beats.append(now_utc())
        log(f"BEAT {number}/{BEATS}")

    try:
        delete_me.unlink()
        delete_error = None
    except OSError as exc:
        delete_error = repr(exc)
    deleted = not delete_me.exists()
    log(f"USERDIR_DELETE deleted={deleted} error={delete_error}")

    relative = Path(RESULTS_DIR) / f"probe-{job_id}.json"
    record = {
        "job_id": job_id,
        "host": socket.gethostname(),
        "python": sys.version.split()[0],
        "started_utc": started,
        "finished_utc": now_utc(),
        "workdir": workdir,
        "input_nonce": nonce,
        "workdir_siblings": own_siblings(workdir),
        "userdir_delete": {"deleted": deleted, "error": delete_error},
        "beats": beats,
    }
    (userdir / relative).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    log("RESULT_FILE=" + relative.as_posix())
    log("PROBE_DONE")


if __name__ == "__main__":
    main()
