from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field

EmploymentType = Literal["full-time", "part-time", "contractor"]
ExperienceBand = Literal["0-2", "3-5", "6-9", "10+"]
Industry = Literal[
    "Banking and finance", "Insurance", "Professional services (accounting, legal, consulting)",
    "Information technology and telecoms", "Media, advertising and marketing",
    "Retail and e-commerce", "Hospitality, food and tourism", "Logistics and transport",
    "Manufacturing and engineering", "Construction and property",
    "Healthcare and pharmaceuticals", "Education and training",
    "Government and public sector", "Non-profit and social services", "Energy and utilities",
    "other",
]
# A browser sends "" for a select left on its blank option, and the form may leave it blank.
BlankIsNone = BeforeValidator(lambda value: value or None)


class CvSummaryAnswer(BaseModel):
    """What the CV summary prompt must get back from Qwen. target_role only when it was asked for."""
    summary: str
    keywords: list[str]
    target_role: str = ""


class Reviewed(BaseModel):
    """The values the candidate reviews and may edit, and the Search endpoint keeps."""
    summary: str
    keywords: list[str]
    target_role: str
    employment_types: Annotated[list[EmploymentType], Field(min_length=1)]
    experience_band: Annotated[ExperienceBand | None, BlankIsNone] = None
    industry: Annotated[Industry | None, BlankIsNone] = None


class Review(Reviewed):
    """What the review screen shows after the CV is read."""
    id: str
