"""One whole ingestion run: fetch, tell new ads from stored ones, extract, store. The run is the seam."""
import pytest
from fake_jsearch import job
from samples import EXTRACTED, TODAY, jsearch_returning, rows

from app.runners.fake import FakeRunner
from app.runners.tacc import SubmissionFailed
from app.services.ingestion import run


def everything_extracts():
    return FakeRunner({f"ad-{i}": EXTRACTED for i in range(10)})


def test_a_first_run_stores_every_new_ad_and_reports_the_counts(conn):
    report = run(jsearch_returning(job("a"), job("b")), everything_extracts(), conn, TODAY)

    assert [row["job_id"] for row in rows(conn)] == ["a", "b"]
    assert vars(report) == {"fetched": 2, "stored": 2, "already_stored": 0, "dropped_chinese": 0,
                            "failed_extraction": 0, "failed_requests": 0}


def test_an_ad_already_stored_gets_a_new_collection_date_and_keeps_its_first_seen_date(conn):
    run(jsearch_returning(job("a")), everything_extracts(), conn, "2026-11-01")

    report = run(jsearch_returning(job("a")), everything_extracts(), conn, "2026-11-14")

    [row] = rows(conn)
    assert (row["first_seen"], row["collected"]) == ("2026-11-01", "2026-11-14")
    assert (report.already_stored, report.stored) == (1, 0)


def test_an_ad_already_stored_is_not_extracted_again(conn):
    run(jsearch_returning(job("a")), everything_extracts(), conn, "2026-11-01")
    second = everything_extracts()

    run(jsearch_returning(job("a"), job("b")), second, conn, "2026-11-14")

    [submission] = second.submissions
    assert len(submission) == 1  # only the new ad "b" is sent to Qwen


def ad_with_chinese(chinese, english, job_id="zh"):
    """An ad whose description has this many Chinese characters and this many English ones."""
    return job(job_id, job_description="\u8077" * chinese + "x" * english)


def test_an_ad_that_is_at_least_20_percent_chinese_is_dropped_before_extraction_and_counted(conn):
    runner = everything_extracts()

    report = run(jsearch_returning(ad_with_chinese(20, 80)), runner, conn, TODAY)

    assert rows(conn) == [] and runner.submissions == []
    assert (report.dropped_chinese, report.stored) == (1, 0)


def test_an_ad_just_under_20_percent_chinese_is_kept(conn):
    report = run(jsearch_returning(ad_with_chinese(19, 81)), everything_extracts(), conn, TODAY)

    assert [row["job_id"] for row in rows(conn)] == ["zh"]
    assert report.dropped_chinese == 0


def test_an_english_ad_with_a_few_chinese_words_such_as_a_company_name_is_kept(conn):
    ad = job("a", job_description="Join \u9999\u6e2f\u9280\u884c as an analyst. " + "Build reports. " * 20)

    run(jsearch_returning(ad), everything_extracts(), conn, TODAY)

    assert [row["job_id"] for row in rows(conn)] == ["a"]


def test_an_ad_with_no_description_is_not_dropped_and_does_not_crash(conn):
    report = run(jsearch_returning(job("empty", job_description="")), everything_extracts(), conn, TODAY)

    assert report.dropped_chinese == 0 and [row["job_id"] for row in rows(conn)] == ["empty"]


def test_re_running_with_the_same_responses_leaves_the_database_unchanged(conn):
    ads = [job("a"), job("b"), ad_with_chinese(20, 80)]
    run(jsearch_returning(*ads), everything_extracts(), conn, TODAY)
    before = rows(conn)

    report = run(jsearch_returning(*ads), everything_extracts(), conn, TODAY)

    assert rows(conn) == before
    assert (report.stored, report.already_stored, report.dropped_chinese) == (0, 2, 1)


def test_an_ad_whose_extraction_failed_is_tried_again_by_the_next_run(conn):
    first = FakeRunner({"ad-0": None})
    run(jsearch_returning(job("a")), first, conn, "2026-11-01")
    assert rows(conn) == []

    report = run(jsearch_returning(job("a")), everything_extracts(), conn, "2026-11-14")

    [row] = rows(conn)
    assert (row["first_seen"], report.stored) == ("2026-11-14", 1)


def test_a_failed_submission_still_refreshes_the_ads_already_stored(conn):
    run(jsearch_returning(job("old")), everything_extracts(), conn, "2026-11-01")

    def broken(prompts):
        raise SubmissionFailed("The Qwen service could not be reached.")

    with pytest.raises(SubmissionFailed):
        run(jsearch_returning(job("old"), job("new")), broken, conn, "2026-11-14")

    assert {row["job_id"]: row["collected"] for row in rows(conn)} == {"old": "2026-11-14"}
