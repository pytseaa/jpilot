from fastapi.testclient import TestClient
from pdfs import blank_pdf, text_pdf

from app.main import create_app


def test_a_pdf_with_no_selectable_text_is_rejected_before_any_qwen_call(upload, runner):
    response = upload(blank_pdf())

    assert response.status_code == 422
    assert "text-based PDF" in response.json()["detail"]
    assert runner.submissions == []


def test_a_file_that_is_not_a_pdf_is_rejected_before_any_qwen_call(upload, runner):
    response = upload(b"just some words, not a PDF")

    assert response.status_code == 422
    assert "text-based PDF" in response.json()["detail"]
    assert runner.submissions == []


def test_a_text_cv_returns_the_runner_summary_and_keywords_in_one_submission(upload, runner):
    response = upload(text_pdf("Analyst at a retail bank"))

    assert response.status_code == 200
    body = response.json()
    assert body["id"]
    assert body["summary"] == "Analyst with five years in retail banking."
    assert body["keywords"] == ["SQL", "Python", "reporting"]
    [[prompt]] = runner.submissions
    assert prompt["id"] == "cv-summary"
    assert "Analyst at a retail bank" in prompt["prompt"]


def test_a_failed_summary_call_gives_an_error_and_no_request(tmp_path):
    def failing_runner(prompts):
        return {"cv-summary": {"status": "failed", "error_type": "timeout"}}

    with TestClient(create_app(runner=failing_runner, data_dir=tmp_path)) as client:
        response = client.post(
            "/api/search-requests", data={"employment_types": "full-time"},
            files={"cv": ("cv.pdf", text_pdf("Analyst at a retail bank"), "application/pdf")})

    assert response.status_code == 502
    assert "CV summary" in response.json()["detail"]
