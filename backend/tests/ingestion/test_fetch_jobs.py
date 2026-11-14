"""The planned JSearch searches: which roles, how many pages, and what comes back."""
from fake_jsearch import FakeJSearch, job

from app.services.ingestion import fetch_jobs

# The roles of the spec's ingestion plan, written out so the test does not read them from the code.
QUERIES = [f"{role} in Hong Kong" for role in (
    "accountant", "financial analyst", "data analyst", "marketing manager", "sales executive",
    "customer service officer", "human resources officer", "graphic designer", "registered nurse",
    "teacher", "mechanical engineer", "software developer", "administrative assistant",
    "logistics officer", "business analyst")]


def test_it_searches_each_of_the_15_roles_for_two_pages_and_makes_30_requests_at_most():
    jsearch = FakeJSearch()  # every role has three pages to give

    fetch_jobs(jsearch)

    assert len(jsearch.calls) == 30
    assert sorted(query for query, _ in jsearch.calls) == sorted(QUERIES * 2)


def test_the_second_page_is_asked_for_with_the_cursor_of_the_first():
    jsearch = FakeJSearch()

    fetch_jobs(jsearch)

    accountant = [call for call in jsearch.calls if call[0] == "accountant in Hong Kong"]
    assert accountant == [("accountant in Hong Kong", None), ("accountant in Hong Kong", "1")]


def test_it_returns_the_jobs_of_both_pages_and_none_of_the_third():
    jobs, failed = fetch_jobs(FakeJSearch())

    ids = {item["job_id"] for item in jobs}
    assert "accountant in Hong Kong#0.0" in ids and "accountant in Hong Kong#1.1" in ids
    assert "accountant in Hong Kong#2.0" not in ids
    assert len(jobs) == 60 and failed == 0


def test_a_failed_request_is_counted_and_the_other_roles_are_still_searched():
    jsearch = FakeJSearch(failing=[("accountant in Hong Kong", None)])

    jobs, failed = fetch_jobs(jsearch)

    assert failed == 1
    assert not any(item["job_id"].startswith("accountant") for item in jobs)  # no cursor, so no page 2 either
    assert len({item["job_id"].split("#")[0] for item in jobs}) == 14
    assert len(jsearch.calls) == 29


def test_a_job_without_a_job_id_is_left_out_and_the_run_goes_on():
    jsearch = FakeJSearch({"accountant in Hong Kong": [[{"job_title": "No id"}, job("with-id")]]})

    jobs, _ = fetch_jobs(jsearch)

    assert "with-id" in {item["job_id"] for item in jobs}
    assert not any(item.get("job_title") == "No id" for item in jobs)


def test_a_job_that_two_roles_both_return_is_kept_once():
    shared = job("shared-job")
    jsearch = FakeJSearch({"data analyst in Hong Kong": [[shared]],
                           "business analyst in Hong Kong": [[shared, job("only-business")]]})

    jobs, _ = fetch_jobs(jsearch)

    assert [item["job_id"] for item in jobs].count("shared-job") == 1
    assert "only-business" in {item["job_id"] for item in jobs}
