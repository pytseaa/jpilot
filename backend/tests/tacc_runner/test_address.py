"""The client folder is submitted with the Qwen service address it holds at that moment."""
from fake_tcloud import FIRST_JOB

PROMPTS = [{"id": "cv-summary", "prompt": "Read this CV."}]
OK = {"status": "ok", "answer": {"summary": "Analyst."}}


def test_the_submitted_folder_holds_the_address_from_the_file(tcloud, runner):
    tcloud.will_answer({"cv-summary": OK})

    runner(PROMPTS)

    assert tcloud.submitted(FIRST_JOB)["server-url.txt"] == b"http://node-7:8000/v1\n"


def test_a_new_address_is_used_by_the_next_submission_without_a_restart(tcloud, runner, client_dir):
    tcloud.will_answer({"cv-summary": OK})
    runner(PROMPTS)

    (client_dir / "server-url.txt").write_bytes(b"http://node-9:8000/v1\n")
    runner(PROMPTS)

    assert tcloud.submitted(FIRST_JOB)["server-url.txt"] == b"http://node-7:8000/v1\n"
    assert tcloud.submitted(FIRST_JOB + 1)["server-url.txt"] == b"http://node-9:8000/v1\n"
