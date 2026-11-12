"""CV intake: read the PDF text, then ask Qwen (through the runner) for the CV summary."""
import io

from pydantic import ValidationError
from pypdf import PdfReader

from app import prompts
from app.schemas.search_request import CvSummaryAnswer

SUMMARY_ID = "cv-summary"
NO_TEXT_MESSAGE = ("We could not read any text from this file. "
                   "Please upload a text-based PDF, not a scan or an image.")


class CvRejected(Exception):
    """The upload cannot be used. The message is for the candidate."""


class SummaryFailed(Exception):
    """Qwen gave no usable CV summary."""


def extract_text(data):
    """Return the selectable text of a PDF, or raise CvRejected before any Qwen call."""
    try:
        text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)
    except Exception as exc:  # pypdf raises many different errors on damaged or odd files
        raise CvRejected(NO_TEXT_MESSAGE) from exc
    if not text.strip():
        raise CvRejected(NO_TEXT_MESSAGE)
    return text


def summarise(cv_text, runner, propose_target_role):
    """One runner submission holding the CV summary prompt.

    Qwen is asked for a target role only when propose_target_role is true."""
    required_keys = ["summary", "keywords"] + (["target_role"] if propose_target_role else [])
    target_role_key = prompts.TARGET_ROLE_KEY if propose_target_role else ""
    prompt = {"id": SUMMARY_ID, "required_keys": required_keys,
              "prompt": prompts.CV_SUMMARY.format(cv_text=cv_text, target_role_key=target_role_key)}
    record = runner([prompt])[SUMMARY_ID]
    try:
        if record["status"] != "ok":
            raise SummaryFailed(record["error_type"])
        return CvSummaryAnswer.model_validate(record["answer"])
    except ValidationError as exc:
        raise SummaryFailed("invalid answer") from exc
