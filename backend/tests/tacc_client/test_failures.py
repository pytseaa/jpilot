from stub_qwen import http_error, ok


def test_http_error_fails_that_call_and_the_other_calls_continue(stub_qwen, run_client):
    stub_qwen.script("broken", http_error(503))
    stub_qwen.script("fine", ok('{"city": "Oslo"}'))

    answers = run_client([
        {"id": "broken", "prompt": "broken", "required_keys": ["city"]},
        {"id": "fine", "prompt": "fine", "required_keys": ["city"]},
    ])

    assert answers["broken"]["status"] == "failed"
    assert answers["broken"]["error_type"] == "http_error"
    assert answers["fine"]["status"] == "ok"
    assert answers["fine"]["answer"] == {"city": "Oslo"}
    # The retry is for bad answers only; an HTTP error is not retried.
    assert stub_qwen.call_count("broken") == 1


def test_timeout_fails_that_call_with_its_error_type_and_the_others_continue(stub_qwen, run_client):
    stub_qwen.script("slow", ok('{"city": "Bern"}', delay=1.0))
    stub_qwen.script("quick", ok('{"city": "Lima"}'))

    answers = run_client([
        {"id": "slow", "prompt": "slow", "required_keys": ["city"]},
        {"id": "quick", "prompt": "quick", "required_keys": ["city"]},
    ], timeout=0.2)

    assert answers["slow"]["status"] == "failed"
    assert answers["slow"]["error_type"] == "timeout"
    assert stub_qwen.call_count("slow") == 1
    assert answers["quick"]["status"] == "ok"
    assert answers["quick"]["answer"] == {"city": "Lima"}


def test_each_call_is_given_300_seconds_unless_a_test_shortens_it(monkeypatch, stub_qwen, tmp_path):
    import prompt_runner
    import qwen_client

    stub_qwen.script("p", ok("{}"))
    timeouts = []
    real_urlopen = qwen_client.urlopen
    monkeypatch.setattr(qwen_client, "urlopen",
                        lambda request, timeout: timeouts.append(timeout) or
                        real_urlopen(request, timeout=timeout))

    prompt_runner.run([{"id": "c1", "prompt": "p"}], tmp_path / "answers.json", stub_qwen.base_url)

    assert timeouts == [300]


def test_unreachable_service_fails_the_call(stub_qwen, run_client):
    stub_qwen.stop()  # nothing listens on the stub's port any more

    answers = run_client([{"id": "lost", "prompt": "anyone there?"}])

    assert answers["lost"]["status"] == "failed"
    assert answers["lost"]["error_type"] == "unreachable"
