"""The ingestion command: `python -m app.ingest [--snapshot]`, run from the backend folder."""
import shutil
import sys
from contextlib import closing
from datetime import date

from app import db
from app.jsearch import JSearch
from app.runners.default import default_runner
from app.runners.tacc import SubmissionFailed
from app.services.ingestion import run


def main(argv, search=None, runner=None, data_dir=None, today=None):
    """Run one ingestion and print its report. Return the exit code."""
    data_dir = data_dir or db.DEFAULT_DATA_DIR
    today = today or date.today().isoformat()
    snapshot = data_dir / "snapshots" / f"jpilot-{today}.db" if "--snapshot" in argv else None
    # Refused before any request, so a run that cannot be frozen never spends JSearch quota.
    if snapshot and snapshot.exists():
        print(f"A snapshot for {today} already exists: {snapshot}. A frozen snapshot is never "
              "overwritten.", file=sys.stderr)
        return 1
    try:
        search = search or JSearch.from_environment()
        runner = runner or default_runner()
    except ValueError as exc:  # a missing JSEARCH_API_KEY or a bad JPILOT_RUNNER: say so, no traceback
        print(exc, file=sys.stderr)
        return 2
    try:
        with closing(db.connect(data_dir)) as conn:
            report = run(search, runner, conn, today)
    except SubmissionFailed as exc:  # no report and no snapshot for a run that did not finish
        print(exc, file=sys.stderr)
        return 1
    if report.failed_requests and not report.fetched:  # nothing to freeze, and the quota may be used up
        print(f"JSearch gave no jobs: all {report.failed_requests} requests failed.", file=sys.stderr)
        return 1
    print(f"Jobs fetched: {report.fetched}\n"
          f"Stored: {report.stored}\n"
          f"Already stored: {report.already_stored}\n"
          f"Dropped as mostly Chinese: {report.dropped_chinese}\n"
          f"Dropped with no description: {report.dropped_no_description}\n"
          f"Failed at extraction: {report.failed_extraction}\n"
          f"Failed JSearch requests: {report.failed_requests}")
    if snapshot:
        snapshot.parent.mkdir(exist_ok=True)
        shutil.copyfile(data_dir / "jpilot.db", snapshot)  # after the connection closes, so the file is complete
        print(f"Snapshot: {snapshot}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
