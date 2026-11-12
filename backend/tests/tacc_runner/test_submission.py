"""The real runner, driven through a fake tcloud that writes NUL bytes and errors on a finished job."""
import json

from fake_tcloud import FIRST_JOB

PROMPTS = [{"id": "cv-summary", "prompt": "Read this CV.", "required_keys": ["summary"]}]
OK = {"status": "ok", "answer": {"summary": "Analyst."}}


def test_the_runner_returns_the_records_the_job_wrote(tcloud, runner):
    # The fake's output has NUL bytes in it and other numbers before the job number, so the
    # answer file of job 4242 can only be found if the number is read from "Submitted batch job N".
    tcloud.will_answer({"cv-summary": OK})

    assert runner(PROMPTS) == {"cv-summary": OK}


def test_the_runner_waits_until_the_status_command_errors_because_the_job_finished(tcloud, runner):
    tcloud.will_answer({"cv-summary": OK})
    tcloud.keep_running_for(3)

    assert runner(PROMPTS) == {"cv-summary": OK}
    assert [call[:2] for call in tcloud.calls()].count(["ps", "-j"]) == 4  # 3 running, then the error


def test_the_prompt_file_is_uploaded_with_the_folder(tcloud, runner):
    tcloud.will_answer({"cv-summary": OK})

    runner(PROMPTS)

    assert json.loads(tcloud.submitted(FIRST_JOB)["prompts.json"]) == {"prompts": PROMPTS}


def test_the_job_is_submitted_from_the_client_folder_itself(tcloud, runner, client_dir):
    tcloud.will_answer({"cv-summary": OK})

    runner(PROMPTS)

    assert tcloud.submitted_from() == client_dir.resolve()


def test_the_prompt_file_is_removed_once_the_call_is_over(tcloud, runner, client_dir):
    # The prompt file holds CV text, so it must not stay in the folder after the call.
    tcloud.will_answer({"cv-summary": OK})

    runner(PROMPTS)

    assert not (client_dir / "prompts.json").exists()
