"""The real runner: one TACC submission through the tcloud command.

Same contract as FakeRunner: takes the prompt list, returns the answer file's records by id."""
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
from threading import Lock

CLIENT_DIR = Path(__file__).resolve().parents[2] / "tacc_qwen_client"
# Other numbers in the output are dates and versions; only this phrase holds the job number.
JOB_NUMBER = re.compile(r"Submitted batch job (\d+)")


SERVICE_MESSAGE = ("The Qwen service could not be reached. Please restart the service, "
                   "then update its address in server-url.txt.")


class SubmissionFailed(Exception):
    """The TACC submission did not run. The message is for the candidate."""

    def __init__(self, message, records=None, error_type="submission_failed"):
        super().__init__(message)
        self.records = records
        self.error_type = "unreachable" if message == SERVICE_MESSAGE else error_type


class TaccRunner:
    def __init__(self, tcloud=("tcloud",), client_dir=CLIENT_DIR, poll_seconds=5,
                 submission_timeout=3600, command_timeout=120):
        self.tcloud = list(tcloud)
        self.client_dir = client_dir
        self.poll_seconds = poll_seconds
        self.submission_timeout = submission_timeout
        self.command_timeout = command_timeout
        self._lock = Lock()

    def __call__(self, prompts):
        # Intake from a second tab must not overwrite a running submission's CV-bearing file.
        with self._lock:
            return self._submit(prompts)

    def _submit(self, prompts):
        deadline = time.monotonic() + self.submission_timeout
        prompt_file = self.client_dir / "prompts.json"  # holds CV text, so it goes as soon as the call ends
        try:
            prompt_file.write_text(json.dumps({"prompts": prompts}), encoding="utf-8")
            code, output = self._run("submit", cwd=self.client_dir)
            found = JOB_NUMBER.search(output)
            if code != 0 or found is None:
                raise SubmissionFailed("The TACC submission failed. Please check the TACC submission status and try again.")
            job = found.group(1)
            # tcloud reports an error for a job that has finished, so an error means "done".
            while self._run("ps", "-j", job)[0] == 0:
                if time.monotonic() >= deadline:
                    raise SubmissionFailed("The TACC submission timed out.", error_type="timeout")
                time.sleep(self.poll_seconds)
            with tempfile.TemporaryDirectory() as tmp:
                answers = Path(tmp) / "answers.json"
                code, _ = self._run("download", f"jpilot-tacc-client/job-{job}.json", str(answers))
                if code != 0:
                    raise SubmissionFailed("The TACC answers could not be downloaded. Please try again.", error_type="download_failed")
                try:
                    records = json.loads(answers.read_text(encoding="utf-8"))["answers"]
                    if (not isinstance(records, dict)
                            or any(not isinstance(records.get(p["id"]), dict)
                                   or records[p["id"]].get("status") not in ("ok", "failed")
                                   or (records[p["id"]]["status"] == "ok" and "answer" not in records[p["id"]])
                                   for p in prompts)):
                        raise ValueError("incomplete answer file")
                except (OSError, ValueError, KeyError, TypeError):  # no file, or not the shape we wrote
                    raise SubmissionFailed("The TACC submission returned an incomplete answer file. Please try again.",
                                           error_type="incomplete_answers") from None
            # Only the Qwen service is down when no call got through; one bad call is not that.
            if records and all(r.get("error_type") == "unreachable" for r in records.values()):
                raise SubmissionFailed(SERVICE_MESSAGE, records=records)
            return records
        finally:
            prompt_file.unlink(missing_ok=True)

    def _run(self, *args, cwd=None):
        """Run tcloud. Return its exit code and its output with the NUL bytes it writes removed."""
        try:
            done = subprocess.run([*self.tcloud, *args], cwd=cwd, capture_output=True,
                                  timeout=self.command_timeout)
        except subprocess.TimeoutExpired:
            raise SubmissionFailed("The TACC command timed out.", error_type="timeout") from None
        except OSError:
            raise SubmissionFailed("The tcloud command could not be started. Check that tcloud is installed and configured.",
                                   error_type="command_unavailable") from None
        return done.returncode, (done.stdout + done.stderr).replace(b"\0", b"").decode(errors="replace")
