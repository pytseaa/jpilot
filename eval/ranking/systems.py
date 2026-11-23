"""Run the four systems on the 8 CVs x 2 settings and save each system's top 5.

    python eval/ranking/systems.py [--fake] [--out eval/out/ranking]

Systems (docs/AGENT_LOOP.md, Evaluation):
    full  the app: summary, keywords, widening, per-job checks, ranking with the soft preferences
    abl_a the app with widening switched off (Ablation A)
    b1    BM25 over the same hard filters, the same keywords, no soft preferences
    b2    one Qwen call over the top-20 pool (see b2.py), no soft preferences

Everything runs through the app's own functions on a copy of the frozen snapshot. Answers are cached on disk, so
a service that ends mid-run costs only the unfinished part: start a new service, update server-url.txt, run again.
It refuses to run unless settings.json says "approved".
"""
import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(Path(__file__).parent)]

import b2  # noqa: E402
from qwen import CachedRunner, Collector  # noqa: E402

from app import prompts  # noqa: E402
from app.runners.tacc import TaccRunner  # noqa: E402
from app.services import checking, cv_intake, refinement, retrieval  # noqa: E402

SNAPSHOT = ROOT / "backend" / "data" / "snapshots" / "jpilot-2026-11-22.db"
SETTINGS = Path(__file__).parent / "settings.json"
CVS = ROOT / "eval" / "cvs"


def load_settings():
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    if settings["status"] != "approved":
        raise SystemExit(f"settings.json is '{settings['status']}'. The plan fixes the preference settings before any "
                         "system runs: have the team read them, then set \"status\" to \"approved\".")
    return settings


def stage_cv_summary(runner, cvs):
    """Stage 1: one summary call per CV. Returns {cv: (cv_text, answer)}."""
    out = {}
    for name, text in cvs.items():
        out[name] = (text, cv_intake.summarise(text, runner, propose_target_role=True))
    return out


def prefetch(real, run_stage):
    """Run a stage once with a Collector to learn its prompts, send them in batches, return nothing: the real
    call then finds every answer in the cache."""
    collector = Collector(dummy=lambda p: {"grade": 0, "claims": [], "unmet_requirements": [], "keywords": [],
                                           "summary": "x", "target_role": "x", "top": []})
    run_stage(collector)
    if collector.prompts:
        real(collector.prompts)


def run(real, out_dir, settings):
    snapshot_dir = Path(tempfile.mkdtemp(prefix="jpilot-eval-"))
    shutil.copyfile(SNAPSHOT, snapshot_dir / "jpilot.db")
    cvs = {p.stem: cv_intake.extract_text(p.read_bytes()) for p in sorted(CVS.glob("*.pdf"))}
    employment = settings["employment_types"]
    results = {"employment_types": employment, "snapshot": SNAPSHOT.name, "queries": {}}

    # Stage 1: CV summaries. The summary does not depend on the setting, so each CV is summarised once.
    prefetch(real, lambda r: stage_cv_summary(r, cvs))
    summaries = stage_cv_summary(real, cvs)

    with closing(sqlite3.connect(snapshot_dir / "jpilot.db")) as conn:
        conn.row_factory = sqlite3.Row
        plans = {}
        for name, (text, answer) in summaries.items():
            keywords, role, summary = answer.keywords, answer.target_role, answer.summary
            # Full: widen until enough jobs qualify. Ablation A: the first qualifying list only.
            first = retrieval.find_qualifying(conn, keywords, employment)
            widened = []

            def widen_stage(runner, keywords=keywords, summary=summary, role=role, widened=widened):
                widened[:] = refinement.widen(conn, keywords, summary, role, employment, runner, lambda n: None)

            prefetch(real, widen_stage)
            widen_stage(real)
            plans[name] = {"text": text, "summary": summary, "keywords": keywords, "role": role,
                           "first": first, "widened": list(widened)}

        # Stage 2: every distinct (CV, job) check, once, whatever system and setting needs it.
        def checks_stage(runner):
            for name, plan in plans.items():
                seen = {}
                for job in plan["widened"] + plan["first"]:
                    seen.setdefault(job["job_id"], job)
                plan["all_checks"] = list(seen.values())
                checking.check_jobs(list(seen.values()), plan["text"], plan["summary"], runner, None, None)

        prefetch(real, checks_stage)
        checks_stage(real)

        # Stage 3: B2, one call per CV over its top-20 pool.
        b2_items = {}
        for name, plan in plans.items():
            item, tokens = b2.build(plan["text"], plan["first"])
            b2_items[name] = (item, tokens)
        too_long = {n: round(t) for n, (_, t) in b2_items.items() if t > b2.MAX_INPUT_TOKENS}
        if too_long:
            raise SystemExit(f"B2 input would not fit the context: {too_long} estimated tokens "
                             f"(limit {b2.MAX_INPUT_TOKENS}). Shorten the pool and say so in the report.")
        real([item for item, _ in b2_items.values()])

        for name, plan in plans.items():
            for label in ("A", "B"):
                prefs = settings["cvs"][name][label]
                band, industry = prefs["experience_band"], prefs["industry"]
                qid = f"{name}|{label}"
                results["queries"][qid] = {
                    "cv": name, "setting": label, "preferences": prefs,
                    "pool_size": len(plan["first"]), "widened_size": len(plan["widened"]),
                    "passing_filters": retrieval.count_passing(conn, employment),
                    "systems": {
                        "full": _app_system(real, plan, plan["widened"], band, industry),
                        "abl_a": _app_system(real, plan, plan["first"], band, industry),
                        "b1": {"top": [j["job_id"] for j in plan["first"][:5]],
                               "pool": [j["job_id"] for j in plan["first"][:POOL_DEPTH]]},
                        "b2": _b2_system(real, plan, b2_items[name][0]),
                    }}
    if real.unresolved:
        raise SystemExit(f"{len(real.unresolved)} calls failed for service or network reasons, so some jobs were skipped. "
                         "Nothing was written. Check the service and run again: every finished answer is kept.")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "systems.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    (out_dir / "usage.json").write_text(json.dumps(real.usage(), indent=1), encoding="utf-8")
    return results


POOL_DEPTH = 7  # the plan pools the top 7 of every system; nDCG@5 and P@5 use the first 5


def _app_system(real, plan, jobs, band, industry):
    """The app's own checking and ranking. The calls were prefetched, so this reads the cache.

    The app shows 5 jobs (checking.SHORTLIST_SIZE). The evaluation widens that to 7 only so the labelling pool is
    deep enough; the order is the app's own ranking, so the first 5 are exactly what the app would show."""
    rows = {}
    original = checking.SHORTLIST_SIZE
    checking.SHORTLIST_SIZE = POOL_DEPTH
    try:
        shortlist, dropped, skipped = checking.check_jobs(jobs, plan["text"], plan["summary"], real, band, industry,
                                                          trace=_Rows(rows))
    finally:
        checking.SHORTLIST_SIZE = original
    shown = shortlist[:5]
    return {"top": [j["job_id"] for j in shown], "pool": [j["job_id"] for j in shortlist], "claims": [
        {"job_id": j["job_id"], "requirement": c["requirement"], "cv_quote": c["cv_quote"], "job_quote": c["job_quote"]}
        for j in shown for c in j["claims"]], "dropped_claims": dropped, "skipped_jobs": skipped,
        "grades_by_job": rows}


class _Rows:
    """Receives checking's per-job trace calls so the grades survive for the report."""

    def __init__(self, rows):
        self.rows = rows

    def job(self, job_id, grade, claims, failure=None):
        self.rows[job_id] = {"grade": grade, "failure": failure}


def _b2_system(real, plan, item):
    record = real([item])["b2"]
    if record["status"] != "ok":
        return {"top": [], "claims": [], "failed": record.get("error_type", "failed")}
    ranked, claims, ignored = b2.parse(record["answer"], plan["text"], plan["first"])
    # B2 is asked for 5 (settled design), so it adds 5 to the labelling pool where the others add 7.
    return {"top": ranked, "pool": ranked, "claims": claims, "ignored_entries": ignored}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fake", action="store_true", help="use the offline stand-in; numbers mean nothing")
    parser.add_argument("--out", default=str(ROOT / "eval" / "out" / "ranking"))
    args = parser.parse_args(argv)
    settings = load_settings() if not args.fake else json.loads(SETTINGS.read_text(encoding="utf-8"))
    out = Path(args.out)
    if args.fake:
        from fakeqwen import FakeQwen
        real = CachedRunner(FakeQwen(), out / "cache-fake.json")
    else:
        real = CachedRunner(TaccRunner(), out / "cache.json")
    results = run(real, out, settings)
    print(f"{len(results['queries'])} queries, {real.submissions} TACC submissions this run, "
          f"{len(real.cache)} distinct answers cached")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
