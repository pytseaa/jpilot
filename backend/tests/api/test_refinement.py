import threading
from contextlib import closing

import pytest
from fixture_jobs import make_job
from pdfs import text_pdf
from searches import wait_until_finished

from app import db
from app.runners.fake import FakeRunner
from app.services.ingestion import INSERT

CV = text_pdf("Built Tableau dashboards for a retail bank")


@pytest.fixture
def store(tmp_path, client):
    """Add jobs to the database the app reads, which holds nothing else. The app is started first, so its tables exist."""
    def put(*jobs):
        with closing(db.connect(tmp_path)) as conn:
            conn.executemany(INSERT, jobs)
            conn.commit()
    return put


@pytest.fixture
def hold(monkeypatch, request):
    """Hold the submission whose first prompt id starts with `prefix` until the test releases it."""
    def hold_at(prefix):
        arrived, release = threading.Event(), threading.Event()
        request.addfinalizer(release.set)
        real = FakeRunner.__call__

        def call(self, prompts):
            if prompts[0]["id"].startswith(prefix):
                arrived.set()
                release.wait(5)
            return real(self, prompts)

        monkeypatch.setattr(FakeRunner, "__call__", call)
        return arrived, release
    return hold_at


def start(client, upload, **edits):
    """Upload a CV and press Search for "tableau". Return the request's URL."""
    review = upload(CV).json()
    base = f"/api/search-requests/{review['id']}"
    assert client.post(f"{base}/search", json={**review, "keywords": ["tableau"], **edits}).status_code == 200
    return base


def shown(client, upload, **edits):
    """Search to the end and return the ids of the jobs shown."""
    base = start(client, upload, **edits)
    assert wait_until_finished(client, base) == {"stage": "done"}
    return {job["job_id"] for job in client.get(f"{base}/results").json()["jobs"]}


def submitted(runner):
    """The id of the first prompt of each submission, in order."""
    return [prompts[0]["id"] for prompts in runner.submissions]


def test_a_refinement_round_adds_keywords_and_the_search_runs_again(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting"), make_job("t2", description="Looker dashboards"))
    runner.answers["refine-1"] = {"keywords": ["looker"]}

    assert shown(client, upload) == {"t1", "t2"}  # t2 only matches the new keyword, t1 the candidate's own
    assert submitted(runner) == ["cv-summary", "refine-1", "check-0"]  # the round is its own submission


def test_the_refinement_prompt_carries_the_summary_the_target_role_and_the_keywords_but_no_cv_text(
        client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting"), make_job("t2", description="Looker dashboards"))
    runner.answers["refine-1"] = {"keywords": []}

    shown(client, upload, keywords=["tableau", "reporting"], summary="Expert in Looker.", target_role="BI developer")

    [prompt] = [s[0]["prompt"] for s in runner.submissions if s[0]["id"] == "refine-1"]
    assert all(text in prompt for text in ("Expert in Looker.", "BI developer", "tableau", "reporting"))
    assert "retail bank" not in prompt  # the CV text never reaches this prompt


def test_refinement_is_skipped_when_every_job_passing_the_hard_filters_already_qualifies(
        client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting"),
          make_job("x1", region="other", description="Looker dashboards"),
          make_job("x2", types=["part-time"], description="Looker dashboards"),
          make_job("x3", age=40, description="Looker dashboards"))  # all three fail a hard filter

    assert shown(client, upload) == {"t1"}
    assert submitted(runner) == ["cv-summary", "check-0"]


def test_refinement_is_skipped_when_20_jobs_already_qualify(client, upload, runner, store):
    store(*[make_job(f"t{n:02}", description="Tableau reporting") for n in range(20)],
          make_job("o1", description="Looker dashboards"))

    shown(client, upload)

    assert submitted(runner) == ["cv-summary", "check-0"]
    assert len(runner.submissions[-1]) == 20  # all 20 are checked, though only 5 are shown


@pytest.mark.parametrize("answer", [None, {"keywords": "looker"}, {}])
def test_an_unusable_refinement_answer_ends_refining_and_the_search_goes_on(
        client, upload, runner, store, answer):
    store(make_job("t1", description="Tableau reporting"), make_job("t2", description="Looker dashboards"))
    runner.answers["refine-1"] = answer  # a failed call, a wrong type and a missing key

    assert shown(client, upload) == {"t1"}
    assert "refine-1" in submitted(runner)  # the round was tried


def test_the_status_says_refining_round_1_and_a_second_search_is_refused_meanwhile(
        client, upload, runner, store, hold):
    store(make_job("t1", description="Tableau reporting"), make_job("t2", description="Looker dashboards"))
    runner.answers["refine-1"] = {"keywords": ["looker"]}
    arrived, release = hold("refine-")

    base = start(client, upload)

    assert arrived.wait(5)
    assert client.get(f"{base}/status").json() == {"stage": "refining round 1"}
    other = upload(CV).json()
    assert client.post(f"/api/search-requests/{other['id']}/search", json=other).status_code == 409
    release.set()
    assert wait_until_finished(client, base) == {"stage": "done"}


def test_the_status_says_checking_jobs_while_the_jobs_are_checked(client, upload, store, hold):
    store(make_job("t1", description="Tableau reporting"))
    arrived, release = hold("check-")

    base = start(client, upload)

    assert arrived.wait(5)
    assert client.get(f"{base}/status").json() == {"stage": "checking jobs"}
    release.set()
    assert wait_until_finished(client, base) == {"stage": "done"}
