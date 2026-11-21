"""Ticket 14: skill gaps and learning links.

Each shown job lists the job requirements the CV does not meet. A learning link
comes only from the curated list, looked up by the id Qwen returns; an unknown id
is dropped, and a made-up URL never reaches the candidate. The skill gaps come
from the same check call as the grade and claims, with no extra submission."""
from contextlib import closing

import pytest
from fixture_jobs import fixture_jobs, make_job
from pdfs import text_pdf
from searches import wait_until_finished

from app import db, learning_links
from app.services.ingestion import INSERT

CV_TEXT = "Built Tableau dashboards for a retail bank"
CV = text_pdf(CV_TEXT)
# A verified claim, so the job is shown: found in both the CV and the ad text below.
CLAIM = {"requirement": "Tableau", "cv_quote": "Tableau dashboards", "job_quote": "Tableau reporting"}


@pytest.fixture(autouse=True)
def job_database(tmp_path, client):
    """Fill the job database the app reads. The app is started first, so its tables exist."""
    with closing(db.connect(tmp_path)) as conn:
        conn.executemany(INSERT, fixture_jobs())
        conn.commit()


@pytest.fixture
def store(tmp_path):
    def put(*jobs):
        with closing(db.connect(tmp_path)) as conn:
            conn.executemany(INSERT, jobs)
            conn.commit()
    return put


def run(client, upload):
    """Press Search for 'tableau' on a fresh upload, wait for the end and return the results body."""
    review = upload(CV).json()
    base = f"/api/search-requests/{review['id']}"
    body = {**review, "keywords": ["tableau"]}
    assert client.post(f"{base}/search", json=body).status_code == 200
    assert wait_until_finished(client, base) == {"stage": "done"}
    return client.get(f"{base}/results").json()


def test_a_skill_gap_with_a_known_link_id_shows_the_full_link(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting for finance"))
    runner.answers["check-0"] = {"grade": 2, "claims": [CLAIM],
                                 "unmet_requirements": [{"requirement": "Apache Spark", "link_ids": ["spark-basics"]}]}

    [job] = run(client, upload)["jobs"]

    [gap] = job["skill_gaps"]
    assert gap["requirement"] == "Apache Spark"
    link = learning_links.BY_ID["spark-basics"]
    assert gap["learning_links"] == [{"id": link["id"], "title": link["title"], "url": link["url"]}]


def test_an_unknown_link_id_is_dropped_but_the_requirement_still_shows(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting for finance"))
    runner.answers["check-0"] = {"grade": 2, "claims": [CLAIM],
                                 "unmet_requirements": [{"requirement": "Kafka",
                                                         "link_ids": ["spark-basics", "made-up-id"]}]}

    [job] = run(client, upload)["jobs"]

    [gap] = job["skill_gaps"]
    assert gap["requirement"] == "Kafka"
    [link] = gap["learning_links"]  # only the known id survives
    assert link["id"] == "spark-basics"


def test_a_requirement_with_no_links_still_shows_as_a_skill_gap(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting for finance"))
    runner.answers["check-0"] = {"grade": 2, "claims": [CLAIM],
                                 "unmet_requirements": [{"requirement": "Kubernetes", "link_ids": []}]}

    [job] = run(client, upload)["jobs"]

    [gap] = job["skill_gaps"]
    assert gap["requirement"] == "Kubernetes"
    assert gap["learning_links"] == []


def test_the_check_prompt_lists_learning_link_ids_and_titles_but_never_urls(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting for finance"))
    runner.answers["check-0"] = {"grade": 2, "claims": [CLAIM], "unmet_requirements": []}

    run(client, upload)

    prompt = runner.submissions[-1][0]["prompt"]
    assert "spark-basics: Apache Spark Tutorials" in prompt  # the id and title appear
    for link in learning_links.LEARNING_LINKS:
        assert link["url"] not in prompt  # no URL ever reaches Qwen


def test_skill_gaps_come_from_the_same_check_call_with_no_extra_submission(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting for finance"))
    runner.answers["check-0"] = {"grade": 2, "claims": [CLAIM],
                                 "unmet_requirements": [{"requirement": "Docker", "link_ids": ["docker-basics"]}]}

    run(client, upload)

    # The CV summary, a refinement round that adds nothing, then one check submission, and no retry.
    assert [submission[0]["id"] for submission in runner.submissions] == ["cv-summary", "refine-1", "check-0"]


def test_a_job_graded_0_shows_no_skill_gaps(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting for finance"))
    runner.answers["check-0"] = {"grade": 0, "claims": [CLAIM],
                                 "unmet_requirements": [{"requirement": "Docker", "link_ids": ["docker-basics"]}]}

    assert run(client, upload)["jobs"] == []  # grade 0 never appears, so its skill gaps never show


def test_an_answer_without_unmet_requirements_shows_empty_skill_gaps(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting for finance"))
    runner.answers["check-0"] = {"grade": 2, "claims": [CLAIM]}  # no unmet_requirements key

    [job] = run(client, upload)["jobs"]

    assert job["skill_gaps"] == []  # default empty, so an older answer still parses


def test_several_skill_gaps_each_keep_their_own_links_in_order(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting for finance"))
    runner.answers["check-0"] = {"grade": 2, "claims": [CLAIM],
                                 "unmet_requirements": [
                                     {"requirement": "Python for data", "link_ids": ["python-basics", "python-pandas"]},
                                     {"requirement": "AWS", "link_ids": ["aws-cloud"]},
                                     {"requirement": "Kafka", "link_ids": []}]}

    [job] = run(client, upload)["jobs"]

    assert [gap["requirement"] for gap in job["skill_gaps"]] == ["Python for data", "AWS", "Kafka"]
    assert [link["id"] for link in job["skill_gaps"][0]["learning_links"]] == ["python-basics", "python-pandas"]
    assert [link["id"] for link in job["skill_gaps"][1]["learning_links"]] == ["aws-cloud"]
    assert job["skill_gaps"][2]["learning_links"] == []


def test_a_non_string_link_id_is_dropped(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting for finance"))
    runner.answers["check-0"] = {"grade": 2, "claims": [CLAIM],
                                 "unmet_requirements": [{"requirement": "Spark",
                                                         "link_ids": ["spark-basics", 123, None]}]}

    [job] = run(client, upload)["jobs"]

    [gap] = job["skill_gaps"]
    assert [link["id"] for link in gap["learning_links"]] == ["spark-basics"]


def test_an_unmet_requirement_with_a_blank_requirement_is_dropped(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting for finance"))
    runner.answers["check-0"] = {"grade": 2, "claims": [CLAIM],
                                 "unmet_requirements": [{"requirement": "   ", "link_ids": ["docker-basics"]}]}

    [job] = run(client, upload)["jobs"]

    assert job["skill_gaps"] == []  # an empty requirement says nothing, so it is never shown
