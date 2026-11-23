"""score.py on small hand-made inputs. Run: python -m pytest eval/ranking -q"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import score  # noqa: E402


def make_systems(tops):
    """tops: {(cv, setting): {system: [job ids]}} -> the structure systems.json has."""
    return {"employment_types": ["full-time"], "queries": {
        f"{cv}|{s}": {"cv": cv, "setting": s, "preferences": {"experience_band": "0-2", "industry": "other"},
                      "systems": {name: {"top": top} for name, top in systems.items()}}
        for (cv, s), systems in tops.items()}}


FOUR = lambda full, b1: {"full": full, "abl_a": full, "b1": b1, "b2": b1}


def test_nDCG_is_per_query_and_uses_the_cvs_whole_labelled_pool():
    systems = make_systems({("c", "A"): FOUR(["a", "b"], ["c", "d"]), ("c", "B"): FOUR(["a", "b"], ["c", "d"])})
    labels = {"c": {"a": 2, "b": 1, "c": 0, "d": 0}}
    rows, scores = score.table(systems, labels)
    assert scores[("c|A", "full")][0] == pytest.approx(1.0)
    assert scores[("c|A", "b1")][0] == 0
    assert rows["full"]["p5"] == [pytest.approx(2 / 5)] * 2


def test_a_job_with_no_label_stops_scoring_instead_of_counting_as_zero():
    systems = make_systems({("c", "A"): FOUR(["a", "zz"], ["a", "b"]), ("c", "B"): FOUR(["a", "b"], ["a", "b"])})
    with pytest.raises(KeyError, match="not in the pool"):
        score.table(systems, {"c": {"a": 2, "b": 1}})


def test_a_cv_with_every_job_graded_0_has_undefined_ndcg_and_is_skipped_in_the_difference():
    systems = make_systems({("c1", "A"): FOUR(["a"], ["b"]), ("c1", "B"): FOUR(["a"], ["b"]),
                            ("c2", "A"): FOUR(["x"], ["y"]), ("c2", "B"): FOUR(["x"], ["y"])})
    labels = {"c1": {"a": 2, "b": 0}, "c2": {"x": 0, "y": 0}}
    rows, scores = score.table(systems, labels)
    assert rows["full"]["undefined_ndcg"] == 2
    mean, low, high, used = score.paired(systems, scores, "full", "b1")
    assert used == 2 and mean == pytest.approx(1.0)


def test_preference_effect_counts_a_cv_only_when_its_top_five_differs():
    systems = make_systems({("c1", "A"): FOUR(["a", "b"], ["x"]), ("c1", "B"): FOUR(["b", "a"], ["x"]),
                            ("c2", "A"): FOUR(["a", "b"], ["x"]), ("c2", "B"): FOUR(["a", "c"], ["x"]),
                            ("c3", "A"): FOUR(["a", "b"], ["x"]), ("c3", "B"): FOUR(["a", "b"], ["x"])})
    full = score.preference_effect(systems)["full"]
    assert full == {"cvs": 3, "different_set": 1, "different_order": 2}


def test_hard_violations_count_region_other_old_jobs_and_wrong_type_but_not_unknowns(tmp_path):
    import json
    import sqlite3
    from datetime import date, timedelta
    db = tmp_path / "s.db"
    conn = sqlite3.connect(db)
    conn.execute("create table jobs (job_id, region, collected, employment_types, unverified)")
    today = date(2026, 11, 22)
    rows = [("ok", "Hong Kong", today.isoformat(), json.dumps(["full-time"]), 0),
            ("elsewhere", "other", today.isoformat(), json.dumps(["full-time"]), 0),
            ("old", "Hong Kong", (today - timedelta(days=31)).isoformat(), json.dumps(["full-time"]), 0),
            ("wrongtype", "Hong Kong", today.isoformat(), json.dumps(["contractor"]), 0),
            ("unknown", "unknown", today.isoformat(), json.dumps([]), 1)]
    conn.executemany("insert into jobs values (?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    systems = {"employment_types": ["full-time"], "queries": {"c|A": {"systems": {"full": {"top": [r[0] for r in rows]}}}}}
    result = score.hard_violations(systems, db, today)
    assert result == {"shown": 5, "violations": 3, "unverified_shown": 1}
