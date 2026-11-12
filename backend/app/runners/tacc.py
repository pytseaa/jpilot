"""The real runner: one TACC submission through the tcloud command.

Same contract as FakeRunner: takes the prompt list, returns the answer file's records by id."""
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parents[2] / "tacc_qwen_client"
# Other numbers in the output are dates and versions; only this phrase holds the job number.
JOB_NUMBER = re.compile(r"Submitted batch job (\d+)")


class TaccRunner:
    def __init__(self, tcloud=("tcloud",), client_dir=CLIENT_DIR, poll_seconds=5):
        self.tcloud = list(tcloud)
        self.client_dir = client_dir
        self.poll_seconds = poll_seconds

    def __call__(self, prompts):
        prompt_file = self.client_dir / "prompts.json"  # holds CV text, so it goes as soon as the call ends
        try:
            prompt_file.write_text(json.dumps({"prompts": prompts}), encoding="utf-8")
            job = JOB_NUMBER.search(self._run("submit", cwd=self.client_dir)[1]).group(1)
            # tcloud reports an error for a job that has finished, so an error means "done".
            while self._run("ps", "-j", job)[0] == 0:
                time.sleep(self.poll_seconds)
            with tempfile.TemporaryDirectory() as tmp:
                answers = Path(tmp) / "answers.json"
                self._run("download", f"jpilot-tacc-client/job-{job}.json", str(answers))
                return json.loads(answers.read_text(encoding="utf-8"))["answers"]
        finally:
            prompt_file.unlink(missing_ok=True)

    def _run(self, *args, cwd=None):
        """Run tcloud. Return its exit code and its output with the NUL bytes it writes removed."""
        done = subprocess.run([*self.tcloud, *args], cwd=cwd, capture_output=True)
        return done.returncode, (done.stdout + done.stderr).replace(b"\0", b"").decode(errors="replace")
