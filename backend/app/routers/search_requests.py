from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile

from app.models.search_request import SearchRequest
from app.runners.tacc import SubmissionFailed
from app.schemas.search_request import (
    BlankIsNone, EmploymentType, ExperienceBand, Industry, Review, Reviewed)
from app.services import cv_intake

router = APIRouter(prefix="/api/search-requests")


def _review(stored):
    return Review.model_validate(vars(stored))  # cv_text is not a Review field, so it is left out


@router.post("")
def create(
    request: Request,
    cv: UploadFile,
    employment_types: Annotated[list[EmploymentType], Form(min_length=1)],
    experience_band: Annotated[ExperienceBand | None, BlankIsNone, Form()] = None,
    industry: Annotated[Industry | None, BlankIsNone, Form()] = None,
    target_role: Annotated[str, Form()] = "",
) -> Review:
    """Read the CV and return its summary for the review screen."""
    target_role = target_role.strip()
    try:
        cv_text = cv_intake.extract_text(cv.file.read())
    except cv_intake.CvRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        answer = cv_intake.summarise(cv_text, request.app.state.runner, not target_role)
    except cv_intake.SummaryFailed as exc:
        raise HTTPException(502, "The CV summary could not be made. Please try again.") from exc
    except SubmissionFailed as exc:
        raise HTTPException(502, str(exc)) from exc
    stored = SearchRequest(uuid4().hex, cv_text, answer.summary, answer.keywords,
                           target_role or answer.target_role.strip(),
                           employment_types, experience_band, industry)
    request.app.state.requests[stored.id] = stored
    return _review(stored)


@router.post("/{request_id}/search")
def search(request: Request, request_id: str, reviewed: Reviewed) -> Review:
    """Keep the reviewed values. Nothing is searched yet, and Qwen is not called again."""
    stored = request.app.state.requests.get(request_id)
    if stored is None:
        raise HTTPException(404, "This request was not found. Please upload your CV again.")
    vars(stored).update(reviewed.model_dump())
    return _review(stored)
