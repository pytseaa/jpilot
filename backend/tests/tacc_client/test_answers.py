from stub_qwen import ok


def test_valid_answer_is_written_under_its_prompt_id(stub_qwen, run_client):
    stub_qwen.script("What is 2+2?", ok('{"result": 4}'))

    answers = run_client([
        {"id": "sum-1", "prompt": "What is 2+2?", "required_keys": ["result"]},
    ])

    assert answers["sum-1"]["status"] == "ok"
    assert answers["sum-1"]["answer"] == {"result": 4}


def test_invalid_answer_then_valid_one_succeeds_on_the_retry(stub_qwen, run_client):
    stub_qwen.script("Name a city", ok("not json at all"), ok('{"city": "Paris"}'))

    answers = run_client([
        {"id": "city-1", "prompt": "Name a city", "required_keys": ["city"]},
    ])

    assert answers["city-1"]["status"] == "ok"
    assert answers["city-1"]["answer"] == {"city": "Paris"}
    assert answers["city-1"]["attempts"] == 2
    assert stub_qwen.call_count("Name a city") == 2


def test_two_invalid_answers_fail_that_call_and_leave_the_others_alone(stub_qwen, run_client):
    stub_qwen.script("bad prompt", ok("garbage"), ok("still garbage"))
    stub_qwen.script("good prompt", ok('{"city": "Rome"}'))

    answers = run_client([
        {"id": "bad", "prompt": "bad prompt", "required_keys": ["city"]},
        {"id": "good", "prompt": "good prompt", "required_keys": ["city"]},
    ])

    assert answers["bad"]["status"] == "failed"
    assert answers["bad"]["error_type"] == "invalid_json"
    assert answers["bad"]["attempts"] == 2
    assert stub_qwen.call_count("bad prompt") == 2  # retried once, not more
    assert answers["good"]["status"] == "ok"
    assert answers["good"]["answer"] == {"city": "Rome"}


def test_answer_missing_a_required_key_is_retried(stub_qwen, run_client):
    stub_qwen.script("Grade it", ok('{"grade": 2}'), ok('{"grade": 2, "claims": []}'))

    answers = run_client([
        {"id": "check-1", "prompt": "Grade it", "required_keys": ["grade", "claims"]},
    ])

    assert answers["check-1"]["status"] == "ok"
    assert answers["check-1"]["answer"] == {"grade": 2, "claims": []}
    assert answers["check-1"]["attempts"] == 2


def test_json_that_is_not_an_object_lacks_the_required_keys(stub_qwen, run_client):
    # A list holding the key name is still not an object that has the key.
    stub_qwen.script("Grade it", ok('["grade"]'), ok('"grade"'))

    answers = run_client([
        {"id": "check-1", "prompt": "Grade it", "required_keys": ["grade"]},
    ])

    assert answers["check-1"]["status"] == "failed"
    assert answers["check-1"]["error_type"] == "missing_key"


def test_answer_missing_a_required_key_twice_is_a_failed_call(stub_qwen, run_client):
    stub_qwen.script("Grade it", ok('{"grade": 2}'), ok('{"claims": []}'))

    answers = run_client([
        {"id": "check-1", "prompt": "Grade it", "required_keys": ["grade", "claims"]},
    ])

    assert answers["check-1"]["status"] == "failed"
    assert answers["check-1"]["error_type"] == "missing_key"
    assert answers["check-1"]["attempts"] == 2
