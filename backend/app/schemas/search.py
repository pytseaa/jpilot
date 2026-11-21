from typing import Literal

from pydantic import BaseModel

from app.schemas.check import Claim


class Status(BaseModel):
    """Where a search is: searching, refining round 1 or 2, checking jobs, done or failed. None until the candidate presses Search."""
    stage: str | None
    error: str | None = None


class LearningLink(BaseModel):
    """One curated learning link the team has checked by hand. The URL never comes from Qwen."""
    id: str
    title: str
    url: str


class SkillGap(BaseModel):
    """A job requirement the CV does not meet, with any learning links that fit it."""
    requirement: str
    learning_links: list[LearningLink]


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
    grade: Literal[1, 2]
    claims: list[Claim]
    skill_gaps: list[SkillGap] = []


class Results(BaseModel):
    jobs: list[ResultJob]
    dropped_claims: int  # claims whose quote was not found, counted apart from the shown ones
    skipped_jobs: int = 0
    explanation: str | None = None
