"""The real JSearch client, run against a fake HTTP server so no request reaches the network."""
import httpx
import pytest

from app.jsearch import JSearch, SearchFailed


def client_answering(status=200, json=None, content=None):
    """A JSearch client whose HTTP calls are answered by this canned response. Also logs the requests."""
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, json=json, content=content)

    return JSearch("secret-key", httpx.Client(transport=httpx.MockTransport(handler))), seen


def test_it_asks_for_hong_kong_jobs_in_english_with_the_key_in_a_header():
    search, seen = client_answering(json={"data": {"jobs": [], "cursor": None}})

    search("data analyst in Hong Kong")

    [request] = seen
    assert request.headers["x-api-key"] == "secret-key"
    assert dict(request.url.params) == {"query": "data analyst in Hong Kong", "country": "hk",
                                        "language": "en"}


def test_the_cursor_of_the_first_page_is_sent_to_get_the_second():
    search, seen = client_answering(json={"data": {"jobs": [], "cursor": None}})

    search("data analyst in Hong Kong", cursor="abc")

    assert seen[0].url.params["cursor"] == "abc"


def test_it_returns_the_jobs_and_the_cursor_of_the_next_page():
    search, _ = client_answering(json={"status": "OK", "data": {"jobs": [{"job_id": "a"}], "cursor": "next"}})

    assert search("q") == ([{"job_id": "a"}], "next")


@pytest.mark.parametrize("status, json, content", [
    (429, {"error": "quota"}, None),   # the monthly quota is used up
    (200, None, b"not json"),
    (200, {"data": {}}, None),         # no job list where the real response has one
    (200, {"data": {"jobs": None}}, None),
])
def test_an_answer_it_cannot_use_is_a_failed_search_that_never_shows_the_key(status, json, content):
    search, _ = client_answering(status, json, content)

    with pytest.raises(SearchFailed) as error:
        search("q")

    assert "secret-key" not in str(error.value)


def test_it_reads_the_key_from_the_environment(monkeypatch):
    monkeypatch.setenv("JSEARCH_API_KEY", "from-env")

    assert JSearch.from_environment().api_key == "from-env"


def test_a_missing_key_stops_the_run_before_any_request(monkeypatch):
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)

    with pytest.raises(ValueError, match="JSEARCH_API_KEY"):
        JSearch.from_environment()
