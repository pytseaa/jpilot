from pydantic import BaseModel

from app.schemas.check import Claim


class Status(BaseModel):
    """Where a search is: searching, done or failed. None until the candidate presses Search."""
    stage: str | None


class ResultJob(BaseModel):
    """One job as the results list shows it."""
    job_id: str
    title: str | None
    employer: str | None
    location: str | None
    apply_link: str | None
    posted_date: str | None
    collected: str
    unverified: bool
    grade: int
    claims: list[Claim]


class Results(BaseModel):
    jobs: list[ResultJob]
    dropped_claims: int  # claims whose quote was not found, counted apart from the shown ones
