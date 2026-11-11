from stub_qwen import ok


def test_max_tokens_in_the_prompt_file_limits_that_call_only(stub_qwen, run_client):
    stub_qwen.script("limited", ok("{}"))
    stub_qwen.script("default", ok("{}"))

    run_client([
        {"id": "a", "prompt": "limited", "max_tokens": 77},
        {"id": "b", "prompt": "default"},
    ])

    sent = {r["messages"][-1]["content"]: r["max_tokens"] for r in stub_qwen.requests}
    assert sent["limited"] == 77
    assert sent["default"] > 256  # room for quotes and claims, not the demo's 256


def test_first_attempt_is_deterministic_and_the_retry_is_not(stub_qwen, run_client):
    # Evaluation runs must repeat, but a retry at temperature 0 would just repeat the bad answer.
    stub_qwen.script("p", ok("not json"), ok("{}"))

    run_client([{"id": "c1", "prompt": "p"}])

    first, retry = stub_qwen.requests
    assert first["temperature"] == 0
    assert retry["temperature"] > 0
