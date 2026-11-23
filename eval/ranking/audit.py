"""The claim audit: a blind random sample of shown claims from Full and B2 for a human to judge.

    python eval/ranking/audit.py [--per-system 50] [--out eval/out/ranking]

Settled (docs/AGENT_LOOP.md, Q22): an unsupported claim is a shown claim that the auditor judges does not show the
requirement it cites. Full drops claims whose quotes are not found before display, so those are counted separately,
not here. B2 drops nothing, so its rate also counts the claims whose quotes are not in the source text.

The sheet has no system name. The auditor writes yes or no in `supported`. The unit is a distinct claim: the same
claim shown under both preference settings is audited once.
"""
import argparse
import csv
import json
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "backend" / "data" / "snapshots" / "jpilot-2026-11-22.db"
FIELDS = ["claim_id", "cv", "job_title", "requirement", "cv_quote", "job_quote", "job_description", "supported", "note"]


def distinct_claims(systems, name):
    seen = {}
    for query in systems["queries"].values():
        for claim in query["systems"][name].get("claims", []):
            key = (query["cv"], claim["job_id"], claim["requirement"], claim["cv_quote"], claim["job_quote"])
            seen.setdefault(key, {**claim, "cv": query["cv"], "system": name})
    return list(seen.values())


def sample(systems, per_system=50, seed=0):
    rng = random.Random(seed)
    chosen = []
    for name in ("full", "b2"):
        pool = distinct_claims(systems, name)
        chosen += rng.sample(pool, min(per_system, len(pool)))
    rng.shuffle(chosen)
    return chosen


def write(systems, out, per_system=50, seed=0):
    existing = [n for n in ("audit.csv", "audit-key.json") if (out / n).exists()]
    if existing:  # a rerun would replace judgements the auditor may already have typed
        raise ValueError(f"{existing} already exist in {out}. Move them away first if you really want a new sample.")
    claims = sample(systems, per_system, seed)
    db = sqlite3.connect(f"file:{SNAPSHOT}?mode=ro", uri=True)
    key, rows = {}, []
    for n, claim in enumerate(claims, 1):
        claim_id = f"C{n:03d}"
        title, description = db.execute("select title, description from jobs where job_id = ?", (claim["job_id"],)).fetchone()
        key[claim_id] = {"system": claim["system"], "cv": claim["cv"], "job_id": claim["job_id"],
                         "quotes_found": bool(claim.get("cv_found", True) and claim.get("job_found", True)),
                         "valid": claim.get("valid", True)}
        rows.append({"claim_id": claim_id, "cv": claim["cv"], "job_title": title, "requirement": claim["requirement"],
                     "cv_quote": claim["cv_quote"], "job_quote": claim["job_quote"], "job_description": description,
                     "supported": "", "note": ""})
    with (out / "audit.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (out / "audit-key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    return {name: sum(v["system"] == name for v in key.values()) for name in ("full", "b2")}


def is_filled(out):
    """False when there is no sheet or nobody has judged a claim yet; True when it is filled. A half-filled sheet
    raises, because reporting a rate from part of the sample would quietly change which claims were audited."""
    path = out / "audit.csv"
    if not path.exists():
        return False
    with path.open(newline="", encoding="utf-8-sig") as f:
        answers = [row["supported"].strip() for row in csv.DictReader(f)]
    done = sum(a != "" for a in answers)
    if done == 0:
        return False
    if done < len(answers):
        raise ValueError(f"audit.csv is half filled: {done} of {len(answers)} claims judged. Finish it, or move it away.")
    return True


def read(out):
    """Per system: audited claims, unsupported claims, and of those how many B2 quote failures were counted."""
    key = json.loads((out / "audit-key.json").read_text(encoding="utf-8"))
    judged = {}
    with (out / "audit.csv").open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["supported"].strip().lower() not in {"yes", "no"}:
                raise ValueError(f"claim {row['claim_id']}: write yes or no in `supported`, not {row['supported']!r}")
            judged[row["claim_id"]] = row["supported"].strip().lower() == "yes"
    if set(judged) != set(key):
        raise ValueError("audit.csv and audit-key.json do not list the same claims")
    totals, by_job = {}, {}
    for claim_id, info in key.items():
        row = totals.setdefault(info["system"], {"audited": 0, "unsupported": 0, "by_quote_failure_only": 0})
        row["audited"] += 1
        failed_quote = info["system"] == "b2" and not info["quotes_found"]
        unsupported = not judged[claim_id] or failed_quote
        row["unsupported"] += unsupported
        row["by_quote_failure_only"] += bool(judged[claim_id]) and failed_quote
        by_job.setdefault(info["system"], {}).setdefault(info["job_id"], []).append(unsupported)
    for system, row in totals.items():
        row["jobs"] = len(by_job[system])
        row["job_clustered_interval"] = job_clustered_interval(list(by_job[system].values()))
    return totals


def job_clustered_interval(groups, resamples=10_000, seed=0):
    """95% bootstrap interval of the unsupported rate, resampling whole jobs. Claims from one job share an ad and a
    CV, so they are not independent, and a plain Wilson interval is too narrow. (low, high)."""
    import random
    rng = random.Random(seed)
    rates = []
    for _ in range(resamples):
        picked = [groups[rng.randrange(len(groups))] for _ in groups]
        flat = [x for group in picked for x in group]
        rates.append(sum(flat) / len(flat))
    rates.sort()
    return rates[int(resamples * 0.025)], rates[int(resamples * 0.975) - 1]


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--per-system", type=int, default=50)
    parser.add_argument("--out", default=str(ROOT / "eval" / "out" / "ranking"))
    args = parser.parse_args(argv)
    out = Path(args.out)
    counts = write(json.loads((out / "systems.json").read_text(encoding="utf-8")), out, args.per_system)
    print(f"audit.csv written: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
