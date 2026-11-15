from pydantic import BaseModel


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


class Results(BaseModel):
    jobs: list[ResultJob]
