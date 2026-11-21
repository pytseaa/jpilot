"""Tickets 09–11: expectations are recorded in verification/tickets-09-11.md before the run."""
import json
from contextlib import closing

import pytest
from fixture_jobs import make_job
from pdfs import text_pdf
from searches import wait_until_finished

from app import db
from app.runners.fake import FakeRunner
from app.runners.tacc import SERVICE_MESSAGE, SubmissionFailed
from app.services.ingestion import INSERT
from app.trace import latency_summary

MARKER = "UNIQUE-CV-PRIVACY-9274"


def store(client, *jobs):
    with closing(db.connect(client.app.state.data_dir)) as conn:
        conn.executemany(INSERT, jobs)
        conn.commit()


def start(client, upload, text="Built SQL reports", **edits):
    response = upload(text_pdf(text))
    assert response.status_code == 200
    review = response.json()
    assert response.headers["X-Request-ID"] == review["id"]
    base = f"/api/search-requests/{review['id']}"
    assert client.post(f"{base}/search", json={**review, "keywords": ["SQL"], **edits}).status_code == 200
    return base, review


def trace_for(client, request_id):
    return json.loads((client.app.state.data_dir / "traces" / f"{request_id}.json").read_text())


def test_short_results_explain_fit_without_padding_with_grade_zero(client, upload, runner):
    store(client, make_job("a", description="SQL reports"), make_job("b", description="SQL reports"))
    runner.answers["check-0"] = {"grade": 0, "claims": []}
    base, review = start(client, upload)
    assert wait_until_finished(client, base)["stage"] == "done"
    result = client.get(f"{base}/results").json()
    assert len(result["jobs"]) == 1
    assert result["jobs"][0]["grade"] in (1, 2)
    assert "Only jobs with a fit" in result["explanation"]
    assert "graded 0" in result["explanation"]
    assert client.post(f"{base}/search", json=review).status_code == 410


@pytest.mark.parametrize("scenario, text, edits, expected", [
    ("sparse CV", "SQL", {}, "too brief"),
    ("conflicting constraints", "Built SQL reports", {"employment_types": ["contractor"]}, "form"),
    ("no suitable jobs", "Botanical field research", {}, "No job fits"),
    ("no keywords", "Built SQL reports", {"keywords": ["unrepresented"]}, "keywords"),
])
def test_empty_results_explain_the_cause(client, upload, runner, scenario, text, edits, expected):
    store(client, make_job("a", description="SQL reports"))
    runner.answers["check-0"] = {"grade": 0, "claims": []}
    base, _ = start(client, upload, text, **edits)
    assert wait_until_finished(client, base)["stage"] == "done"
    result = client.get(f"{base}/results").json()
    assert result["jobs"] == []
    assert expected in result["explanation"]


def test_unreadable_cv_is_rejected_before_a_call_and_keeps_a_failed_trace(client, upload, runner):
    response = upload(b"not a PDF")
    assert response.status_code == 422
    assert "text-based PDF" in response.json()["detail"]
    assert runner.submissions == []
    trace = trace_for(client, response.headers["X-Request-ID"])
    assert trace["outcome"] == "failed"
    assert trace["stages"][0]["name"] == "reading CV"


@pytest.mark.parametrize("failure", ["submission", "unreachable", "incomplete", "unexpected"])
def test_failed_search_deletes_cv_has_no_partial_results_and_requires_reupload(
        client, upload, runner, monkeypatch, tmp_path, caplog, failure):
    store(client, make_job("a", description="SQL reports"))
    original = FakeRunner.__call__

    def fail(self, prompts):
        if prompts[0]["id"].startswith("check-"):
            if failure == "unreachable":
                return {p["id"]: {"status": "failed", "error_type": "unreachable", "attempts": 1} for p in prompts}
            if failure == "incomplete":
                return {}
            if failure == "unexpected":
                raise ValueError(MARKER)
            raise SubmissionFailed(MARKER)
        return original(self, prompts)

    monkeypatch.setattr(FakeRunner, "__call__", fail)
    runner.answers["cv-summary"]["summary"] = MARKER
    base, review = start(client, upload, f"Built SQL reports {MARKER}")
    status = wait_until_finished(client, base)
    assert status["stage"] == "failed"
    assert "upload" in status["error"]
    if failure == "unreachable":
        assert "restart" in status["error"] and "server-url.txt" in status["error"]
    assert client.get(f"{base}/results").status_code == 409
    assert client.post(f"{base}/search", json=review).status_code == 410
    stored = client.app.state.requests[review["id"]]
    assert (stored.cv_text, stored.summary, stored.keywords, stored.target_role, stored.jobs) == ("", "", [], "", [])
    assert trace_for(client, review["id"])["outcome"] == "failed"
    assert MARKER not in caplog.text
    assert all(MARKER.encode() not in p.read_bytes() for p in tmp_path.rglob("*") if p.is_file())


def test_completed_search_clears_cv_and_keeps_only_safe_trace_fields(client, upload, runner, tmp_path):
    store(client, make_job("a", description="SQL reports"))
    runner.answers["cv-summary"]["summary"] = MARKER
    runner.answers["check-0"] = {"grade": 2, "claims": [
        {"requirement": MARKER, "cv_quote": "SQL", "job_quote": "SQL"},
        {"requirement": MARKER, "cv_quote": MARKER, "job_quote": "not in the ad"},
        {"requirement": MARKER},
    ]}
    base, review = start(client, upload, f"Built SQL reports {MARKER}")
    assert wait_until_finished(client, base)["stage"] == "done"
    result = client.get(f"{base}/results").json()
    assert len(result["jobs"]) == 1 and result["dropped_claims"] == 2
    stored = client.app.state.requests[review["id"]]
    assert (stored.cv_text, stored.summary, stored.keywords, stored.target_role) == ("", "", [], "")
    trace = trace_for(client, review["id"])
    assert trace["outcome"] == "done"
    assert trace["elapsed_seconds"] > 0
    assert [s["name"] for s in trace["stages"]] == ["reading CV", "searching", "checking jobs"]
    [job] = trace["jobs"]
    assert (job["job_id"], job["grade"]) == ("a", 2)
    assert [c["kept"] for c in job["claims"]] == [True, False, False]
    assert job["claims"][1]["cv_quote_found"] is True
    assert job["claims"][1]["job_quote_found"] is False
    assert job["claims"][2]["reason"] == "invalid_claim"
    for submission in trace["submissions"]:
        assert submission["elapsed_seconds"] >= 0
        assert "started_at" in submission and "finished_at" in submission
    assert all(MARKER.encode() not in p.read_bytes() for p in tmp_path.rglob("*") if p.is_file())


def test_trace_lists_both_refinement_rounds_and_survives_a_new_app(client, upload, runner, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app

    store(client, make_job("a", description="SQL reports"), make_job("b", description="Tableau reports"),
          make_job("c", description="Looker reports"))
    runner.answers["refine-1"] = {"keywords": ["Tableau"]}
    runner.answers["refine-2"] = {"keywords": ["Looker"]}
    base, review = start(client, upload)
    assert wait_until_finished(client, base)["stage"] == "done"
    trace = trace_for(client, review["id"])
    assert [s["name"] for s in trace["stages"]] == [
        "reading CV", "searching", "refining round 1", "refining round 2", "checking jobs"]
    assert len(trace["submissions"]) == 4
    with TestClient(create_app(runner=FakeRunner(), data_dir=tmp_path)):
        assert trace_for(client, review["id"]) == trace
        assert latency_summary(tmp_path)["count"] == 1


def test_latency_summary_reads_many_completed_traces_excluding_pending_reviews(client, upload, tmp_path):
    for _ in range(3):
        base, _ = start(client, upload)
        assert wait_until_finished(client, base)["stage"] == "done"
    upload(text_pdf("Waiting for review"))
    values = sorted(json.loads(p.read_text())["elapsed_seconds"] for p in (tmp_path / "traces").glob("*.json")
                    if json.loads(p.read_text())["outcome"] == "done")
    summary = latency_summary(tmp_path)
    assert summary == {"count": 3, "median_seconds": values[1],
                       "p95_seconds": pytest.approx(values[1] + (values[2] - values[1]) * .9)}


def test_two_invalid_json_replies_skip_one_job_and_trace_real_retry_tokens(client, upload, runner, monkeypatch, tmp_path):
    """Use the actual standard-library client and a local HTTP Qwen stub, through the API."""
    from pathlib import Path
    from tempfile import TemporaryDirectory

    backend = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(backend / "tacc_qwen_client"))
    monkeypatch.syspath_prepend(str(backend / "tests" / "tacc_client"))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    import prompt_runner
    from stub_qwen import StubQwen, ok

    store(client, make_job("a", description="SQL reports"), make_job("b", description="SQL reports"))
    stub = StubQwen()
    seen = []

    def submit(prompts):
        for item in prompts:
            if item["id"] == "cv-summary":
                answer = {"summary": MARKER, "keywords": ["SQL"], "target_role": "Analyst"}
            elif item["id"] == "check-0":
                stub.script(item["prompt"], ok("bad JSON"), ok("still bad JSON"))
                seen.append(item["prompt"])
                continue
            else:
                answer = {"grade": 2, "claims": [{"requirement": "SQL", "cv_quote": "SQL", "job_quote": "SQL"}]}
            stub.script(item["prompt"], ok(json.dumps(answer)))
        # The two check prompts must differ for the stub to distinguish their scripts.
        with TemporaryDirectory(dir=tmp_path) as temporary:
            answers_path = Path(temporary) / "answers.json"
            prompt_runner.run(prompts, answers_path, stub.base_url)
            return json.loads(answers_path.read_text())["answers"]

    # Distinct ad text means distinct prompt text, while both remain qualifying jobs.
    with closing(db.connect(tmp_path)) as conn:
        conn.execute("UPDATE jobs SET description = 'SQL weekly reports' WHERE job_id = 'b'")
        conn.commit()
    client.app.state.runner = submit
    stub.start()
    try:
        base, review = start(client, upload, f"SQL {MARKER}")
        assert wait_until_finished(client, base)["stage"] == "done"
        result = client.get(f"{base}/results").json()
        assert len(result["jobs"]) == 1
        assert result["skipped_jobs"] == 1
        assert stub.call_count(seen[0]) == 2
        trace = trace_for(client, review["id"])
        bad, good = trace["submissions"][-1]["calls"]
        assert (bad["attempts"], bad["retries"], bad["prompt_tokens"], bad["completion_tokens"]) == (2, 1, 20, 10)
        assert bad["errors"] == ["invalid_json", "invalid_json"]
        assert good["attempts"] == 1
        assert all(MARKER.encode() not in p.read_bytes() for p in tmp_path.rglob("*") if p.is_file())
    finally:
        stub.stop()


def test_all_failed_checks_have_an_honest_explanation(client, upload, runner):
    store(client, make_job("a", description="SQL reports"))
    runner.answers["check-0"] = None
    base, _ = start(client, upload)
    assert wait_until_finished(client, base)["stage"] == "done"
    result = client.get(f"{base}/results").json()
    assert result["skipped_jobs"] == 1 and result["jobs"] == []
    assert "No jobs could be checked" in result["explanation"]
