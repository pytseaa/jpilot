from dataclasses import dataclass


@dataclass
class SearchRequest:
    """One candidate's request. Held in memory only: the CV text never reaches a file."""
    id: str
    cv_text: str
    summary: str
    keywords: list[str]
    target_role: str
