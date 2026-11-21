import logging
from contextlib import closing
from threading import Lock, Thread
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Form, HTTPException, Request, Response, UploadFile

from app import db
from app.models.search_request import SearchRequest
from app.runners.tacc import SERVICE_MESSAGE, SubmissionFailed
from app.trace import RequestTrace
from app.schemas.search import Results, Status
from app.schemas.search_request import (
    BlankIsNone, EmploymentType, ExperienceBand, Industry, Review, Reviewed)
from app.services import checking, cv_intake, explanations, refinement, retrieval

router = APIRouter(prefix="/api/search-requests")
logger = logging.getLogger(__name__)
_start_lock = Lock()


def _review(stored):
    return Review.model_validate(vars(stored))  # cv_text is not a Review field, so it is left out


@router.post("")
def create(
    request: Request,
    response: Response,
    cv: UploadFile,
    employment_types: Annotated[list[EmploymentType], Form(min_length=1)],
    experience_band: Annotated[ExperienceBand | None, BlankIsNone, Form()] = None,
    industry: Annotated[Industry | None, BlankIsNone, Form()] = None,
    target_role: Annotated[str, Form()] = "",
) -> Review:
    """Read the CV and return its summary for the review screen."""
    request_id = uuid4().hex
    trace = RequestTrace(request.app.state.data_dir, request_id)
    headers = {"X-Request-ID": request_id}
    response.headers.update(headers)
    target_role = target_role.strip()
    try:
        cv_text = cv_intake.extract_text(cv.file.read())
        answer = cv_intake.summarise(cv_text, trace.runner(request.app.state.runner), not target_role)
    except cv_intake.CvRejected as exc:
        trace.finish("failed", "invalid_answer")
        raise HTTPException(422, str(exc), headers=headers) from None
    except cv_intake.SummaryFailed:
        trace.finish("failed", "invalid_answer")
        raise HTTPException(502, "The CV could not be matched because no usable CV summary was returned. "
                            "Please upload your CV again to retry.", headers=headers) from None
    except SubmissionFailed as exc:
        trace.finish("failed", "submission_failed")
        raise HTTPException(502, str(exc), headers=headers) from None
    except Exception:
        trace.finish("failed", "client_error")
        raise HTTPException(502, "The CV could not be read. Please upload your CV again.", headers=headers) from None
    finally:
        cv.file.close()
    stored = SearchRequest(request_id, cv_text, answer.summary, answer.keywords,
                           target_role or answer.target_role.strip(),
                           employment_types, experience_band, industry)
    stored.trace = trace
    trace.review()
    request.app.state.requests[stored.id] = stored
    return _review(stored)


def _stored(request, request_id):
    stored = request.app.state.requests.get(request_id)
    if stored is None:
        raise HTTPException(404, "This request was not found. Please upload your CV again.")
    return stored


def _run_search(data_dir, runner, stored):
    try:
        runner = stored.trace.runner(runner)
        with closing(db.connect(data_dir)) as conn:  # a connection belongs to the thread that opened it
            passing = retrieval.count_passing(conn, stored.employment_types)
            def on_round(round_number):
                stored.trace.stage(f"refining round {round_number}")
                stored.stage = f"refining round {round_number}"
            qualifying = refinement.widen(
                conn, stored.keywords, stored.summary, stored.target_role, stored.employment_types, runner,
                on_round)
        stored.trace.stage("checking jobs")
        stored.stage = "checking jobs"
        stored.jobs, stored.dropped_claims, stored.skipped_jobs = checking.check_jobs(
            qualifying, stored.cv_text, stored.summary, runner, stored.experience_band, stored.industry, stored.trace)
        stored.explanation = explanations.short_results(stored.jobs, passing, len(qualifying), stored.skipped_jobs)
        stored.forget_cv()
        stored.trace.finish("done")
        stored.stage = "done"
    except Exception as exc:  # never log exception text: a library error may include prompt or answer text
        failure = "submission_failed" if isinstance(exc, SubmissionFailed) else "client_error"
        stored.jobs = []
        stored.forget_cv()
        stored.error = ((SERVICE_MESSAGE if str(exc) == SERVICE_MESSAGE else "The TACC submission failed. No partial results are shown.")
                        if isinstance(exc, SubmissionFailed) else "The search failed. No partial results are shown.")
        stored.error += " Your CV has been deleted. Please upload it again to retry."
        logger.error("Request %s failed (%s)", stored.id, failure)
        try:
            stored.trace.finish("failed", failure)
        finally:
            stored.stage = "failed"


@router.post("/{request_id}/search")
def search(request: Request, request_id: str, reviewed: Reviewed) -> Review:
    """Keep the reviewed values and start the search in the background."""
    stored = _stored(request, request_id)
    with _start_lock:  # two starts at the same moment must not both pass the check
        if stored.stage in ("done", "failed"):
            raise HTTPException(410, "Your CV has been deleted. Please upload it again to start a new search.")
        # One search at a time for the whole backend; list() copies, as an upload may add a request.
        if any(other.stage not in (None, "done", "failed") for other in list(request.app.state.requests.values())):
            raise HTTPException(409, "A search is already running.")
        stored.stage = "searching"
        vars(stored).update(reviewed.model_dump())
        review = _review(stored)  # snapshot before the worker can delete the CV summary
        stored.trace.stage("searching")
        Thread(target=_run_search, args=(request.app.state.data_dir, request.app.state.runner, stored),
               daemon=True).start()
    return review


@router.get("/{request_id}/status", response_model_exclude_none=True)
def status(request: Request, request_id: str) -> Status:
    stored = _stored(request, request_id)
    return Status(stage=stored.stage, error=stored.error)


@router.get("/{request_id}/results")
def results(request: Request, request_id: str) -> Results:
    stored = _stored(request, request_id)
    if stored.stage != "done":  # a search that is running or failed has no list to show
        raise HTTPException(409, "The search is not finished.")
    return Results.model_validate({"jobs": stored.jobs, "dropped_claims": stored.dropped_claims,
                                   "skipped_jobs": stored.skipped_jobs, "explanation": stored.explanation})
