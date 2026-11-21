from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class SearchRequest:
    """One in-memory request. CV and review fields are cleared before its terminal status."""
    id: str
    cv_text: str
    summary: str
    keywords: list[str]
    target_role: str
    employment_types: Sequence[str]
    experience_band: str | None
    industry: str | None
    # searching, refining round 1 or 2, checking jobs, done or failed; None until Search is pressed
    stage: str | None = None
    jobs: list[dict] = field(default_factory=list)  # the shortlist with its verified claims, once done
    dropped_claims: int = 0
    skipped_jobs: int = 0
    explanation: str | None = None
    error: str | None = None
    trace: object = None

    def forget_cv(self):
        self.cv_text = ""
        self.summary = ""
        self.keywords = []
        self.target_role = ""
