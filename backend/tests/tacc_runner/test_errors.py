"""Each way a submission can fail ends in one clear error for the user, not a traceback."""
import pytest

from app.runners.tacc import SubmissionFailed, TaccRunner

PROMPTS = [{"id": "cv-summary", "prompt": "Read this CV."}]


def test_a_missing_tcloud_asks_the_user_to_restart_the_service(client_dir):
    runner = TaccRunner(tcloud=["no-such-tcloud-for-tests"], client_dir=client_dir, poll_seconds=0)

    with pytest.raises(SubmissionFailed, match="restart"):
        runner(PROMPTS)


def test_a_submission_that_exits_with_an_error_asks_the_user_to_restart_the_service(tcloud, runner):
    tcloud.will_print_on_submit("Error: quota exceeded", exit_code=1)

    with pytest.raises(SubmissionFailed, match="restart"):
        runner(PROMPTS)


def test_a_finished_job_with_no_answer_file_asks_the_user_to_restart_the_service(tcloud, runner):
    tcloud.will_answer({"cv-summary": {"status": "ok", "answer": {}}})
    tcloud.will_not_write_answer_file()

    with pytest.raises(SubmissionFailed, match="restart"):
        runner(PROMPTS)


def test_every_call_unreachable_asks_the_user_to_restart_the_service(tcloud, runner):
    # The client still writes a complete answer file when the service is down, with every call
    # marked unreachable. That is one service failure, not a list of skipped jobs.
    tcloud.will_answer({"cv-summary": {"status": "failed", "error_type": "unreachable"}})

    with pytest.raises(SubmissionFailed, match="restart"):
        runner(PROMPTS)


def test_some_calls_failing_is_not_a_service_failure(tcloud, runner):
    # A call that fails on its own is left for the backend to count as skipped.
    prompts = [{"id": "a", "prompt": "x"}, {"id": "b", "prompt": "y"}]
    tcloud.will_answer({"a": {"status": "ok", "answer": {}},
                        "b": {"status": "failed", "error_type": "unreachable"}})

    assert runner(prompts) == {"a": {"status": "ok", "answer": {}},
                               "b": {"status": "failed", "error_type": "unreachable"}}
