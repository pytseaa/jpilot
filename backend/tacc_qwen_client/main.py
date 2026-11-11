"""Answer every prompt in prompts.json with Qwen and write one answer file."""
import os
from pathlib import Path

from prompt_runner import load_prompts, run
from qwen_client import normalize_base_url


def main():
    base_url = normalize_base_url(os.environ["QWEN_BASE_URL"])
    prompts = load_prompts(Path(os.environ["TACC_WORKDIR"]) / "prompts.json")

    relative = Path("jpilot-tacc-client") / f"job-{os.environ['SLURM_JOB_ID']}.json"
    destination = Path(os.environ["TACC_USERDIR"]) / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(prompts, destination, base_url)
    print("RESULT_FILE=" + relative.as_posix())


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        raise SystemExit(f"Error: {exc}")
