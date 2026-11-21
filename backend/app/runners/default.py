import os

from app.runners.fake import FakeRunner
from app.runners.tacc import TaccRunner


def default_runner():
    # Set JPILOT_RUNNER=tacc to submit to TACC. Anything else is refused, so a typo cannot
    # quietly run the canned answers while the user believes they are on TACC.
    setting = os.environ.get("JPILOT_RUNNER", "tacc")
    if setting == "fake":
        return FakeRunner(retain_prompts=False)
    if setting == "tacc":
        return TaccRunner()
    raise ValueError(f"JPILOT_RUNNER must be 'fake' or 'tacc', not {setting!r}")
