"""The JSearch search service: the only place ingestion talks to the network."""
import os

import httpx

URL = "https://api.openwebninja.com/jsearch/search-v2"


class SearchFailed(Exception):
    """One JSearch request did not give a usable answer."""


class JSearch:
    """One page of search results per call. The key is held in memory and goes only in a header."""

    def __init__(self, api_key, http=None):
        self.api_key = api_key
        self.http = http or httpx.Client(timeout=60)

    @classmethod
    def from_environment(cls):
        key = os.environ.get("JSEARCH_API_KEY")
        if not key:
            raise ValueError("JSEARCH_API_KEY is not set. Put the JSearch key in that environment variable.")
        return cls(key)

    def __call__(self, query, cursor=None):
        """Return the jobs of one page and the cursor of the next page, or None on the last one."""
        params = {"query": query, "country": "hk", "language": "en"}
        if cursor:
            params["cursor"] = cursor
        try:
            response = self.http.get(URL, params=params, headers={"x-api-key": self.api_key})
        except httpx.HTTPError as exc:
            raise SearchFailed(f"JSearch could not be reached ({type(exc).__name__}).") from exc
        if response.status_code != 200:
            raise SearchFailed(f"JSearch answered HTTP {response.status_code}.")
        try:
            data = response.json()["data"]
            jobs = [job for job in data["jobs"] if isinstance(job, dict)]
            return jobs, data.get("cursor")
        except (ValueError, KeyError, TypeError) as exc:
            raise SearchFailed("JSearch gave an answer without a job list.") from exc
