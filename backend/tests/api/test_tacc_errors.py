from fastapi.testclient import TestClient
from pdfs import text_pdf

from app.main import create_app
from app.runners.tacc import SubmissionFailed

CV = text_pdf("Analyst at a retail bank")


def test_a_failed_tacc_submission_is_a_502_that_asks_for_a_service_restart(tmp_path):
    def unreachable(prompts):
        raise SubmissionFailed("restart")

    with TestClient(create_app(runner=unreachable, data_dir=tmp_path)) as client:
        response = client.post("/api/search-requests", data={"employment_types": ["full-time"]},
                               files={"cv": ("cv.pdf", CV, "application/pdf")})

    assert response.status_code == 502
    assert "restart" in response.json()["detail"]
