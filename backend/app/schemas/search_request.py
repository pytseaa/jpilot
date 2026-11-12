from pydantic import BaseModel


class CvSummaryAnswer(BaseModel):
    """What the CV summary prompt must get back from Qwen. target_role only when it was asked for."""
    summary: str
    keywords: list[str]
    target_role: str = ""


class Review(BaseModel):
    """What the review screen shows after the CV is read."""
    id: str
    summary: str
    keywords: list[str]
    target_role: str
