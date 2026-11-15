from contextlib import closing
from datetime import date

import pytest
from fixture_jobs import fixture_jobs, make_job
from pdfs import text_pdf
from searches import wait_until_finished

from app import db
from app.services import retrieval
from app.services.ingestion import INSERT

CV_TEXT = "Built Tableau dashboards for a retail bank"
CV = text_pdf(CV_TEXT)
# Found in CV_TEXT and in the description of the jobs below, so a check that returns it is verified.
CLAIM = {"requirement": "Tableau", "cv_quote": "Tableau dashboards", "job_quote": "Tableau reporting"}


@pytest.fixture(autouse=True)
def job_database(tmp_path, client):
    """Fill the job database the app reads. The app is started first, so its tables exist."""
    with closing(db.connect(tmp_path)) as conn:
        conn.executemany(INSERT, fixture_jobs())
        conn.commit()


@pytest.fixture
def store(tmp_path):
    """Add jobs to the database the app reads. Only these jobs mention "tableau", the keyword the tests search."""
    def put(*jobs):
        with closing(db.connect(tmp_path)) as conn:
            conn.executemany(INSERT, jobs)
            conn.commit()
    return put


def run(client, upload, **edits):
    """Press Search for "tableau" on a fresh upload, wait for the end and return the results body.

    Most tests store one qualifying job, so its check is check-0."""
    review = upload(CV).json()
    base = f"/api/search-requests/{review['id']}"
    body = {**review, "keywords": ["tableau"], **edits}
    assert client.post(f"{base}/search", json=body).status_code == 200
    assert wait_until_finished(client, base) == {"stage": "done"}
    return client.get(f"{base}/results").json()


def test_a_job_with_a_verified_claim_is_shown_with_its_grade_and_both_quotes(client, upload, runner, store):
    store(make_job("t1", title="Reporting lead", description="Tableau reporting for finance"))
    runner.answers["check-0"] = {"grade": 2, "claims": [CLAIM]}

    results = run(client, upload)

    [job] = results["jobs"]
    assert (job["job_id"], job["grade"]) == ("t1", 2)
    assert job["claims"] == [CLAIM]
    assert results["dropped_claims"] == 0


def test_a_quote_matches_ignoring_letter_case_and_spacing(client, upload, runner, store):
    store(make_job("t1", description="Tableau\nreporting for finance"))  # a line break, as a PDF or ad may hold
    runner.answers["check-0"] = {"grade": 1, "claims": [
        {**CLAIM, "cv_quote": "tableau   DASHBOARDS", "job_quote": "TABLEAU reporting"}]}

    [job] = run(client, upload)["jobs"]

    assert job["job_id"] == "t1"


def test_a_quote_that_is_only_part_of_a_word_is_not_found(client, upload, runner, store):
    store(make_job("t1", description="Tableau and MySQL reporting"))
    runner.answers["check-0"] = {"grade": 2, "claims": [{**CLAIM, "job_quote": "SQL"}]}

    results = run(client, upload)

    assert results["jobs"] == []  # "SQL" is inside "MySQL", not a word of its own
    assert results["dropped_claims"] == 1


def test_a_blank_quote_is_dropped(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting"))
    runner.answers["check-0"] = {"grade": 2, "claims": [{**CLAIM, "cv_quote": ""}]}

    results = run(client, upload)

    assert results["jobs"] == []  # an empty quote would be "found" anywhere
    assert results["dropped_claims"] == 1


def test_a_claim_quote_found_only_in_the_cv_summary_is_dropped(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting for finance"))
    runner.answers["cv-summary"] = {**runner.answers["cv-summary"], "summary": "Expert in Looker."}
    runner.answers["check-0"] = {"grade": 2, "claims": [{**CLAIM, "cv_quote": "Looker"}]}

    results = run(client, upload)

    assert results["jobs"] == []  # the summary is Qwen's paraphrase, so it proves nothing (ADR 0003)
    assert results["dropped_claims"] == 1


def test_a_job_quote_found_only_in_the_requirements_list_is_dropped(client, upload, runner, store):
    store({**make_job("t1", title="Tableau analyst", description="We need a finance analyst."),
           "requirements": '["Tableau reporting"]'})
    runner.answers["check-0"] = {"grade": 2, "claims": [CLAIM]}  # "Tableau reporting" is not in the ad text

    results = run(client, upload)

    assert results["jobs"] == []  # the extracted requirements never verify a quote (ADR 0003)
    assert results["dropped_claims"] == 1


def test_a_claim_with_a_missing_quote_is_dropped_and_qwen_is_not_asked_again(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting for finance"))
    runner.answers["check-0"] = {"grade": 2, "claims": [{"requirement": "Tableau", "cv_quote": "Tableau"}]}

    results = run(client, upload)

    assert results["jobs"] == []
    assert results["dropped_claims"] == 1
    assert len(runner.submissions) == 2  # the CV summary, then one check submission, and no retry


def test_a_job_graded_0_never_appears_even_with_a_verified_claim(client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting for finance"))
    runner.answers["check-0"] = {"grade": 0, "claims": [CLAIM]}

    assert run(client, upload)["jobs"] == []


def test_each_check_prompt_carries_the_cv_summary_cv_text_and_one_ad_but_never_the_preferences(
        client, upload, runner, store):
    store(make_job("t1", description="Tableau reporting for finance teams"),
          make_job("t2", description="Tableau dashboards for hospitals"))
    runner.answers["check-0"] = {"grade": 0, "claims": []}
    runner.answers["check-1"] = {"grade": 0, "claims": []}

    run(client, upload, experience_band="6-9", industry="Insurance")

    prompts = [item["prompt"] for item in runner.submissions[-1]]
    assert len(prompts) == 2
    assert all("Analyst with five years in retail banking" in p for p in prompts)  # the CV summary
    assert all(CV_TEXT in p for p in prompts)  # the full CV text
    assert all(("finance" in p) != ("hospitals" in p) for p in prompts)  # one ad each, never both
    assert not any("Insurance" in p or "6-9" in p for p in prompts)  # preferences never reach Qwen


def keyword_order(client, keyword):
    """The job ids retrieval finds for one keyword, in keyword order, before any grading."""
    with closing(db.connect(client.app.state.data_dir)) as conn:
        return [job["job_id"] for job in retrieval.find_qualifying(conn, [keyword], ["full-time"])]


def test_a_grade_2_job_is_shown_before_a_grade_1_job_even_when_keyword_order_puts_it_later(
        client, upload, runner, store):
    # "Tableau Tableau" scores higher than "Tableau", so g1 comes first in keyword order.
    store(make_job("g1", description="Tableau Tableau reporting"),
          make_job("g2", description="Tableau reporting"))
    assert keyword_order(client, "tableau") == ["g1", "g2"]  # so check-0 is g1 and check-1 is g2
    runner.answers["check-0"] = {"grade": 1, "claims": [CLAIM]}
    runner.answers["check-1"] = {"grade": 2, "claims": [CLAIM]}

    assert [job["job_id"] for job in run(client, upload)["jobs"]] == ["g2", "g1"]


def test_jobs_of_the_same_grade_keep_the_keyword_order(client, upload, runner, store):
    store(make_job("s1", description="Tableau reporting"),
          make_job("s2", description="Tableau Tableau reporting"))
    assert keyword_order(client, "tableau") == ["s2", "s1"]
    runner.answers["check-0"] = {"grade": 2, "claims": [CLAIM]}
    runner.answers["check-1"] = {"grade": 2, "claims": [CLAIM]}

    assert [job["job_id"] for job in run(client, upload)["jobs"]] == ["s2", "s1"]


def test_at_most_five_jobs_are_shown(client, upload, runner, store):
    store(*[make_job(f"f{n}", description="Tableau reporting for finance") for n in range(1, 8)])
    for n in range(7):
        runner.answers[f"check-{n}"] = {"grade": 1, "claims": [CLAIM]}

    results = run(client, upload)

    # Equal scores go by job id, so the first five in keyword order are f1 to f5.
    assert [job["job_id"] for job in results["jobs"]] == ["f1", "f2", "f3", "f4", "f5"]


def test_without_a_canned_answer_the_fake_grades_a_job_by_quoting_its_text(client, upload, store):
    store(make_job("t1", description="Tableau reporting for finance"))

    results = run(client, upload)

    [job] = results["jobs"]
    assert (job["grade"], results["dropped_claims"]) == (2, 0)  # its quotes come from the prompt, so both verify


def test_a_shown_job_carries_its_collection_date_and_its_posted_date(client, upload, runner, store):
    store({**make_job("d1", description="Tableau reporting for finance"), "posted_date": "2026-11-01"},
          make_job("d2", description="Tableau reporting for banks"))  # the source gave no posted date
    runner.answers["check-0"] = {"grade": 2, "claims": [CLAIM]}
    runner.answers["check-1"] = {"grade": 2, "claims": [CLAIM]}

    jobs = {job["job_id"]: job for job in run(client, upload)["jobs"]}

    assert jobs["d1"]["posted_date"] == "2026-11-01"
    assert jobs["d2"]["posted_date"] is None
    assert jobs["d1"]["collected"] == date.today().isoformat()
