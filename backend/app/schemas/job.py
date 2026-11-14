"""What the job extraction prompt must get back from Qwen. Checked before anything is stored."""
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.schemas.search_request import EmploymentType, Industry


class JobExtractionAnswer(BaseModel):
    region: Literal["Hong Kong", "other", "unknown"]
    employment_types: list[EmploymentType]  # empty means unknown
    minimum_years: Annotated[int, Field(ge=0)] | None  # None means the job says nothing
    industry: Industry | Literal["unknown"]
    requirements: list[str]
