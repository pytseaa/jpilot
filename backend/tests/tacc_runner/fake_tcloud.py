"""A stand-in for the tcloud command that needs no TACC. Standard library only.

It copies the output shapes the TACC probe saw on the real tool: NUL bytes in the output, other
numbers before the job number, and an error from `ps -j` once a job has finished.
Everything it keeps is in the folder named by FAKE_TCLOUD_HOME:
    answers.json     what the job writes as the "answers" of its answer file (set by the test)
    running_polls    how many `ps -j` calls still show the job running (default 0)
    calls.jsonl      one line per command run
    submissions/<n>/ a copy of the folder each `submit` was run in
    userdir/         the user's folder on TACC
"""
import json
import os
import shutil
import sys
from pathlib import Path

FIRST_JOB = 4242


class FakeTcloud:
    """The test's side of the fake: set it up, then read what the runner did."""

    def __init__(self, home):
        self.home = Path(home)

    @property
    def command(self):
        return [sys.executable, str(Path(__file__))]

    def will_answer(self, answers):
        (self.home / "answers.json").write_text(json.dumps(answers), encoding="utf-8")

    def keep_running_for(self, polls):
        (self.home / "running_polls").write_text(str(polls), encoding="utf-8")

    def calls(self):
        text = (self.home / "calls.jsonl").read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines()]

    def submitted(self, job=FIRST_JOB):
        """The files of one submission, by name."""
        return {p.name: p.read_bytes() for p in (self.home / "submissions" / str(job)).iterdir()}


def say(text, stream):
    # The real tool puts NUL bytes in its output. One between every character is the worst case.
    stream.buffer.write("\0".join(text).encode() + b"\n")
    stream.flush()


def running_polls(home):
    path = home / "running_polls"
    return int(path.read_text(encoding="utf-8")) if path.exists() else 0


def finish(home, job):
    answers = json.loads((home / "answers.json").read_text(encoding="utf-8"))
    path = home / "userdir" / "jpilot-tacc-client" / f"job-{job}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"answers": answers}), encoding="utf-8")


def submit(home):
    submissions = home / "submissions"
    job = FIRST_JOB + (len(list(submissions.iterdir())) if submissions.exists() else 0)
    shutil.copytree(Path.cwd(), submissions / str(job))
    say("tcloud 0.4.1 2026-11-10 uploaded 5632 bytes in 9 seconds", sys.stdout)
    say(f"Submitted batch job {job}", sys.stdout)
    return 0


def ps(home, job):
    counter = home / f"ps-{job}"
    count = int(counter.read_text(encoding="utf-8")) + 1 if counter.exists() else 1
    counter.write_text(str(count), encoding="utf-8")
    if count <= running_polls(home):
        say(f"JOBID PARTITION NAME USER ST TIME NODES\n{job} tacc jpilot-tacc-client me R 0:05 1",
            sys.stdout)
        return 0
    finish(home, job)
    say(f"Error: job {job} not found", sys.stderr)
    return 1


def download(home, remote, local):
    source = home / "userdir" / remote
    if not source.exists():
        say(f"Error: {remote} not found", sys.stderr)
        return 1
    shutil.copyfile(source, local)
    return 0


def main(args):
    home = Path(os.environ["FAKE_TCLOUD_HOME"])
    with open(home / "calls.jsonl", "a", encoding="utf-8") as calls:
        calls.write(json.dumps(args) + "\n")
    if args[:1] == ["submit"]:
        return submit(home)
    if args[:2] == ["ps", "-j"]:
        return ps(home, args[2])
    if args[:1] == ["download"]:
        return download(home, args[1], args[2])
    say(f"Error: unknown command {args}", sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
