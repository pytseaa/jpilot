import json
import sys
from pathlib import Path

import pytest

CLIENT_DIR = Path(__file__).resolve().parents[2] / "tacc_qwen_client"
# The client is a flat folder of scripts (it runs from its own folder on TACC). Append, so its
# module names (main, qwen_client, prompt_runner) can never shadow a backend module.
sys.path.append(str(CLIENT_DIR))

import prompt_runner  # noqa: E402
from stub_qwen import StubQwen  # noqa: E402


@pytest.fixture(autouse=True)
def bypass_proxy(monkeypatch):
    """Keep calls to the localhost stub away from any proxy on the developer's machine."""
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")


@pytest.fixture
def client_dir():
    return CLIENT_DIR


@pytest.fixture
def stub_qwen():
    stub = StubQwen()
    stub.start()
    yield stub
    stub.stop()


@pytest.fixture
def run_client(tmp_path, stub_qwen):
    """Write a prompt file, run the client against the stub, return the answers by id."""
    def run(prompts, **options):
        prompts_path = tmp_path / "prompts.json"
        prompts_path.write_text(json.dumps({"prompts": prompts}), encoding="utf-8")
        answers_path = tmp_path / "answers.json"
        prompt_runner.run(prompt_runner.load_prompts(prompts_path), answers_path,
                          stub_qwen.base_url, **options)
        return json.loads(answers_path.read_text(encoding="utf-8"))["answers"]
    return run
