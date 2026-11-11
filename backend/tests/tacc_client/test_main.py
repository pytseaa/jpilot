"""main.py run the way job.sh runs it: from the copied client folder, with job.sh's env vars."""
import json
import os
import shutil
import subprocess
import sys

import pytest

from stub_qwen import http_error, ok

RESULT = "jpilot-tacc-client/job-4242.json"


def run_main(tmp_path, client_dir, stub_qwen, prompt_file_text):
    workdir = tmp_path / "workdir"
    shutil.copytree(client_dir, workdir)
    (workdir / "prompts.json").write_text(prompt_file_text, encoding="utf-8")
    userdir = tmp_path / "userdir"
    env = {**os.environ,
           "QWEN_BASE_URL": stub_qwen.base_url,
           "TACC_WORKDIR": str(workdir),
           "TACC_USERDIR": str(userdir),
           "SLURM_JOB_ID": "4242"}
    process = subprocess.run([sys.executable, "-u", "main.py"], cwd=workdir, env=env,
                             capture_output=True, text=True, encoding="utf-8", timeout=60)
    return process, userdir


def test_main_writes_the_answer_file_where_the_backend_downloads_it(tmp_path, client_dir, stub_qwen):
    stub_qwen.script("2+2?", ok('{"result": 4}'))
    prompt_file = json.dumps({"prompts": [
        {"id": "sum", "prompt": "2+2?", "required_keys": ["result"]}]})

    process, userdir = run_main(tmp_path, client_dir, stub_qwen, prompt_file)

    assert process.returncode == 0, process.stderr
    assert f"RESULT_FILE={RESULT}" in process.stdout.splitlines()
    answers = json.loads((userdir / RESULT).read_text(encoding="utf-8"))["answers"]
    assert answers["sum"]["answer"] == {"result": 4}


def test_main_logs_one_line_per_finished_call_so_progress_can_be_counted(
        tmp_path, client_dir, stub_qwen):
    # The backend reads this running log with `tcloud cat` to show "n of 20 jobs checked".
    stub_qwen.script("good", ok('{"a": 1}'))
    stub_qwen.script("bad", http_error(500))
    prompt_file = json.dumps({"prompts": [
        {"id": "job-1", "prompt": "good", "required_keys": ["a"]},
        {"id": "job-2", "prompt": "bad", "required_keys": ["a"]}]})

    process, _ = run_main(tmp_path, client_dir, stub_qwen, prompt_file)

    lines = [line for line in process.stdout.splitlines() if line.startswith("CALL_DONE")]
    assert sorted(line.split()[1:4] for line in lines) == [["1", "of", "2:"], ["2", "of", "2:"]]
    assert any("job-1 ok" in line for line in lines)
    assert any("job-2 failed http_error" in line for line in lines)


def test_the_log_never_holds_prompt_or_answer_text(tmp_path, client_dir, stub_qwen):
    stub_qwen.script("SECRET-PROMPT-TEXT", ok('{"a": "SECRET-ANSWER-TEXT"}'))
    prompt_file = json.dumps({"prompts": [
        {"id": "job-1", "prompt": "SECRET-PROMPT-TEXT", "required_keys": ["a"]}]})

    process, _ = run_main(tmp_path, client_dir, stub_qwen, prompt_file)

    assert "SECRET" not in process.stdout + process.stderr


BAD_PROMPT_FILES = {
    "not json": "this is not json",
    "no prompts list": json.dumps({"questions": []}),
    "prompt without id": json.dumps({"prompts": [{"prompt": "hi"}]}),
    "prompt without text": json.dumps({"prompts": [{"id": "a"}]}),
    # Two answers under one id would silently overwrite each other.
    "duplicate ids": json.dumps({"prompts": [{"id": "a", "prompt": "x"},
                                             {"id": "a", "prompt": "y"}]}),
    # A string would be read as one key per letter.
    "required_keys is text": json.dumps({"prompts": [{"id": "a", "prompt": "x",
                                                      "required_keys": "grade"}]}),
    "required_keys holds a number": json.dumps({"prompts": [{"id": "a", "prompt": "x",
                                                             "required_keys": [1]}]}),
    "max_tokens is text": json.dumps({"prompts": [{"id": "a", "prompt": "x",
                                                   "max_tokens": "many"}]}),
}


@pytest.mark.parametrize("prompt_file", BAD_PROMPT_FILES.values(), ids=BAD_PROMPT_FILES.keys())
def test_main_exits_with_an_error_when_the_prompt_file_is_unusable(
        tmp_path, client_dir, stub_qwen, prompt_file):
    process, userdir = run_main(tmp_path, client_dir, stub_qwen, prompt_file)

    assert process.returncode != 0
    assert "prompts.json" in process.stderr
    assert "Traceback" not in process.stderr
    assert stub_qwen.requests == []
    assert not (userdir / RESULT).exists()
