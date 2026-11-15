"""What the check prompt must get back from Qwen for one job."""
from typing import Any, Literal

from pydantic import BaseModel


class Claim(BaseModel):
    """A reason the CV fits the job. It is shown only once both quotes are found in their source."""
    requirement: str
    cv_quote: str
    job_quote: str


class CheckAnswer(BaseModel):
    grade: Literal[0, 1, 2]
    # Each claim is checked on its own, so one bad claim does not fail the whole answer.
    claims: list[Any]
