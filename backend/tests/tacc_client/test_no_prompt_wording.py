"""ADR 0002: all prompt wording lives in the backend, never in the TACC client's files."""
import re

from stub_qwen import ok

# Wording that instructs a model. Error messages and docstrings do not use it.
INSTRUCTION_WORDING = re.compile(
    r"[　-鿿＀-￯]"  # Chinese text, as in the course demo's sample prompts
    r"|\byou are\b|\byour task\b|\brespond (with|in|only)\b|\banswer (with|in|only)\b"
    r"|\b(output|return|reply) (only|just|exactly)\b|\bonly (output|return|reply)\b"
    r"|\bstep by step\b|\bas a json\b|\bjson (object|array|format)\b",
    re.IGNORECASE,
)


def client_files(client_dir):
    return [p for p in client_dir.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix in {".py", ".sh", ".conf"}]


def test_client_files_are_found(client_dir):
    names = {p.name for p in client_files(client_dir)}

    assert {"main.py", "qwen_client.py", "prompt_runner.py", "job.sh", "tuxiv.conf"} <= names


def test_client_files_contain_no_prompt_wording(client_dir):
    found = [
        f"{p.name}:{number}: {line.strip()}".encode("ascii", "backslashreplace").decode()
        for p in client_files(client_dir)
        for number, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1)
        if INSTRUCTION_WORDING.search(line)
    ]

    assert found == []


def test_the_only_model_input_is_the_prompt_from_the_prompt_file(stub_qwen, run_client):
    # No system message and no added instruction: the request holds the prompt and nothing else.
    stub_qwen.script("exact text 你好", ok("{}"))

    run_client([{"id": "c1", "prompt": "exact text 你好"}])

    assert stub_qwen.requests[0]["messages"] == [{"role": "user", "content": "exact text 你好"}]
