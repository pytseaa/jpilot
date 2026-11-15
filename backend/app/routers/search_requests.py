import logging
from contextlib import closing
from threading import Lock, Thread
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile

from app import db
from app.models.search_request import SearchRequest
from app.runners.tacc import SubmissionFailed
from app.schemas.search import Results, Status
from app.schemas.search_request import (
    BlankIsNone, EmploymentType, ExperienceBand, Industry, Review, Reviewed)
from app.services import checking, cv_intake, retrieval

router = APIRouter(prefix="/api/search-requests")
logger = logging.getLogger(__name__)
_start_lock = Lock()


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


def _stored(request, request_id):
    stored = request.app.state.requests.get(request_id)
    if stored is None:
        raise HTTPException(404, "This request was not found. Please upload your CV again.")
    return stored


def _run_search(data_dir, runner, stored):
    # shortcut: only a raised error ends a search, so one that hangs blocks every session until restart, add a timeout once a search can wait on Qwen.
    try:
        with closing(db.connect(data_dir)) as conn:  # a connection belongs to the thread that opened it
            qualifying = retrieval.find_qualifying(conn, stored.keywords, stored.employment_types)
        stored.jobs, stored.dropped_claims = checking.check_jobs(
            qualifying, stored.cv_text, stored.summary, runner)
        stored.stage = "done"
    except Exception:  # whatever went wrong, the candidate must see "failed", not a search that never ends
        logger.exception("The search for request %s failed", stored.id)
        stored.stage = "failed"


@router.post("/{request_id}/search")
def search(request: Request, request_id: str, reviewed: Reviewed) -> Review:
    """Keep the reviewed values and start the search in the background."""
    stored = _stored(request, request_id)
    with _start_lock:  # two starts at the same moment must not both pass the check
        # One search at a time for the whole backend; list() copies, as an upload may add a request.
        if any(other.stage == "searching" for other in list(request.app.state.requests.values())):
            raise HTTPException(409, "A search is already running.")
        stored.stage = "searching"
    vars(stored).update(reviewed.model_dump())
    Thread(target=_run_search, args=(request.app.state.data_dir, request.app.state.runner, stored),
           daemon=True).start()
    return _review(stored)


@router.get("/{request_id}/status")
def status(request: Request, request_id: str) -> Status:
    return Status(stage=_stored(request, request_id).stage)


@router.get("/{request_id}/results")
def results(request: Request, request_id: str) -> Results:
    stored = _stored(request, request_id)
    if stored.stage != "done":  # a search that is running or failed has no list to show
        raise HTTPException(409, "The search is not finished.")
    return Results.model_validate({"jobs": stored.jobs, "dropped_claims": stored.dropped_claims})
