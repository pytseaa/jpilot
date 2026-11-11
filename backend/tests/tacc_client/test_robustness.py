"""One misbehaving call, or reply, must never cost the other calls their answers."""
import json

import prompt_runner
from stub_qwen import cut_short, ok


def test_a_reply_cut_short_is_retried_and_can_succeed(stub_qwen, run_client):
    stub_qwen.script("flaky", cut_short(), ok('{"a": 1}'))

    answers = run_client([{"id": "c1", "prompt": "flaky", "required_keys": ["a"]}])

    assert answers["c1"]["status"] == "ok"
    assert answers["c1"]["attempts"] == 2


def test_a_reply_cut_short_twice_fails_that_call_only(stub_qwen, run_client):
    stub_qwen.script("flaky", cut_short())
    stub_qwen.script("fine", ok('{"a": 1}'))

    answers = run_client([
        {"id": "flaky", "prompt": "flaky", "required_keys": ["a"]},
        {"id": "fine", "prompt": "fine", "required_keys": ["a"]},
    ])

    assert answers["flaky"]["status"] == "failed"
    assert answers["flaky"]["error_type"] == "bad_response"
    assert answers["fine"]["status"] == "ok"


def test_a_runaway_answer_of_open_brackets_is_an_invalid_answer(stub_qwen, run_client):
    stub_qwen.script("loop", ok("[" * 5000))
    stub_qwen.script("fine", ok('{"a": 1}'))

    answers = run_client([
        {"id": "loop", "prompt": "loop", "required_keys": ["a"]},
        {"id": "fine", "prompt": "fine", "required_keys": ["a"]},
    ])

    assert answers["loop"]["status"] == "failed"
    assert answers["loop"]["error_type"] == "invalid_json"
    assert answers["fine"]["status"] == "ok"


def test_text_that_cannot_be_encoded_still_gives_a_complete_answer_file(stub_qwen, tmp_path):
    stub_qwen.script("odd", ok('{"a": "\\ud800"}'))  # a lone surrogate, valid JSON text
    answers_path = tmp_path / "answers.json"

    prompt_runner.run([{"id": "c1", "prompt": "odd", "required_keys": ["a"]}],
                      answers_path, stub_qwen.base_url)

    answers = json.loads(answers_path.read_text(encoding="utf-8"))["answers"]
    assert answers["c1"]["status"] == "ok"
    assert answers["c1"]["answer"] == {"a": "\ud800"}


def test_unusable_token_counts_never_cost_a_good_answer(stub_qwen, run_client):
    stub_qwen.script("no-usage", ok('{"a": 1}', usage=None))
    stub_qwen.script("odd-usage", ok('{"a": 1}', usage={"prompt_tokens": None,
                                                         "completion_tokens": "many"}))
    stub_qwen.script("list-usage", ok('{"a": 1}', usage=[1, 2]))

    answers = run_client([
        {"id": name, "prompt": name, "required_keys": ["a"]}
        for name in ("no-usage", "odd-usage", "list-usage")
    ])

    for name in ("no-usage", "odd-usage", "list-usage"):
        assert answers[name]["status"] == "ok"
        assert answers[name]["prompt_tokens"] == 0
        assert answers[name]["completion_tokens"] == 0


def test_a_call_that_breaks_unexpectedly_is_recorded_and_the_others_continue(stub_qwen, tmp_path):
    stub_qwen.script("fine", ok('{"a": 1}'))
    answers_path = tmp_path / "answers.json"

    # No "prompt" text: a malformed item that slipped past the prompt file checks.
    prompt_runner.run([{"id": "broken"}, {"id": "fine", "prompt": "fine"}],
                      answers_path, stub_qwen.base_url)

    answers = json.loads(answers_path.read_text(encoding="utf-8"))["answers"]
    assert answers["broken"]["status"] == "failed"
    assert answers["broken"]["error_type"] == "client_error"
    assert answers["fine"]["status"] == "ok"
