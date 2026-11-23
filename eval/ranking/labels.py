"""Blind rating packs for two human raters, and the final labels built from their answers.

    python eval/ranking/labels.py pack      [--out eval/out/ranking]  writes rater1.csv, rater2.csv, key.json
    python eval/ranking/labels.py agreement [--out eval/out/ranking]  kappa before talking + disagreements.csv
    python eval/ranking/labels.py resolve   [--out eval/out/ranking]  filled disagreements.csv -> resolved.csv
    python eval/ranking/labels.py finalise  [--out eval/out/ranking]  reads the filled rater files (+ resolved.csv)

Protocol (docs/AGENT_LOOP.md): each rater grades every pooled job on their own, blind to the system, by CV fit only
(0 irrelevant, 1 plausible, 2 strong). Kappa is recorded before the raters talk. They then settle only the jobs they
disagreed on; if they still disagree the job gets the lower of the two grades.

Labels ignore the preference settings, so the pool and the labels are per CV, not per query. The pool is the union of
every system's pooled jobs (top 7 for Full, Ablation A and B1; B2 gives its 5) over both settings.
"""
import argparse
import csv
import json
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

import metrics  # noqa: E402

SNAPSHOT = ROOT / "backend" / "data" / "snapshots" / "jpilot-2026-11-22.db"
FIELDS = ["item_id", "cv", "title", "employer", "location", "description", "grade"]


def pool_by_cv(systems):
    """{cv: {job_id: [system names that returned it]}}. The system names go only into the key file."""
    pools = {}
    for query in systems["queries"].values():
        for name, system in query["systems"].items():
            for job_id in system.get("pool", system["top"]):
                pools.setdefault(query["cv"], {}).setdefault(job_id, set()).add(name)
    return pools


def make_packs(systems, out, seed=0):
    existing = [n for n in ("rater1.csv", "rater2.csv", "key.json") if (out / n).exists()]
    if existing:  # a rerun would replace grades a rater may already have typed
        raise ValueError(f"{existing} already exist in {out}. Move them away first if you really want new packs.")
    pools = pool_by_cv(systems)
    db = sqlite3.connect(f"file:{SNAPSHOT}?mode=ro", uri=True)
    rng = random.Random(seed)
    items = []  # (cv, job_id, [systems])
    for cv in sorted(pools):
        for job_id in sorted(pools[cv]):
            items.append((cv, job_id, sorted(pools[cv][job_id])))
    ids = {(cv, job_id): f"R{n:04d}" for n, (cv, job_id, _) in enumerate(rng.sample(items, len(items)), 1)}
    key = {ids[(cv, job_id)]: {"cv": cv, "job_id": job_id, "systems": names} for cv, job_id, names in items}
    for rater in (1, 2):
        rows = []
        for cv in sorted(pools):
            mine = [(c, j) for c, j, _ in items if c == cv]
            rng.shuffle(mine)  # a different order for each rater, so order effects do not line up
            for _, job_id in mine:
                title, employer, location, description = db.execute(
                    "select title, employer, location, description from jobs where job_id = ?", (job_id,)).fetchone()
                rows.append({"item_id": ids[(cv, job_id)], "cv": cv, "title": title, "employer": employer,
                             "location": location, "description": description, "grade": ""})
        with (out / f"rater{rater}.csv").open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    (out / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    sizes = {cv: len(pools[cv]) for cv in sorted(pools)}
    return len(items), sizes


def _read_grades(path, key):
    grades = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["item_id"] not in key:
                raise ValueError(f"{path}: unknown item {row['item_id']}")
            if row["grade"].strip() not in {"0", "1", "2"}:
                raise ValueError(f"{path}: item {row['item_id']} has grade {row['grade']!r}; use 0, 1 or 2")
            grades[row["item_id"]] = int(row["grade"])
    missing = set(key) - set(grades)
    if missing:
        raise ValueError(f"{path}: {len(missing)} items not graded, for example {sorted(missing)[:3]}")
    return grades


def agreement(out):
    """Agreement of the two raters' own grades, and the jobs they disagreed on, before anyone talks.

    Writes disagreements.csv (item_id, both grades, cv, title) for the raters' meeting. Needs no resolved.csv."""
    key = json.loads((out / "key.json").read_text(encoding="utf-8"))
    first, second = _read_grades(out / "rater1.csv", key), _read_grades(out / "rater2.csv", key)
    order = sorted(key)
    a, b = [first[i] for i in order], [second[i] for i in order]
    disagree = [i for i in order if first[i] != second[i]]
    titles = {}
    with (out / "rater1.csv").open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            titles[row["item_id"]] = (row["cv"], row["title"])
    with (out / "disagreements.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["item_id", "cv", "title", "rater1", "rater2", "agreed_grade_after_talking"])
        for i in disagree:
            writer.writerow([i, *titles[i], first[i], second[i], ""])
    return {"items": len(order), "agreed": len(order) - len(disagree), "disagreed": len(disagree),
            "raw_agreement": (len(order) - len(disagree)) / len(order),
            "kappa_quadratic": metrics.weighted_kappa(a, b), "kappa_linear": metrics.weighted_kappa(a, b, weights="linear")}


def resolve(out):
    """Turn the filled disagreements.csv into resolved.csv. Returns the counts and any grade outside both raters'.

    A blank cell is an error, not "could not settle": blank also means "not filled in yet", and reading it as
    unsettled would silently apply the lower-grade rule to jobs the raters did settle. Write the word `lower` for a
    job they could not settle."""
    target = out / "resolved.csv"
    if target.exists():
        raise ValueError(f"{target.name} already exists. Move it away first if you really want to rebuild it.")
    with (out / "disagreements.csv").open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    blank = [r["item_id"] for r in rows if not r["agreed_grade_after_talking"].strip()]
    if blank:
        raise ValueError(f"{len(blank)} of {len(rows)} rows have no agreed grade yet, for example {blank[:3]}. "
                         "Write 0, 1 or 2, or the word 'lower' for a job the raters could not settle.")
    resolved, outside = [], []
    for r in rows:
        value = r["agreed_grade_after_talking"].strip().lower()
        if value == "lower":
            resolved.append((r["item_id"], ""))
        elif value in {"0", "1", "2"}:
            resolved.append((r["item_id"], value))
            if int(value) not in (int(r["rater1"]), int(r["rater2"])):
                outside.append(r["item_id"])
        else:
            raise ValueError(f"{r['item_id']}: {r['agreed_grade_after_talking']!r} is not 0, 1, 2 or 'lower'")
    with target.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["item_id", "grade"])
        writer.writerows(resolved)
    return {"rows": len(rows), "settled": sum(g != "" for _, g in resolved),
            "left_open_lower_grade_rule": sum(g == "" for _, g in resolved),
            "grade_outside_both_raters": outside}


def finalise(out):
    key = json.loads((out / "key.json").read_text(encoding="utf-8"))
    first, second = _read_grades(out / "rater1.csv", key), _read_grades(out / "rater2.csv", key)
    order = sorted(key)
    a, b = [first[i] for i in order], [second[i] for i in order]
    disagree = [i for i in order if first[i] != second[i]]
    resolved = {}
    path = out / "resolved.csv"
    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row["item_id"] not in disagree:
                    raise ValueError(f"resolved.csv: {row['item_id']} was not a disagreement")
                if row["grade"].strip() in {"0", "1", "2"}:
                    resolved[row["item_id"]] = int(row["grade"])
    elif disagree:
        raise ValueError(f"{len(disagree)} disagreements and no resolved.csv. Write one with columns item_id,grade "
                         "(leave grade empty for a job the raters could not settle).")
    final, lower_rule = {}, []
    for i in order:
        if first[i] == second[i]:
            final[i] = first[i]
        elif i in resolved:
            final[i] = resolved[i]
        else:
            final[i] = min(first[i], second[i])
            lower_rule.append(i)
    labels = {}
    for i, grade in final.items():
        labels.setdefault(key[i]["cv"], {})[key[i]["job_id"]] = grade
    stats = {"items": len(order), "agreed": len(order) - len(disagree), "disagreed": len(disagree),
             "settled_by_talking": len(resolved), "lower_grade_rule_applied": len(lower_rule),
             "raw_agreement": (len(order) - len(disagree)) / len(order),
             "kappa_quadratic": metrics.weighted_kappa(a, b), "kappa_linear": metrics.weighted_kappa(a, b, weights="linear"),
             "grade_counts_final": {g: sum(v == g for v in final.values()) for g in (0, 1, 2)}}
    (out / "labels.json").write_text(json.dumps({"labels": labels, "stats": stats}, indent=1), encoding="utf-8")
    return stats


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["pack", "agreement", "resolve", "finalise"])
    parser.add_argument("--out", default=str(ROOT / "eval" / "out" / "ranking"))
    args = parser.parse_args(argv)
    out = Path(args.out)
    if args.action == "pack":
        total, sizes = make_packs(json.loads((out / "systems.json").read_text(encoding="utf-8")), out)
        print(f"{total} jobs to grade per rater; per CV: {sizes}")
    elif args.action == "agreement":
        print(json.dumps(agreement(out), indent=1))
        print(f"Disagreements written to {out / 'disagreements.csv'}")
    elif args.action == "resolve":
        print(json.dumps(resolve(out), indent=1))
    else:
        print(json.dumps(finalise(out), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
