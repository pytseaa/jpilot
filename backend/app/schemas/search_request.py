from pydantic import BaseModel


class CvSummaryAnswer(BaseModel):
    """What the CV summary prompt must get back from Qwen."""
    summary: str
    keywords: list[str]


class Review(BaseModel):
    """What the review screen shows after the CV is read."""
    id: str
    summary: str
    keywords: list[str]
