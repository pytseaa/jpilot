"""A backend that replays real Qwen answers and breaks one thing, for failure screenshots. Not part of the app.

    FAULT=invalid_output|search_crash python -m uvicorn --app-dir eval inject_faults:create --factory --port 8000

It runs on a temporary copy of the frozen snapshot, so the real traces and database stay untouched. The answers
are the ones TACC returned for the happy-path run of CV e2 (eval/out/replay/job-30771.json is its CV summary and
job-30773.json its 20 job checks), so the same jobs and quotes come back. Upload eval/cvs/e2-customer-admin-experienced.pdf.

    invalid_output  check-2 (the top-ranked job) gets two unusable replies, as the real client records them
    search_crash    the checking submission raises an unexpected error
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402

REPLAY = ROOT / "eval" / "out" / "replay"
SNAPSHOT = ROOT / "backend" / "data" / "snapshots" / "jpilot-2026-11-22.db"
TWO_BAD_REPLIES = {"status": "failed", "error_type": "invalid_json", "attempts": 2,
                   "errors": ["invalid_json", "invalid_json"], "prompt_tokens": 0, "completion_tokens": 0,
                   "elapsed_seconds": 0}


class ReplayRunner:
    def __init__(self, fault):
        self.fault = fault
        self.records = {}
        for name in ("job-30771.json", "job-30773.json"):
            self.records.update(json.loads((REPLAY / name).read_text(encoding="utf-8"))["answers"])

    def __call__(self, prompts):
        if self.fault == "search_crash" and any(p["id"].startswith("check-") for p in prompts):
            raise RuntimeError("injected fault: the checking step crashed")
        records = {p["id"]: self.records[p["id"]] for p in prompts}  # a missing id means the jobs differ from the recording
        if self.fault == "invalid_output" and "check-2" in records:
            records["check-2"] = TWO_BAD_REPLIES
        return records


def create():
    fault = os.environ["FAULT"]
    assert fault in ("invalid_output", "search_crash"), fault
    data_dir = Path(tempfile.mkdtemp(prefix="jpilot-fault-"))
    shutil.copyfile(SNAPSHOT, data_dir / "jpilot.db")
    return create_app(runner=ReplayRunner(fault), data_dir=data_dir)
