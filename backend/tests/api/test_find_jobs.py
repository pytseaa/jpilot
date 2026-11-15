import time
from contextlib import closing

import pytest
from fixture_jobs import fixture_jobs
from pdfs import text_pdf

from app import db
from app.services.ingestion import INSERT

CV = text_pdf("Analyst at a retail bank")


@pytest.fixture(autouse=True)
def job_database(tmp_path, client):
    """Fill the job database the app reads. The app is started first, so its tables exist."""
    with closing(db.connect(tmp_path)) as conn:
        conn.executemany(INSERT, fixture_jobs())
        conn.commit()


def search(client, upload, **edits):
    """Press Search on a fresh upload with the review edited as given. Return the result jobs."""
    review = upload(CV).json()
    base = f"/api/search-requests/{review['id']}"
    client.post(f"{base}/search", json={**review, **edits})
    deadline = time.monotonic() + 5
    while client.get(f"{base}/status").json()["stage"] == "searching" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert client.get(f"{base}/status").json() == {"stage": "done"}
    return client.get(f"{base}/results").json()["jobs"]


def ids(jobs):
    return {job["job_id"] for job in jobs}


def test_a_finished_search_lists_a_confirmed_hong_kong_job(client, upload):
    jobs = search(client, upload, employment_types=["full-time"])

    assert "h01" in ids(jobs)


def test_a_job_passes_the_employment_type_filter_if_it_has_any_picked_type(client, upload):
    jobs = search(client, upload, employment_types=["contractor", "part-time"])

    assert ids(jobs) >= {"h06", "h07", "h08"}  # part-time, contractor, and full-time plus contractor
    assert not ids(jobs) & {"h01", "h02", "h03", "h16", "h17"}  # full-time only


def test_jobs_outside_hong_kong_are_removed(client, upload):
    jobs = search(client, upload, employment_types=["full-time", "part-time", "contractor"])

    assert not ids(jobs) & {"h09", "h10"}  # region "other"


def test_a_job_with_an_unknown_region_or_type_is_kept_and_marked_unverified(client, upload):
    jobs = search(client, upload, employment_types=["full-time"])
    unverified = {job["job_id"] for job in jobs if job["unverified"]}

    assert unverified == {"h11", "h12", "h13"}  # unknown region, unknown type, both unknown
    assert "h01" in ids(jobs) - unverified  # a confirmed job carries no flag


def test_experience_band_and_industry_never_remove_a_job(client, upload):
    # h16 asks for 12 years and is in banking; the candidate picks 0-2 years and insurance.
    jobs = search(client, upload, employment_types=["full-time"], experience_band="0-2",
                  industry="Insurance")

    assert {"h16", "h17"} <= ids(jobs)


def test_jobs_not_seen_in_the_last_30_days_are_never_returned(client, upload):
    jobs = search(client, upload, employment_types=["full-time"])

    assert {"h02", "h03"} <= ids(jobs)  # seen 29 and 30 days ago: still open
    assert not ids(jobs) & {"h04", "h05", "h15"}  # seen 31, 90 and 40 days ago: closed
