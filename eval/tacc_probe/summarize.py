"""Turn one probe run's events, log and result into summary.json and a short printout."""
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def main(out_dir, job):
    out = Path(out_dir)
    events = []
    for line in (out / "events.tsv").read_text(encoding="utf-8").splitlines():
        stamp, name, detail = (line.split("\t") + ["", ""])[:3]
        events.append((parse_time(stamp), name, detail))

    def first(name, prefix="", after=None):
        for stamp, event, detail in events:
            if event == name and detail.startswith(prefix) and (after is None or stamp > after):
                return stamp, detail
        return None, ""

    submit_begin, _ = first("SUBMIT_BEGIN")
    submit_end, _ = first("SUBMIT_END")
    running_at, _ = first("STATE", "R ")
    pending_at, _ = first("STATE", "PD ")
    # The first empty poll after the job ran; empty polls before it ran mean "not listed yet".
    gone_at, _ = first("STATE", "GONE ", after=running_at) if running_at else (None, "")
    cat_at, cat_detail = first("CAT_WHILE_RUNNING")

    summary = {"job_id": job}
    if submit_begin and submit_end:
        summary["tcloud_submit_seconds"] = round((submit_end - submit_begin).total_seconds(), 1)
    if submit_end and running_at:
        summary["queue_wait_seconds"] = round((running_at - submit_end).total_seconds(), 1)
    summary["saw_pending_state"] = pending_at is not None
    if running_at and gone_at:
        summary["running_seconds_seen_by_ps"] = round((gone_at - running_at).total_seconds(), 1)
    summary["cat_showed_log_while_running"] = cat_at is not None
    summary["cat_detail"] = cat_detail

    result_path = out / "result.json"
    log_path = out / "client.log"
    summary["result_downloaded"] = result_path.exists() and result_path.stat().st_size > 0
    summary["log_downloaded"] = log_path.exists() and log_path.stat().st_size > 0

    if summary["result_downloaded"]:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        nonce = (out / "nonce.txt").read_text(encoding="utf-8").strip()
        summary["input_file_reached_worker"] = result.get("input_nonce") == nonce
        summary["job_could_delete_userdir_file"] = result.get("userdir_delete", {}).get("deleted")
        summary["job_delete_error"] = result.get("userdir_delete", {}).get("error")
        summary["worker_workdir"] = result.get("workdir")
        summary["workdir_siblings_of_ours"] = result.get("workdir_siblings")
        started = parse_time(result["started_utc"])
        if submit_end:
            summary["worker_start_minus_submit_end_seconds"] = round((started - submit_end).total_seconds(), 1)
        if running_at:
            # Time from the job showing "R" to our Python code starting: the job's own set-up (not ours to change).
            summary["running_to_python_start_seconds"] = round((started - running_at).total_seconds(), 1)
        summary["note_clocks"] = "worker times and PC times come from two clocks; treat the gaps as approximate"
    ls_path = out / "ls-results.txt"
    if ls_path.exists():
        ls_text = ls_path.read_text(encoding="utf-8", errors="replace")
        summary["userdir_file_listed_after_job"] = f"probe-{job}-delete-me.txt" in ls_text
    if not any(event == "STATE" for _, event, _ in events):
        summary["queue_wait_note"] = "not measured: the probe did not poll the job state"

    if log_path.exists():
        text = log_path.read_text(encoding="utf-8", errors="replace")
        summary["log_has_probe_done"] = "PROBE_DONE" in text
        match = re.search(r"TACC_WORKDIR=(\S+)", text)
        summary["log_workdir"] = match.group(1) if match else None

    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
