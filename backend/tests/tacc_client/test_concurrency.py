from stub_qwen import ok


def test_calls_overlap_but_never_more_than_four_run_at_once(stub_qwen, run_client):
    prompts = []
    for n in range(8):
        stub_qwen.script(f"prompt {n}", ok('{"n": %d}' % n, delay=0.3))
        prompts.append({"id": f"p{n}", "prompt": f"prompt {n}", "required_keys": ["n"]})

    answers = run_client(prompts)

    assert all(answers[f"p{n}"]["status"] == "ok" for n in range(8))
    assert [answers[f"p{n}"]["answer"] for n in range(8)] == [{"n": n} for n in range(8)]
    # Exactly four: the calls do overlap, and never more than four at a time.
    assert stub_qwen.peak_in_flight == 4
