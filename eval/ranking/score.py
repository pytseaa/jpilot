"""Turn systems.json + labels.json (+ audit) into the evaluation tables.

    python eval/ranking/score.py [--out eval/out/ranking]

Writes <out>/results.md and <out>/results.json. Nothing here invents a label: it stops if a job in a top 5 has none.
"""
import argparse
import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

import audit  # noqa: E402
import metrics  # noqa: E402

SNAPSHOT = ROOT / "backend" / "data" / "snapshots" / "jpilot-2026-11-22.db"
SYSTEMS = [("full", "Full system"), ("abl_a", "Ablation A (no refinement)"), ("b1", "B1 keyword (BM25)"), ("b2", "B2 single pass")]
BAND_RANGE = {"0-2": (0, 2), "3-5": (3, 5), "6-9": (6, 9), "10+": (10, 10 ** 6)}


def hard_violations(systems, snapshot, snapshot_date):
    """Jobs in any top 5 that break a hard filter, checked against the stored fields.

    Region 'other' and a job older than 30 days at the snapshot date are violations; a job whose region or type is
    unknown is kept by design and counted separately as Unverified, not as a violation."""
    db = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    oldest = (snapshot_date - timedelta(days=30)).isoformat()
    shown = violations = unverified = 0
    for query in systems["queries"].values():
        picked = set(query_employment(systems))
        for name, system in query["systems"].items():
            for job_id in system["top"]:
                row = db.execute("select * from jobs where job_id = ?", (job_id,)).fetchone()
                shown += 1
                types = set(json.loads(row["employment_types"]))
                bad = (row["region"] == "other" or row["collected"] < oldest or (types and not types & picked))
                violations += bool(bad)
                unverified += bool(row["unverified"])
    return {"shown": shown, "violations": violations, "unverified_shown": unverified}


def query_employment(systems):
    return systems["employment_types"]


def per_query_scores(systems, labels, gain="linear"):
    """{(query id, system): (ndcg@5, p@5)}; nDCG's ideal ranking comes from the CV's whole labelled pool."""
    scores = {}
    for qid, query in systems["queries"].items():
        pool = labels[query["cv"]]
        for name, _ in SYSTEMS:
            top = query["systems"][name]["top"]
            scores[(qid, name)] = (metrics.ndcg_at_k(top, pool, set(pool), 5, gain), metrics.precision_at_k(top, pool, 5))
    return scores


def table(systems, labels, gain="linear"):
    scores = per_query_scores(systems, labels, gain)
    rows = {}
    for name, title in SYSTEMS:
        values = [(q, scores[(q, name)]) for q in systems["queries"]]
        rows[name] = {"title": title, "ndcg": [v[0] for _, v in values if v[0] is not None],
                      "p5": [v[1] for _, v in values],
                      "undefined_ndcg": sum(v[0] is None for _, v in values)}
    return rows, scores


def paired(systems, scores, left, right):
    """Per-query nDCG@5 differences left - right with a CV-clustered bootstrap, skipping queries undefined for either."""
    diffs, clusters = [], []
    for qid, query in systems["queries"].items():
        a, b = scores[(qid, left)][0], scores[(qid, right)][0]
        if a is not None and b is not None:
            diffs.append(a - b)
            clusters.append(query["cv"])
    if not diffs:
        return None
    return metrics.paired_bootstrap(diffs, clusters=clusters) + (len(diffs),)


def preference_effect(systems):
    """How many CVs return a different top 5 under A and B (a different set, and a different order)."""
    cvs = sorted({q["cv"] for q in systems["queries"].values()})
    out = {}
    for name in ("full", "abl_a"):
        diff_set = diff_order = 0
        for cv in cvs:
            a = systems["queries"][f"{cv}|A"]["systems"][name]["top"]
            b = systems["queries"][f"{cv}|B"]["systems"][name]["top"]
            diff_set += set(a) != set(b)
            diff_order += a != b
        out[name] = {"cvs": len(cvs), "different_set": diff_set, "different_order": diff_order}
    return out


def preference_fit(systems):
    """For the Full system: how many of its top 5 meet the experience band and the industry, under each setting."""
    db = sqlite3.connect(f"file:{SNAPSHOT}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    out = {"A": [0, 0, 0], "B": [0, 0, 0]}  # band met, industry met, shown
    for query in systems["queries"].values():
        low, high = BAND_RANGE[query["preferences"]["experience_band"]]
        for job_id in query["systems"]["full"]["top"]:
            row = db.execute("select minimum_years, industry from jobs where job_id = ?", (job_id,)).fetchone()
            out[query["setting"]][2] += 1
            out[query["setting"]][0] += row["minimum_years"] is None or low <= row["minimum_years"] <= high
            out[query["setting"]][1] += row["industry"] in (query["preferences"]["industry"], "unknown")
    return out


def fmt(value, places=3):
    return "n/a" if value is None else f"{value:.{places}f}"


def render(systems, labels_doc, audit_totals, snapshot_date):
    labels = labels_doc["labels"]
    rows, scores = table(systems, labels)
    exp_rows, _ = table(systems, labels, gain="exponential")
    lines = ["# Ranking evaluation results", "",
             f"Snapshot {SNAPSHOT.name}, hard filters: employment type {systems['employment_types']}, region Hong Kong.",
             f"Queries: {len(systems['queries'])} (8 CVs x settings A and B). Grades: final labels after the raters "
             "talked (lower grade on a standing disagreement).", "",
             "## nDCG@5 and Precision@5 (mean over queries)", "",
             "| System | nDCG@5 (linear gain) | nDCG@5 (2^g-1 gain) | Precision@5 | Queries with undefined nDCG |",
             "|---|---|---|---|---|"]
    for name, title in SYSTEMS:
        r, e = rows[name], exp_rows[name]
        mean = lambda v: fmt(sum(v) / len(v)) if v else "n/a"
        lines.append(f"| {title} | {mean(r['ndcg'])} | {mean(e['ndcg'])} | {mean(r['p5'])} | {r['undefined_ndcg']} |")
    lines += ["", "nDCG@5 uses the grade itself as gain (0, 1, 2); the second column is a sensitivity check. The ideal "
              "ranking is the best 5 jobs of the CV's whole labelled pool, so the value is relative to what any system "
              "returned. Settings A and B of one CV share most of their jobs, so intervals resample CVs, not queries.", "",
              "## Paired differences in nDCG@5 (bootstrap 95% interval, 10,000 resamples of CVs)", "",
              "| Comparison | Mean difference | 95% interval | Queries used |", "|---|---|---|---|"]
    stronger = max(("b1", "b2"), key=lambda n: sum(rows[n]["ndcg"]) / max(len(rows[n]["ndcg"]), 1))
    for right in ("b1", "b2", "abl_a"):
        result = paired(systems, scores, "full", right)
        label = f"{dict(SYSTEMS)['full']} - {dict(SYSTEMS)[right]}" + (" (stronger baseline)" if right == stronger else "")
        lines.append(f"| {label} | " + (f"{result[0]:+.3f} | [{result[1]:+.3f}, {result[2]:+.3f}] | {result[3]} |" if result else "n/a | n/a | 0 |"))
    lines += ["", "Target from the proposal: +0.05 nDCG@5 over the stronger baseline. Reported with its interval "
              "whether or not it is met.", ""]
    effect = preference_effect(systems)
    lines += ["## Do the two preference settings change the top 5?", "",
              "| System | CVs | Different set of 5 jobs | Different set or order |", "|---|---|---|---|"]
    for name, e in effect.items():
        lines.append(f"| {dict(SYSTEMS)[name]} | {e['cvs']} | {e['different_set']} | {e['different_order']} |")
    pref = preference_fit(systems)
    lines += ["", "Full system, share of the top 5 that meets the preference (unknown counts as met): "
              + "; ".join(f"setting {s}: band {v[0]}/{v[2]}, industry {v[1]}/{v[2]}" for s, v in pref.items()), ""]
    hv = hard_violations(systems, SNAPSHOT, snapshot_date)
    lines += ["## Hard constraints", "",
              f"{hv['violations']} violations in {hv['shown']} shown jobs across all systems (region 'other', older than "
              f"30 days at the snapshot date, or an employment type that excludes the picked one). "
              f"{hv['unverified_shown']} shown jobs are Unverified (a field is unknown); the design keeps and flags them, "
              "so they are not counted as violations. B1, B2 and the Full system all pass through the same code filters.", ""]
    if audit_totals:
        lines += ["## Unsupported claims (human audit)", "",
                  "| System | Audited | From jobs | Unsupported | Rate | Wilson 95% | Job-clustered 95% |", "|---|---|---|---|---|---|---|"]
        for name in ("full", "b2"):
            t = audit_totals.get(name)
            if t:
                w = metrics.wilson_interval(t["unsupported"], t["audited"])
                c = t["job_clustered_interval"]
                lines.append(f"| {dict(SYSTEMS)[name]} | {t['audited']} | {t['jobs']} | {t['unsupported']} | {w[0]:.1%} | "
                             f"[{w[1]:.1%}, {w[2]:.1%}] | [{c[0]:.1%}, {c[1]:.1%}] |")
        lines += ["", "B2's count includes claims whose quote is not in the source text, because B2 drops none "
                  f"({sum(t['by_quote_failure_only'] for t in [audit_totals.get('b2', {'by_quote_failure_only': 0})])} such claims "
                  "were judged supported by the auditor and counted unsupported anyway). Full drops claims with a missing quote "
                  "before display, so those are counted below, not here. Claims from one job share an ad, so the job-clustered "
                  "interval is the one to quote.", ""]
    # Settings A and B share every check, so a CV's dropped claims are counted once, not once per setting.
    per_cv = {q["cv"]: q["systems"]["full"].get("dropped_claims", 0) for q in systems["queries"].values()}
    lines += [f"Claims the Full system dropped for a missing quote, counted once per CV over {len(per_cv)} CVs: "
              f"{sum(per_cv.values())}.", ""]
    stats = labels_doc["stats"]
    lines += ["## Rater agreement", "",
              f"Jobs graded: {stats['items']}. Agreed: {stats['agreed']} ({stats['raw_agreement']:.1%}). "
              f"Weighted Cohen's kappa, quadratic weights: {fmt(stats['kappa_quadratic'])}, linear weights: {fmt(stats['kappa_linear'])}, "
              f"both before the raters talked. Disagreements settled by talking: {stats['settled_by_talking']}. "
              f"Lower-grade rule applied: {stats['lower_grade_rule_applied']}. Final grades 0/1/2: "
              f"{stats['grade_counts_final']['0']}/{stats['grade_counts_final']['1']}/{stats['grade_counts_final']['2']}.", ""]
    return "\n".join(lines), {"nDCG": {n: rows[n]["ndcg"] for n in rows}, "hard": hv}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "eval" / "out" / "ranking"))
    parser.add_argument("--snapshot-date", default="2026-11-22")
    args = parser.parse_args(argv)
    out = Path(args.out)
    systems = json.loads((out / "systems.json").read_text(encoding="utf-8"))
    labels_doc = json.loads((out / "labels.json").read_text(encoding="utf-8"))
    totals = audit.read(out) if audit.is_filled(out) else None
    text, data = render(systems, labels_doc, totals, date.fromisoformat(args.snapshot_date))
    (out / "results.md").write_text(text + "\n", encoding="utf-8")
    (out / "results.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
