import threading
from contextlib import closing

import pytest
from fixture_jobs import make_job
from pdfs import text_pdf
from searches import wait_until_finished

from app import db
from app.runners.fake import FakeRunner
from app.runners.tacc import SubmissionFailed
from app.services import retrieval
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


def prompt_of(runner, prompt_id):
    [prompt] = [s[0]["prompt"] for s in runner.submissions if s[0]["id"] == prompt_id]
    return prompt


def test_two_extra_rounds_run_and_a_third_never_does(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting"), make_job("t2", description="Looker dashboards"),
          make_job("t3", description="Qlik dashboards"), make_job("u1", description="Excel macros"))
    runner.answers["refine-1"] = {"keywords": ["looker"]}
    runner.answers["refine-2"] = {"keywords": ["qlik"]}
    runner.answers["refine-3"] = {"keywords": ["excel"]}  # would bring in u1, if a third round ran

    assert shown(client, upload) == {"t1", "t2", "t3"}  # t1 is the candidate's own match, kept through both rounds
    assert submitted(runner) == ["cv-summary", "refine-1", "refine-2", "check-0"]


def test_refining_stops_after_round_1_once_20_jobs_qualify(client, upload, runner, store):
    store(*[make_job(f"t{n:02}", description=f"Tableau reporting t{n:02}") for n in range(1, 20)],
          make_job("l1", description="Looker dashboards l1"), make_job("q1", description="Qlik dashboards q1"))
    runner.answers["refine-1"] = {"keywords": ["looker"]}  # the 20th qualifying job
    runner.answers["refine-2"] = {"keywords": ["qlik"]}

    shown(client, upload)

    assert submitted(runner) == ["cv-summary", "refine-1", "check-0"]
    assert "q1" not in checked_ids(runner) and "l1" in checked_ids(runner)
    assert len(runner.submissions[-1]) == 20


def test_refining_stops_after_round_1_once_every_job_passing_the_hard_filters_qualifies(
        client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting"), make_job("t2", description="Looker dashboards"))
    runner.answers["refine-1"] = {"keywords": ["looker"]}  # t2 was the only job left over

    assert shown(client, upload) == {"t1", "t2"}
    assert submitted(runner) == ["cv-summary", "refine-1", "check-0"]


def test_refining_stops_when_qwen_adds_no_new_keyword(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting"), make_job("t2", description="Looker dashboards"))
    runner.answers["refine-1"] = {"keywords": ["Tableau", "the", "experience"]}  # a repeat and two stop words

    assert shown(client, upload) == {"t1"}
    assert submitted(runner) == ["cv-summary", "refine-1", "check-0"]  # a second round could not change the search


def test_refining_stops_when_qwen_proposes_only_a_word_that_matching_ignores(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting"), make_job("t2", description="Looker dashboards"))
    # The stop list keeps "IT" so the review screen can show it, but matching ignores it, so it cannot change the search.
    runner.answers["refine-1"] = {"keywords": ["IT"]}

    assert shown(client, upload) == {"t1"}
    assert submitted(runner) == ["cv-summary", "refine-1", "check-0"]


def test_new_keywords_pass_the_stop_list_and_repeats_are_dropped_and_the_old_keywords_stay(
        client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting"), make_job("t2", description="Looker dashboards"),
          make_job("t3", description="Qlik dashboards"))
    runner.answers["refine-1"] = {"keywords": ["the", "experience", "Tableau", "Looker", "LOOKER",
                                               "Business Intelligence"]}

    shown(client, upload)

    # Round 2 holds the candidate's keyword first, then the new ones in Qwen's order, once each, spelled as first given.
    assert prompt_of(runner, "refine-2").endswith("Keywords so far:\ntableau, Looker, Business Intelligence")


def checked_ids(runner):
    """The job ids in the last submission, in prompt order. Each test ad ends with its own job id."""
    return [item["prompt"].split()[-1] for item in runner.submissions[-1]]


def test_when_more_than_20_qualify_jobs_from_the_earlier_round_come_first_and_the_best_others_fill_the_rest(
        client, upload, runner, store):
    earlier = [make_job(f"e{n:02}", description=f"Tableau reporting e{n:02}") for n in range(1, 16)]
    # n04 to n08 say "Looker" twice and n01 to n03 once, so the 5 best others are not the 5 lowest ids.
    others = [make_job(f"n{n:02}", description=f"Looker {'Looker ' if n > 3 else ''}dashboards n{n:02}")
              for n in range(1, 9)]
    store(*earlier, *others)
    runner.answers["refine-1"] = {"keywords": ["looker"]}
    with closing(db.connect(client.app.state.data_dir)) as conn:
        by_score = [job["job_id"] for job in retrieval.find_qualifying(conn, ["tableau", "looker"], ["full-time"])]
    # Score order alone puts all 8 others first, which would push 3 earlier jobs out of the 20.
    assert by_score[:5] == [f"n{n:02}" for n in range(4, 9)] and set(by_score[:8]) == {f"n{n:02}" for n in range(1, 9)}

    shown(client, upload)

    # All 15 earlier jobs, then the 5 best others by keyword score. Equal scores go by job id.
    assert checked_ids(runner) == [f"e{n:02}" for n in range(1, 16)] + [f"n{n:02}" for n in range(4, 9)]


def test_up_to_20_qualifying_jobs_keep_keyword_order_whichever_round_found_them(client, upload, runner, store):
    # t2 says "Looker" three times, so it outscores t1 once both keywords count. Nothing is cut, so no job needs protecting.
    store(make_job("t1", description="Tableau reporting t1"),
          make_job("t2", description="Looker Looker Looker dashboards t2"),
          *[make_job(f"f{n}", description=f"Excel macros f{n}") for n in range(1, 6)])  # they never match
    runner.answers["refine-1"] = {"keywords": ["looker"]}
    with closing(db.connect(client.app.state.data_dir)) as conn:
        by_score = [job["job_id"] for job in retrieval.find_qualifying(conn, ["tableau", "looker"], ["full-time"])]
    assert by_score == ["t2", "t1"]

    shown(client, upload)

    assert checked_ids(runner) == ["t2", "t1"]  # t1 was found in the first search and t2 in round 1


@pytest.mark.parametrize("held_at, stage", [
    ("refine-1", "refining round 1"), ("refine-2", "refining round 2"), ("check-", "checking jobs")])
def test_the_status_names_each_running_stage_and_a_second_search_is_refused_meanwhile(
        client, upload, runner, store, hold, held_at, stage):
    store(make_job("t1", description="Tableau reporting"), make_job("t2", description="Looker dashboards"),
          make_job("t3", description="Qlik dashboards"))
    runner.answers["refine-1"] = {"keywords": ["looker"]}  # t3 is left over, so round 2 runs
    arrived, release = hold(held_at)

    base = start(client, upload)

    assert arrived.wait(5)
    assert client.get(f"{base}/status").json() == {"stage": stage}
    other = upload(CV).json()
    assert client.post(f"/api/search-requests/{other['id']}/search", json=other).status_code == 409
    release.set()
    assert wait_until_finished(client, base) == {"stage": "done"}


def test_a_refinement_submission_that_raises_ends_the_search_as_failed(client, upload, store, monkeypatch):
    store(make_job("t1", description="Tableau reporting"), make_job("t2", description="Looker dashboards"))
    real = FakeRunner.__call__

    def call(self, prompts):
        if prompts[0]["id"].startswith("refine-"):
            raise SubmissionFailed("the Qwen service cannot be reached")
        return real(self, prompts)

    monkeypatch.setattr(FakeRunner, "__call__", call)

    base = start(client, upload)

    assert wait_until_finished(client, base)["stage"] == "failed"
    assert client.get(f"{base}/results").status_code == 409  # no partial list
