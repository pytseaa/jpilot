"""Ingestion stores each new ad once its extraction works. The database is the seam."""
import pytest
from fake_jsearch import job
from samples import EXTRACTED, TODAY, rows

from app.runners.fake import FakeRunner
from app.runners.tacc import SubmissionFailed
from app.services.ingestion import store_new_ads


def test_a_new_ad_is_stored_with_its_fields_and_both_dates_set_to_today(conn):
    ad = job("ad-1", job_title="Data Analyst", employer_name="Acme", job_location="Central, Hong Kong",
             job_posted_at_datetime_utc="2026-11-04T00:00:00.000Z",
             job_apply_link="https://example.com/apply", job_description="Build reports.")

    store_new_ads([ad], FakeRunner({"ad-0": EXTRACTED}), conn, TODAY)

    assert rows(conn) == [{
        "job_id": "ad-1", "title": "Data Analyst", "description": "Build reports.", "employer": "Acme",
        "location": "Central, Hong Kong", "posted_date": "2026-11-04",
        "apply_link": "https://example.com/apply", "first_seen": TODAY, "collected": TODAY,
        "region": "Hong Kong", "employment_types": '["full-time"]', "minimum_years": 3,
        "industry": "Banking and finance", "requirements": '["SQL", "Python"]', "unverified": 0,
    }]


def test_each_new_ad_gets_one_extraction_prompt_and_they_all_go_in_one_submission(conn):
    runner = FakeRunner({"ad-0": EXTRACTED, "ad-1": EXTRACTED})

    store_new_ads([job("a", job_description="First ad."), job("b", job_description="Second ad.")],
                  runner, conn, TODAY)

    [submission] = runner.submissions
    assert [item["id"] for item in submission] == ["ad-0", "ad-1"]
    assert "First ad." in submission[0]["prompt"] and "Second ad." in submission[1]["prompt"]
    assert "industry" in submission[0]["required_keys"]


def test_a_run_with_no_new_ads_makes_no_submission(conn):
    runner = FakeRunner({})

    store_new_ads([], runner, conn, TODAY)

    assert runner.submissions == []


def test_a_failed_submission_stores_nothing_and_the_error_reaches_the_caller(conn):
    def broken(prompts):
        raise SubmissionFailed("The Qwen service could not be reached.")

    with pytest.raises(SubmissionFailed):
        store_new_ads([job("a")], broken, conn, TODAY)

    assert rows(conn) == []


def test_an_ad_whose_extraction_fails_stays_unstored_and_the_others_are_kept(conn):
    runner = FakeRunner({"ad-0": None, "ad-1": EXTRACTED})

    assert store_new_ads([job("bad"), job("good")], runner, conn, TODAY) == (1, 1)
    assert [row["job_id"] for row in rows(conn)] == ["good"]


def test_an_answer_outside_the_fixed_lists_stays_unstored(conn):
    runner = FakeRunner({"ad-0": {**EXTRACTED, "industry": "Crypto"}})

    assert store_new_ads([job("a")], runner, conn, TODAY) == (0, 1)
    assert rows(conn) == []


def test_a_job_with_an_unknown_region_or_employment_type_is_stored_and_flagged_unverified(conn):
    runner = FakeRunner({"ad-0": {**EXTRACTED, "region": "unknown"},
                         "ad-1": {**EXTRACTED, "employment_types": []},
                         "ad-2": EXTRACTED})

    store_new_ads([job("no-region"), job("no-type"), job("known")], runner, conn, TODAY)

    assert {row["job_id"]: row["unverified"] for row in rows(conn)} == {
        "no-region": 1, "no-type": 1, "known": 0}
