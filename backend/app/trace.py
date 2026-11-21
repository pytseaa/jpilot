"""Request measurements. Only identifiers, fixed labels, numbers and booleans reach disk."""
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

from app.runners.tacc import SERVICE_MESSAGE, SubmissionFailed

ERROR_TYPES = {"http_error", "timeout", "unreachable", "bad_response", "invalid_json",
               "missing_key", "client_error", "invalid_answer", "submission_failed",
               "download_failed", "incomplete_answers", "command_unavailable"}


def error_type(value):
    return value if isinstance(value, str) and value in ERROR_TYPES else "client_error"


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else 0


def _now():
    return datetime.now(timezone.utc).isoformat()


class RequestTrace:
    def __init__(self, data_dir, request_id):
        self.path = Path(data_dir) / "traces" / f"{request_id}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = {"request_id": request_id, "started_at": _now(), "outcome": "running",
                     "elapsed_seconds": 0, "stages": [], "submissions": [], "jobs": []}
        self._stage_started = None
        self.stage("reading CV")

    def save(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
        # Windows readers can briefly hold the old file open while inspecting a running trace.
        for attempt in range(6):
            try:
                temporary.replace(self.path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(.02 * 2 ** attempt)

    def _end_stage(self):
        if self._stage_started is not None:
            elapsed = time.perf_counter() - self._stage_started
            self.data["stages"][-1]["elapsed_seconds"] = elapsed
            self.data["elapsed_seconds"] += elapsed
            self._stage_started = None

    def stage(self, name):
        self._end_stage()
        self.data["outcome"] = "running"
        self.data["stages"].append({"name": name, "started_at": _now()})
        self._stage_started = time.perf_counter()
        self.save()

    def review(self):
        # Human review time is excluded from request processing latency.
        self._end_stage()
        self.data["outcome"] = "awaiting_review"
        self.save()

    def finish(self, outcome, failure=None):
        self._end_stage()
        self.data.update(outcome=outcome, finished_at=_now())
        calls = [call for submission in self.data["submissions"] for call in submission["calls"]]
        self.data["totals"] = {"scheduled_calls": len(calls),
                               "calls": sum(c["status"] != "not_returned" for c in calls), **{
            name: sum(call[name] for call in calls)
            for name in ("attempts", "retries", "prompt_tokens", "completion_tokens")}}
        if failure:
            self.data["error_type"] = error_type(failure)
        self.save()

    def runner(self, runner):
        def submit(prompts):
            entry = {"stage": self.data["stages"][-1]["name"], "started_at": _now(), "calls": []}
            self.data["submissions"].append(entry)
            started = time.perf_counter()
            records = {}
            try:
                records = runner(prompts)
                if (not isinstance(records, dict)
                        or any(not isinstance(records.get(p["id"]), dict)
                               or records[p["id"]].get("status") not in ("ok", "failed")
                               or (records[p["id"]]["status"] == "ok" and "answer" not in records[p["id"]])
                               for p in prompts)):
                    raise SubmissionFailed("The submission returned an incomplete answer file.", error_type="incomplete_answers")
                if prompts and all(records[p["id"]].get("error_type") == "unreachable" for p in prompts):
                    raise SubmissionFailed(SERVICE_MESSAGE, records=records)
                entry["status"] = "ok"
                return records
            except Exception as exc:
                entry.update(status="failed", error_type=error_type(
                    exc.error_type if isinstance(exc, SubmissionFailed) else "client_error"))
                records = getattr(exc, "records", None) or records
                raise
            finally:
                # Never copy a record wholesale: answers and exception messages can contain CV text.
                for prompt in prompts:
                    record = records.get(prompt["id"], {}) if isinstance(records, dict) else {}
                    record = record if isinstance(record, dict) else {}
                    attempts = record.get("attempts")
                    attempts = attempts if type(attempts) is int and attempts in (1, 2) else 0
                    call = {"id": prompt["id"], "status": record.get("status", "not_returned"),
                            "attempts": attempts, "retries": max(0, attempts - 1),
                            "prompt_tokens": _number(record.get("prompt_tokens")),
                            "completion_tokens": _number(record.get("completion_tokens")),
                            "elapsed_seconds": _number(record.get("elapsed_seconds")),
                            "errors": [error_type(e) for e in record.get("errors", [])]
                            if isinstance(record.get("errors"), list) else []}
                    if call["status"] not in ("ok", "failed", "not_returned"):
                        call["status"] = "failed"
                    if "error_type" in record:
                        call["error_type"] = error_type(record["error_type"])
                    entry["calls"].append(call)
                entry.update(finished_at=_now(), elapsed_seconds=time.perf_counter() - started)
                self.save()
        return submit

    def job(self, job_id, grade, claims, failure=None):
        entry = {"job_id": job_id, "grade": grade, "claims": claims}
        if failure:
            entry["error_type"] = error_type(failure)
        self.data["jobs"].append(entry)
        self.save()


def latency_summary(data_dir):
    """Read retained traces. Linear percentiles over completed (successful or failed) requests."""
    from statistics import median

    values = []
    for path in (Path(data_dir) / "traces").glob("*.json"):
        trace = json.loads(path.read_text(encoding="utf-8"))
        if trace["outcome"] in ("done", "failed"):
            values.append(trace["elapsed_seconds"])
    values.sort()
    if not values:
        return {"count": 0, "median_seconds": None, "p95_seconds": None}
    index = (len(values) - 1) * 0.95
    lo, hi = math.floor(index), math.ceil(index)
    return {"count": len(values), "median_seconds": median(values),
            "p95_seconds": values[lo] + (values[hi] - values[lo]) * (index - lo)}
