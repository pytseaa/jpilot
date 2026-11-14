"""One whole ingestion run: fetch, tell new jobs from stored ones, extract, store. The run is the seam."""
import pytest
from fake_jsearch import job
from samples import EXTRACTED, TODAY, jsearch_returning, rows

from app.runners.fake import FakeRunner
from app.runners.tacc import SubmissionFailed
from app.services.ingestion import run


def everything_extracts():
    return FakeRunner({f"job-{i}": EXTRACTED for i in range(10)})


def test_a_first_run_stores_every_new_job_and_reports_the_counts(conn):
    report = run(jsearch_returning(job("a"), job("b")), everything_extracts(), conn, TODAY)

    assert [row["job_id"] for row in rows(conn)] == ["a", "b"]
    assert vars(report) == {"fetched": 2, "stored": 2, "already_stored": 0, "dropped_chinese": 0,
                            "dropped_no_description": 0, "failed_extraction": 0, "failed_requests": 0}


def test_a_job_already_stored_gets_a_new_collection_date_and_keeps_its_first_seen_date(conn):
    run(jsearch_returning(job("a")), everything_extracts(), conn, "2026-11-01")

    report = run(jsearch_returning(job("a")), everything_extracts(), conn, "2026-11-14")

    [row] = rows(conn)
    assert (row["first_seen"], row["collected"]) == ("2026-11-01", "2026-11-14")
    assert (report.already_stored, report.stored) == (1, 0)


def test_a_job_already_stored_is_not_extracted_again(conn):
    run(jsearch_returning(job("a")), everything_extracts(), conn, "2026-11-01")
    second = everything_extracts()

    run(jsearch_returning(job("a"), job("b")), second, conn, "2026-11-14")

    [submission] = second.submissions
    assert len(submission) == 1  # only the new job "b" is sent to Qwen


def job_with_chinese(chinese, english, job_id="zh"):
    """A job whose description has this many Chinese characters and this many English ones."""
    return job(job_id, job_description="\u8077" * chinese + "x" * english)


def test_a_job_that_is_at_least_20_percent_chinese_is_dropped_before_extraction_and_counted(conn):
    runner = everything_extracts()

    report = run(jsearch_returning(job_with_chinese(20, 80)), runner, conn, TODAY)

    assert rows(conn) == [] and runner.submissions == []
    assert (report.dropped_chinese, report.stored) == (1, 0)


def test_a_job_just_under_20_percent_chinese_is_kept(conn):
    report = run(jsearch_returning(job_with_chinese(19, 81)), everything_extracts(), conn, TODAY)

    assert [row["job_id"] for row in rows(conn)] == ["zh"]
    assert report.dropped_chinese == 0


def test_an_english_job_with_a_few_chinese_words_such_as_a_company_name_is_kept(conn):
    job_with_company_name = job("a", job_description="Join \u9999\u6e2f\u9280\u884c as an analyst. " + "Build reports. " * 20)

    run(jsearch_returning(job_with_company_name), everything_extracts(), conn, TODAY)

    assert [row["job_id"] for row in rows(conn)] == ["a"]


@pytest.mark.parametrize("description", ["", "  \n ", None])
def test_a_job_with_no_description_is_dropped_before_extraction_and_counted(conn, description):
    runner = everything_extracts()

    report = run(jsearch_returning(job("empty", job_description=description)), runner, conn, TODAY)

    assert rows(conn) == [] and runner.submissions == []
    assert (report.dropped_no_description, report.dropped_chinese, report.stored) == (1, 0, 0)


def test_re_running_with_the_same_responses_leaves_the_database_unchanged(conn):
    jobs = [job("a"), job("b"), job_with_chinese(20, 80)]
    run(jsearch_returning(*jobs), everything_extracts(), conn, TODAY)
    before = rows(conn)

    report = run(jsearch_returning(*jobs), everything_extracts(), conn, TODAY)

    assert rows(conn) == before
    assert (report.stored, report.already_stored, report.dropped_chinese) == (0, 2, 1)


def test_a_job_whose_extraction_failed_is_tried_again_by_the_next_run(conn):
    first = FakeRunner({"job-0": None})
    run(jsearch_returning(job("a")), first, conn, "2026-11-01")
    assert rows(conn) == []

    report = run(jsearch_returning(job("a")), everything_extracts(), conn, "2026-11-14")

    [row] = rows(conn)
    assert (row["first_seen"], report.stored) == ("2026-11-14", 1)


def test_a_failed_submission_still_refreshes_the_jobs_already_stored(conn):
    run(jsearch_returning(job("old")), everything_extracts(), conn, "2026-11-01")

    def broken(prompts):
        raise SubmissionFailed("The Qwen service could not be reached.")

    with pytest.raises(SubmissionFailed):
        run(jsearch_returning(job("old"), job("new")), broken, conn, "2026-11-14")

    assert {row["job_id"]: row["collected"] for row in rows(conn)} == {"old": "2026-11-14"}
