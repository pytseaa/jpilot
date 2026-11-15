from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class SearchRequest:
    """One candidate's request. Held in memory only: the CV text never reaches a file."""
    id: str
    cv_text: str
    summary: str
    keywords: list[str]
    target_role: str
    employment_types: Sequence[str]
    experience_band: str | None
    industry: str | None
    stage: str | None = None  # searching, done or failed; None until Search is pressed
    jobs: list[dict] = field(default_factory=list)  # the checked jobs with their verified claims, once done
    dropped_claims: int = 0
