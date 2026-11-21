"""Each way a submission can fail ends in one clear error for the user, not a traceback."""
import pytest

from app.runners.tacc import SubmissionFailed, TaccRunner

PROMPTS = [{"id": "cv-summary", "prompt": "Read this CV."}]


def test_a_missing_tcloud_asks_the_user_to_check_its_installation(client_dir):
    runner = TaccRunner(tcloud=["no-such-tcloud-for-tests"], client_dir=client_dir, poll_seconds=0)

    with pytest.raises(SubmissionFailed, match="installed"):
        runner(PROMPTS)


def test_a_submission_that_exits_with_an_error_reports_submission_failure(tcloud, runner):
    tcloud.will_print_on_submit("Error: quota exceeded", exit_code=1)

    with pytest.raises(SubmissionFailed, match="submission failed") as failure:
        runner(PROMPTS)
    assert failure.value.error_type == "submission_failed"


def test_a_finished_job_with_no_answer_file_reports_download_failure(tcloud, runner):
    tcloud.will_answer({"cv-summary": {"status": "ok", "answer": {}}})
    tcloud.will_not_write_answer_file()

    with pytest.raises(SubmissionFailed, match="downloaded") as failure:
        runner(PROMPTS)
    assert failure.value.error_type == "download_failed"


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


@pytest.mark.parametrize("records", [{}, [], {"cv-summary": "not a record"}, {"cv-summary": {"status": "ok"}}])
def test_incomplete_answer_files_fail_the_submission_and_remove_local_prompts(tcloud, runner, client_dir, records):
    tcloud.will_answer(records)
    with pytest.raises(SubmissionFailed):
        runner(PROMPTS)
    assert not (client_dir / "prompts.json").exists()


def test_failed_submit_removes_cv_bearing_local_prompts(tcloud, runner, client_dir):
    tcloud.will_print_on_submit("submission failed", exit_code=1)
    with pytest.raises(SubmissionFailed):
        runner([{"id": "cv-summary", "prompt": "PRIVATE-CV-MARKER"}])
    assert all(b"PRIVATE-CV-MARKER" not in p.read_bytes() for p in client_dir.rglob("*") if p.is_file())


def test_polling_timeout_fails_and_removes_local_prompts(tcloud, runner, client_dir):
    tcloud.keep_running_for(100)
    runner.submission_timeout = 0
    with pytest.raises(SubmissionFailed, match="timed out"):
        runner(PROMPTS)
    assert not (client_dir / "prompts.json").exists()


def test_failed_download_is_rejected_even_when_it_leaves_valid_json(tcloud, runner, client_dir):
    tcloud.will_answer({"cv-summary": {"status": "ok", "answer": {"summary": "PRIVATE-CV-MARKER"}}})
    tcloud.will_fail_download_after_copy()
    with pytest.raises(SubmissionFailed) as failure:
        runner(PROMPTS)
    assert failure.value.error_type == "download_failed"
    assert not (client_dir / "prompts.json").exists()
    downloaded_to = tcloud.calls()[-1][-1]
    from pathlib import Path
    assert not Path(downloaded_to).exists()
