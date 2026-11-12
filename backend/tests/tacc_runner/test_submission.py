"""The real runner, driven through a fake tcloud that writes NUL bytes and errors on a finished job."""
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
