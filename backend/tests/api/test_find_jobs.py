import time
from contextlib import closing

import pytest
from fixture_jobs import fixture_jobs, make_job
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
    jobs = search(client, upload, employment_types=["full-time"])

    assert "h09" not in ids(jobs)  # full-time and matching, so only the region filter removes it


def test_a_job_with_an_unknown_region_or_type_is_kept_and_marked_unverified(client, upload):
    jobs = search(client, upload, employment_types=["full-time"])
    unverified = {job["job_id"] for job in jobs if job["unverified"]}

    assert unverified == {"h11", "h12", "h13"}  # unknown region, unknown type, both unknown
    assert "h01" in ids(jobs) - unverified  # a confirmed job carries no flag


def test_jobs_not_seen_in_the_last_30_days_are_never_returned(client, upload):
    jobs = search(client, upload, employment_types=["full-time"])

    assert {"h02", "h03"} <= ids(jobs)  # seen 29 and 30 days ago: still open
    assert not ids(jobs) & {"h04", "h05", "h15"}  # seen 31, 90 and 40 days ago: closed


def test_experience_band_and_industry_never_remove_a_job(client, upload):
    # h16 asks for 12 years and is in banking; the candidate picks 0-2 years and insurance.
    jobs = search(client, upload, employment_types=["full-time"], experience_band="0-2",
                  industry="Insurance")

    assert {"h16", "h17"} <= ids(jobs)


def test_matching_ignores_letter_case(client, upload):
    jobs = search(client, upload, keywords=["sql", "PYTHON"], employment_types=["full-time"])

    assert ids(jobs) == {"k-title", "k-desc", "k-lower"}


def test_a_keyword_matches_a_word_next_to_punctuation(client, upload):
    jobs = search(client, upload, keywords=["python"], employment_types=["full-time"])

    assert ids(jobs) == {"k-lower"}  # its text is "(python)"


def test_a_keyword_is_split_on_spaces_and_one_word_is_enough(client, upload):
    jobs = search(client, upload, keywords=["data analyst"], employment_types=["full-time"])

    assert {"h01", "k-title"} <= ids(jobs)  # h01 has only "analyst"; k-title has only "data"
    assert "k-stop" not in ids(jobs)  # neither word appears in it


def test_stop_words_and_it_never_qualify_a_job(client, upload):
    jobs = search(client, upload, keywords=["team", "IT", "SQL"], employment_types=["full-time"])

    assert "k-title" in ids(jobs)
    assert "k-stop" not in ids(jobs)  # its title says "Team" and its text says "it": neither counts


def test_a_match_in_the_title_scores_like_one_in_the_description_and_ties_go_by_job_id(client, upload):
    jobs = search(client, upload, keywords=["SQL"], employment_types=["full-time"])

    # k-title has "SQL" in its title and k-desc in its description. Both texts are five words with
    # one "sql", so the scores are equal and the job id decides the order.
    assert [job["job_id"] for job in jobs] == ["k-desc", "k-title"]


def test_keywords_that_are_all_stop_words_match_no_job(client, upload):
    jobs = search(client, upload, keywords=["the", "and"], employment_types=["full-time"])

    assert jobs == []


def test_a_search_of_an_empty_database_finishes_with_no_jobs(client, upload, tmp_path):
    with closing(db.connect(tmp_path)) as conn:
        conn.execute("DELETE FROM jobs")
        conn.commit()

    assert search(client, upload, employment_types=["full-time"]) == []


def test_at_most_20_jobs_come_back_best_first(client, upload, tmp_path):
    # Twenty-one jobs score alike. zz-sql says "SQL" twice in the same five words, so it scores higher.
    extra = [make_job(f"cap-{n:02}", types=["contractor"], title="Data developer",
                      description="SQL scripts weekly") for n in range(1, 22)]
    extra.append(make_job("zz-sql", types=["contractor"], title="Data developer",
                          description="SQL SQL weekly"))
    with closing(db.connect(tmp_path)) as conn:
        conn.executemany(INSERT, extra)
        conn.commit()

    jobs = search(client, upload, keywords=["SQL"], employment_types=["contractor"])

    assert [job["job_id"] for job in jobs] == ["zz-sql"] + [f"cap-{n:02}" for n in range(1, 20)]
