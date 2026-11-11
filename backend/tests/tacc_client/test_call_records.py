"""What each answer record carries for the backend's trace: tokens and elapsed seconds."""
from stub_qwen import COMPLETION_TOKENS, PROMPT_TOKENS, http_error, ok


def test_answer_records_token_counts_and_elapsed_seconds(stub_qwen, run_client):
    stub_qwen.script("slow-ish", ok('{"a": 1}', delay=0.3))

    answers = run_client([{"id": "c1", "prompt": "slow-ish", "required_keys": ["a"]}])

    assert answers["c1"]["prompt_tokens"] == PROMPT_TOKENS
    assert answers["c1"]["completion_tokens"] == COMPLETION_TOKENS
    assert 0.3 <= answers["c1"]["elapsed_seconds"] < 5


def test_a_retried_call_records_the_totals_of_both_attempts(stub_qwen, run_client):
    stub_qwen.script("again", ok("nope", delay=0.2), ok('{"a": 1}', delay=0.2))

    answers = run_client([{"id": "c1", "prompt": "again", "required_keys": ["a"]}])

    assert answers["c1"]["prompt_tokens"] == 2 * PROMPT_TOKENS
    assert answers["c1"]["completion_tokens"] == 2 * COMPLETION_TOKENS
    assert 0.4 <= answers["c1"]["elapsed_seconds"] < 5


def test_a_failed_call_still_records_its_tokens_and_elapsed_seconds(stub_qwen, run_client):
    stub_qwen.script("bad", ok("nope", delay=0.2), ok("nope again", delay=0.2))
    stub_qwen.script("down", http_error(500, delay=0.2))

    answers = run_client([
        {"id": "bad", "prompt": "bad", "required_keys": ["a"]},
        {"id": "down", "prompt": "down", "required_keys": ["a"]},
    ])

    assert answers["bad"]["prompt_tokens"] == 2 * PROMPT_TOKENS
    assert answers["bad"]["completion_tokens"] == 2 * COMPLETION_TOKENS
    assert 0.4 <= answers["bad"]["elapsed_seconds"] < 5
    # No reply arrived, so no tokens were counted.
    assert answers["down"]["prompt_tokens"] == 0
    assert answers["down"]["completion_tokens"] == 0
    assert 0.2 <= answers["down"]["elapsed_seconds"] < 5
