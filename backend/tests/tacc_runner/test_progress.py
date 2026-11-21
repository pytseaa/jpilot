"""Ticket 12: the count of jobs checked, read from the running log.

The TACC client prints one 'CALL_DONE <n> of <total>: <id> <outcome>' line per
finished call. The runner reads that log while the job runs and reports the
highest count it has seen. A log that is empty, partly written or unreadable
never crashes the poll, and the count never goes down between two polls."""
import json

from fake_tcloud import FIRST_JOB

PROMPTS = [{"id": f"check-{i}", "prompt": "Read this.", "required_keys": ["grade"]} for i in range(3)]
OK = {"status": "ok", "answer": {"grade": 2}}
ANSWERS = {f"check-{i}": OK for i in range(3)}


def test_progress_rises_as_the_log_grows(tcloud, runner):
    tcloud.will_answer(ANSWERS)
    tcloud.keep_running_for(3)  # three running polls, then the job finishes
    tcloud.will_grow_log([
        "CALL_DONE 1 of 3: check-0 ok",
        "CALL_DONE 1 of 3: check-0 ok\nCALL_DONE 2 of 3: check-1 ok",
        "CALL_DONE 1 of 3: check-0 ok\nCALL_DONE 2 of 3: check-1 ok\nCALL_DONE 3 of 3: check-2 ok",
    ])
    seen = []
    runner.progress = lambda checked, total: seen.append((checked, total))

    runner(PROMPTS)

    assert seen == [(1, 3), (2, 3), (3, 3)]  # the count rises with each poll


def test_progress_is_silent_when_the_log_cannot_be_read(tcloud, runner):
    tcloud.will_answer(ANSWERS)
    tcloud.keep_running_for(2)
    # no will_grow_log and no will_log: cat returns an error, as when the log is not there yet
    seen = []
    runner.progress = lambda checked, total: seen.append((checked, total))

    runner(PROMPTS)

    assert seen == []  # the log could not be read, so progress stayed silent


def test_progress_is_silent_when_the_log_is_empty(tcloud, runner):
    tcloud.will_answer(ANSWERS)
    tcloud.keep_running_for(2)
    tcloud.will_log("")  # the job started, but no call has finished yet
    seen = []
    runner.progress = lambda checked, total: seen.append((checked, total))

    runner(PROMPTS)

    assert seen == []  # no CALL_DONE line yet, so no count to report


def test_the_count_never_goes_down_even_if_the_log_does(tcloud, runner):
    tcloud.will_answer(ANSWERS)
    tcloud.keep_running_for(3)
    # The second snapshot has a smaller count, as a line was lost or the log rewrote.
    tcloud.will_grow_log([
        "CALL_DONE 2 of 3: check-1 ok",
        "CALL_DONE 1 of 3: check-0 ok",
        "CALL_DONE 3 of 3: check-2 ok",
    ])
    seen = []
    runner.progress = lambda checked, total: seen.append((checked, total))

    runner(PROMPTS)

    assert [c for c, _ in seen] == [2, 3]  # 1 is dropped: the count never goes down from 2 to 1


def test_a_partly_written_line_is_ignored(tcloud, runner):
    two = [{"id": f"check-{i}", "prompt": "Read this.", "required_keys": ["grade"]} for i in range(2)]
    tcloud.will_answer({f"check-{i}": OK for i in range(2)})
    tcloud.keep_running_for(2)
    tcloud.will_grow_log([
        "CALL_DONE 1 of 2: check-0 ok\nCALL_D",  # a line cut short mid-write
        "CALL_DONE 1 of 2: check-0 ok\nCALL_DONE 2 of 2: check-1 ok",
    ])
    seen = []
    runner.progress = lambda checked, total: seen.append((checked, total))

    runner(two)

    assert [c for c, _ in seen] == [1, 2]  # the half-line never crashes the poll


def test_progress_is_silent_when_no_one_is_listening(tcloud, runner):
    tcloud.will_answer(ANSWERS)
    tcloud.keep_running_for(2)
    tcloud.will_grow_log(["CALL_DONE 1 of 3: check-0 ok"])
    # runner.progress stays None: the backend sets it only during a real search

    records = runner(PROMPTS)  # must not crash

    assert records == ANSWERS  # the submission still works with no progress listener
