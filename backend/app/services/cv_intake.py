"""CV intake: read the PDF text, then ask Qwen (through the runner) for the CV summary."""
import io

from pydantic import ValidationError
from pypdf import PdfReader

from app import prompts
from app.schemas.search_request import CvSummaryAnswer

SUMMARY_ID = "cv-summary"
REQUIRED_KEYS = ["summary", "keywords"]
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


def summarise(cv_text, runner):
    """One runner submission holding the CV summary prompt."""
    prompt = {"id": SUMMARY_ID, "prompt": prompts.CV_SUMMARY.format(cv_text=cv_text),
              "required_keys": REQUIRED_KEYS}
    record = runner([prompt])[SUMMARY_ID]
    try:
        if record["status"] != "ok":
            raise SummaryFailed(record["error_type"])
        return CvSummaryAnswer.model_validate(record["answer"])
    except ValidationError as exc:
        raise SummaryFailed("invalid answer") from exc
