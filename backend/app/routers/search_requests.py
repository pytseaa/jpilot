from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, UploadFile

from app.models.search_request import SearchRequest
from app.schemas.search_request import Review
from app.services import cv_intake

router = APIRouter(prefix="/api/search-requests")


@router.post("")
def create(request: Request, cv: UploadFile) -> Review:
    """Read the CV and return its summary for the review screen."""
    try:
        cv_text = cv_intake.extract_text(cv.file.read())
    except cv_intake.CvRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        answer = cv_intake.summarise(cv_text, request.app.state.runner)
    except cv_intake.SummaryFailed as exc:
        raise HTTPException(502, "The CV summary could not be made. Please try again.") from exc
    stored = SearchRequest(uuid4().hex, cv_text, answer.summary, answer.keywords)
    request.app.state.requests[stored.id] = stored
    return Review(id=stored.id, summary=stored.summary, keywords=stored.keywords)
