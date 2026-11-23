"""The evaluation pipeline, run offline with the fake runner. Run: python -m pytest eval/ranking -q (from the repo root)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(Path(__file__).parent)]

import b2  # noqa: E402
import systems  # noqa: E402
from fakeqwen import FakeQwen  # noqa: E402
from qwen import CachedRunner, Collector, key_of  # noqa: E402

from app.services import checking  # noqa: E402


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    if not systems.SNAPSHOT.exists():
        pytest.skip(f"needs the job snapshot {systems.SNAPSHOT.name}; run ingestion with --snapshot first (see README)")
    out = tmp_path_factory.mktemp("rank")
    settings = json.loads(systems.SETTINGS.read_text(encoding="utf-8"))
    return systems.run(CachedRunner(FakeQwen(), out / "cache.json"), out, settings), out


def test_every_query_has_all_four_systems_with_five_distinct_jobs(results):
    data, _ = results
    assert len(data["queries"]) == 16
    for query in data["queries"].values():
        assert set(query["systems"]) == {"full", "abl_a", "b1", "b2"}
        for system in query["systems"].values():
            assert len(system["top"]) == len(set(system["top"])) == 5


def test_the_app_shortlist_size_is_restored_after_a_run(results):
    assert checking.SHORTLIST_SIZE == 5


def test_the_first_five_of_the_seven_deep_pool_are_what_the_app_would_show(results):
    data, _ = results
    query = data["queries"]["e2-customer-admin-experienced|A"]["systems"]["full"]
    assert query["pool"][:5] == query["top"] and len(query["pool"]) == 7


def test_both_settings_share_every_grade_and_only_the_cut_and_order_may_differ(results):
    # Preferences only break ties between equal-grade jobs, so the top 7 can differ between A and B,
    # but a job that was checked under both gets the same grade, and the baselines ignore preferences.
    data, _ = results
    for cv in {q["cv"] for q in data["queries"].values()}:
        a, b = data["queries"][f"{cv}|A"]["systems"], data["queries"][f"{cv}|B"]["systems"]
        shared = set(a["full"]["grades_by_job"]) & set(b["full"]["grades_by_job"])
        assert shared and all(a["full"]["grades_by_job"][j] == b["full"]["grades_by_job"][j] for j in shared)
        assert a["b1"]["top"] == b["b1"]["top"] and a["b2"]["top"] == b["b2"]["top"]


def test_b1_is_the_top_of_the_keyword_ordered_pool(results):
    data, _ = results
    for query in data["queries"].values():
        assert query["pool_size"] == 20 and len(query["systems"]["b1"]["pool"]) == 7


def test_a_second_run_sends_nothing_because_every_answer_is_cached(results):
    _, out = results
    fake = FakeQwen()
    settings = json.loads(systems.SETTINGS.read_text(encoding="utf-8"))
    runner = CachedRunner(fake, out / "cache.json")
    systems.run(runner, out, settings)
    assert fake.submissions == 0


def test_the_runner_refuses_unapproved_settings(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"status": "draft"}), encoding="utf-8")
    monkeypatch.setattr(systems, "SETTINGS", path)
    with pytest.raises(SystemExit, match="draft"):
        systems.load_settings()


def test_a_service_failure_is_not_cached_but_a_model_failure_is(tmp_path):
    class Flaky:
        def __call__(self, prompts):
            return {p["id"]: {"status": "failed", "error_type": p["prompt"], "attempts": 1} for p in prompts}

    runner = CachedRunner(Flaky(), tmp_path / "c.json")
    runner([{"id": "check-0", "prompt": "unreachable"}, {"id": "check-1", "prompt": "invalid_json"}])
    kept = [e["record"]["error_type"] for e in runner.cache.values()]
    assert kept == ["invalid_json"]


def test_a_prompt_that_failed_for_a_service_reason_stays_unresolved_until_a_retry_succeeds(tmp_path):
    class FailsOnce:
        calls = 0

        def __call__(self, prompts):
            self.calls += 1
            bad = {"status": "failed", "error_type": "unreachable", "attempts": 1}
            good = {"status": "ok", "answer": {}, "attempts": 1}
            return {p["id"]: bad if self.calls == 1 else good for p in prompts}

    runner = CachedRunner(FailsOnce(), tmp_path / "c.json")
    item = {"id": "check-0", "prompt": "p"}
    runner([item])
    assert len(runner.unresolved) == 1
    runner([item])
    assert runner.unresolved == set()


def test_the_collector_sends_nothing_and_keeps_the_prompts():
    collector = Collector(dummy=lambda p: {"keywords": []})
    collector([{"id": "refine-1", "prompt": "x"}])
    assert [p["prompt"] for p in collector.prompts] == ["x"]


def test_b2_parse_checks_quotes_and_ignores_bad_ad_numbers():
    jobs = [{"job_id": "j1", "description": "alpha beta gamma delta"}, {"job_id": "j2", "description": "one two three"},
            {"job_id": "j3", "description": "red green blue"}]
    answer = {"top": [{"job": 2, "claims": [{"requirement": "r", "cv_quote": "skill", "job_quote": "two three"}]},
                      {"job": 9, "claims": []},      # no such ad: ignored
                      {"job": 2, "claims": []},      # a repeat: ignored, and so are its claims
                      {"job": "1", "claims": [{"requirement": "r", "cv_quote": "skill", "job_quote": "not there"}]},
                      {"job": 3, "claims": [{"cv_quote": "x"}]}]}   # a claim with fields missing
    ranked, claims, ignored = b2.parse(answer, "some skill here", jobs)
    assert ranked == ["j2", "j1", "j3"] and ignored == 2
    assert [(c["cv_found"], c["job_found"], c["valid"]) for c in claims] == [
        (True, True, True), (True, False, True), (False, False, False)]


def test_b2_build_estimates_size_from_measured_characters_per_token():
    item, tokens = b2.build("cv", [{"description": "x" * 4430}])
    assert item["max_tokens"] == b2.REPLY_TOKENS
    assert tokens == pytest.approx(len(item["prompt"]) / b2.CHARS_PER_TOKEN)
    assert tokens > 4430 / b2.CHARS_PER_TOKEN  # the template and the CV are counted too


def test_the_prompt_key_ignores_the_id_so_equal_prompts_share_an_answer():
    assert key_of({"id": "check-3", "prompt": "p"}) == key_of({"id": "check-9", "prompt": "p"})
