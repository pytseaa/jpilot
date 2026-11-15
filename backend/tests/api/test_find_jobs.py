import threading
import time
from contextlib import closing

import pytest
from fixture_jobs import fixture_jobs, make_job
from pdfs import text_pdf

from app import db
from app.services import retrieval
from app.services.ingestion import INSERT

CV = text_pdf("Analyst at a retail bank")


@pytest.fixture(autouse=True)
def job_database(tmp_path, client):
    """Fill the job database the app reads. The app is started first, so its tables exist."""
    with closing(db.connect(tmp_path)) as conn:
        conn.executemany(INSERT, fixture_jobs())
        conn.commit()


@pytest.fixture
def held(monkeypatch):
    """Hold every search open, around the real search step, until the test sets the event."""
    release = threading.Event()
    real = retrieval.find_qualifying

    def wait_then_search(*args):
        release.wait(5)
        return real(*args)

    monkeypatch.setattr(retrieval, "find_qualifying", wait_then_search)
    yield release
    release.set()


def start(client, upload, **edits):
    """Upload a CV and press Search with the review edited as given. Return the request's URL and the body sent."""
    review = upload(CV).json()
    base = f"/api/search-requests/{review['id']}"
    body = {**review, **edits}
    assert client.post(f"{base}/search", json=body).status_code == 200
    return base, body


def wait_until_finished(client, base):
    """Poll the status until the search leaves "searching". Return the status."""
    deadline = time.monotonic() + 5
    while client.get(f"{base}/status").json()["stage"] == "searching" and time.monotonic() < deadline:
        time.sleep(0.01)
    return client.get(f"{base}/status").json()


def search(client, upload, **edits):
    """Press Search on a fresh upload with the review edited as given. Return the result jobs."""
    base, _ = start(client, upload, **edits)
    assert wait_until_finished(client, base) == {"stage": "done"}
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


def test_a_keyword_matches_a_word_in_curly_quotes(client, upload, tmp_path):
    store(tmp_path, [make_job("q1", title="Lead", description="“Tableau” ‘Excel’ wanted")])

    jobs = search(client, upload, keywords=["excel", "tableau"], employment_types=["full-time"])

    assert ids(jobs) == {"q1"}


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


def test_a_second_start_while_a_search_runs_is_refused(client, upload, held):
    base, body = start(client, upload, keywords=["SQL"], employment_types=["full-time"])
    assert client.get(f"{base}/status").json() == {"stage": "searching"}

    second = client.post(f"{base}/search", json=body)

    assert second.status_code == 409
    held.set()
    assert wait_until_finished(client, base) == {"stage": "done"}  # the first search was not disturbed
    assert ids(client.get(f"{base}/results").json()["jobs"]) == {"k-title", "k-desc"}


def test_a_search_for_another_request_is_refused_while_one_runs(client, upload, held):
    base, _ = start(client, upload, employment_types=["full-time"])
    other = upload(CV).json()  # a second session in the sidebar, with its own CV
    other_url = f"/api/search-requests/{other['id']}/search"

    assert client.post(other_url, json=other).status_code == 409
    held.set()
    assert wait_until_finished(client, base) == {"stage": "done"}
    assert client.post(other_url, json=other).status_code == 200  # free again once the first is done


class SlowToRead:
    """A stored request whose stage takes a moment to read, as when another thread gets the CPU."""
    def __init__(self):
        self.reading = threading.Event()

    @property
    def stage(self):
        self.reading.set()
        time.sleep(0.3)  # long enough for an upload to add a request
        return None


def test_an_upload_while_a_start_checks_the_other_sessions_is_not_lost_or_broken(client, upload):
    first = upload(CV).json()
    slow = client.app.state.requests["slow"] = SlowToRead()
    answers = []
    start_search = threading.Thread(target=lambda: answers.append(
        client.post(f"/api/search-requests/{first['id']}/search", json=first)))
    start_search.start()
    assert slow.reading.wait(5)  # the start is part-way through checking the sessions

    second = upload(CV)  # arrives in the middle of it
    start_search.join(5)

    assert [answer.status_code for answer in answers] == [200]
    assert second.status_code == 200
    assert second.json()["id"] in client.app.state.requests


def test_a_search_that_fails_ends_as_failed_and_gives_no_list(client, upload, monkeypatch):
    def broken(*args):
        raise RuntimeError("the job database cannot be read")

    monkeypatch.setattr(retrieval, "find_qualifying", broken)
    base, _ = start(client, upload, employment_types=["full-time"])

    assert wait_until_finished(client, base) == {"stage": "failed"}
    assert client.get(f"{base}/results").status_code == 409


def test_after_a_failed_search_the_candidate_can_search_again(client, upload, monkeypatch):
    with monkeypatch.context() as broken:
        broken.setattr(retrieval, "find_qualifying", lambda *args: 1 / 0)
        base, body = start(client, upload, keywords=["SQL"], employment_types=["full-time"])
        assert wait_until_finished(client, base) == {"stage": "failed"}

    assert client.post(f"{base}/search", json=body).status_code == 200
    assert wait_until_finished(client, base) == {"stage": "done"}
    assert ids(client.get(f"{base}/results").json()["jobs"]) == {"k-title", "k-desc"}


def test_results_are_refused_until_the_search_is_done(client, upload, held):
    base, _ = start(client, upload, employment_types=["full-time"])

    assert client.get(f"{base}/results").status_code == 409  # still searching


def test_keywords_that_are_all_stop_words_match_no_job(client, upload):
    jobs = search(client, upload, keywords=["the", "and"], employment_types=["full-time"])

    assert jobs == []


def test_a_search_of_an_empty_database_finishes_with_no_jobs(client, upload, tmp_path):
    with closing(db.connect(tmp_path)) as conn:
        conn.execute("DELETE FROM jobs")
        conn.commit()

    assert search(client, upload, employment_types=["full-time"]) == []


def store(tmp_path, jobs):
    """Add jobs to the database the app reads."""
    with closing(db.connect(tmp_path)) as conn:
        conn.executemany(INSERT, jobs)
        conn.commit()


def test_a_database_whose_jobs_have_no_words_left_finishes_with_no_jobs(client, upload, tmp_path):
    with closing(db.connect(tmp_path)) as conn:
        conn.execute("DELETE FROM jobs")
        conn.commit()
    store(tmp_path, [make_job("e1", title="The", description="and of"),
                     make_job("e2", title="", description="")])  # only stop words, or nothing at all

    assert search(client, upload, keywords=["SQL"], employment_types=["full-time"]) == []


def test_at_most_20_jobs_come_back_best_first(client, upload, tmp_path):
    # Twenty-one jobs score alike. zz-sql says "SQL" twice in the same five words, so it scores higher.
    extra = [make_job(f"cap-{n:02}", types=["contractor"], title="Data developer",
                      description="SQL scripts weekly") for n in range(1, 22)]
    extra.append(make_job("zz-sql", types=["contractor"], title="Data developer",
                          description="SQL SQL weekly"))
    store(tmp_path, extra)

    jobs = search(client, upload, keywords=["SQL"], employment_types=["contractor"])

    assert [job["job_id"] for job in jobs] == ["zz-sql"] + [f"cap-{n:02}" for n in range(1, 20)]
