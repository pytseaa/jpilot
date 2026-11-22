"""What the check prompt must get back from Qwen for one job."""
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints


class Claim(BaseModel):
    """A reason the CV fits the job. It is shown only once both quotes are found in their source."""
    requirement: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    cv_quote: str
    job_quote: str


class UnmetRequirement(BaseModel):
    """A job requirement the CV does not meet. Shown as a skill gap with any learning links that fit."""
    requirement: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    # Each id is checked on its own against the curated list, so one bad id does not drop the whole requirement.
    link_ids: list[Any] = []


class CheckAnswer(BaseModel):
    grade: Annotated[int, Field(strict=True, ge=0, le=2)]  # strict: JSON true or 1.0 is not a grade
    # Each claim is checked on its own, so one bad claim does not fail the whole answer.
    claims: list[Any]
    # Default empty so an answer from before this field existed still parses.
    unmet_requirements: list[Any] = []
