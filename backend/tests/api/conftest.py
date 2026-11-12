import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.runners.fake import FakeRunner


@pytest.fixture
def runner():
    return FakeRunner({"cv-summary": {
        "summary": "Analyst with five years in retail banking.",
        "keywords": ["SQL", "Python", "reporting"],
    }})


@pytest.fixture
def client(runner, tmp_path):
    with TestClient(create_app(runner=runner, data_dir=tmp_path)) as client:
        yield client


@pytest.fixture
def upload(client):
    """Send a CV to the app the way the browser does."""
    def send(content):
        return client.post("/api/search-requests",
                           files={"cv": ("cv.pdf", content, "application/pdf")})
    return send
