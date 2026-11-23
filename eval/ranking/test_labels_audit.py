"""Label finalising and the claim audit, with hand-made answers. Run: python -m pytest eval/ranking -q"""
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import audit  # noqa: E402
import labels  # noqa: E402


def write_rater(path, grades):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, labels.FIELDS)
        writer.writeheader()
        for item, grade in grades.items():
            writer.writerow({"item_id": item, "cv": "x", "title": "", "employer": "", "location": "",
                             "description": "", "grade": grade})


def setup(tmp_path, first, second, resolved=None):
    key = {f"R000{i}": {"cv": "cv1", "job_id": f"job{i}", "systems": ["full"]} for i in range(1, 5)}
    (tmp_path / "key.json").write_text(json.dumps(key), encoding="utf-8")
    write_rater(tmp_path / "rater1.csv", first)
    write_rater(tmp_path / "rater2.csv", second)
    if resolved is not None:
        (tmp_path / "resolved.csv").write_text("item_id,grade\n" + "".join(f"{k},{v}\n" for k, v in resolved.items()),
                                               encoding="utf-8")


def test_agreed_jobs_keep_their_grade_and_a_talked_out_job_takes_the_agreed_grade(tmp_path):
    setup(tmp_path, {"R0001": 2, "R0002": 1, "R0003": 0, "R0004": 2}, {"R0001": 2, "R0002": 2, "R0003": 0, "R0004": 1},
          resolved={"R0002": 2, "R0004": 1})
    stats = labels.finalise(tmp_path)
    final = json.loads((tmp_path / "labels.json").read_text(encoding="utf-8"))["labels"]["cv1"]
    assert final == {"job1": 2, "job2": 2, "job3": 0, "job4": 1}
    assert stats["agreed"] == 2 and stats["disagreed"] == 2 and stats["settled_by_talking"] == 2
    assert stats["lower_grade_rule_applied"] == 0


def test_agreement_gives_kappa_and_lists_the_disagreements_without_a_resolved_file(tmp_path):
    setup(tmp_path, {"R0001": 2, "R0002": 1, "R0003": 0, "R0004": 2}, {"R0001": 2, "R0002": 2, "R0003": 0, "R0004": 1})
    result = labels.agreement(tmp_path)
    assert result["agreed"] == 2 and result["disagreed"] == 2 and result["raw_agreement"] == 0.5
    assert result["kappa_quadratic"] is not None
    rows = list(csv.DictReader((tmp_path / "disagreements.csv").open(encoding="utf-8-sig")))
    assert [(r["item_id"], r["rater1"], r["rater2"]) for r in rows] == [("R0002", "1", "2"), ("R0004", "2", "1")]
    assert not (tmp_path / "resolved.csv").exists() and not (tmp_path / "labels.json").exists()


def write_disagreements(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["item_id", "cv", "title", "rater1", "rater2", "agreed_grade_after_talking"])
        for item, r1, r2, agreed in rows:
            writer.writerow([item, "cv1", "t", r1, r2, agreed])


def test_resolve_refuses_blank_cells_because_blank_would_mean_lower_grade_by_accident(tmp_path):
    write_disagreements(tmp_path / "disagreements.csv", [("R0001", 2, 1, ""), ("R0002", 1, 0, "1")])
    with pytest.raises(ValueError, match="1 of 2 rows have no agreed grade"):
        labels.resolve(tmp_path)
    assert not (tmp_path / "resolved.csv").exists()


def test_resolve_builds_the_file_finalise_reads_and_the_word_lower_leaves_a_job_open(tmp_path):
    setup(tmp_path, {"R0001": 2, "R0002": 1, "R0003": 0, "R0004": 2}, {"R0001": 1, "R0002": 0, "R0003": 0, "R0004": 2})
    write_disagreements(tmp_path / "disagreements.csv", [("R0001", 2, 1, "2"), ("R0002", 1, 0, "lower")])
    summary = labels.resolve(tmp_path)
    assert summary == {"rows": 2, "settled": 1, "left_open_lower_grade_rule": 1, "grade_outside_both_raters": []}
    stats = labels.finalise(tmp_path)
    final = json.loads((tmp_path / "labels.json").read_text(encoding="utf-8"))["labels"]["cv1"]
    assert final["job1"] == 2 and final["job2"] == 0  # settled at 2; left open takes the lower of 1 and 0
    assert stats["settled_by_talking"] == 1 and stats["lower_grade_rule_applied"] == 1


def test_resolve_flags_a_grade_neither_rater_gave_and_rejects_junk_and_overwrites(tmp_path):
    write_disagreements(tmp_path / "disagreements.csv", [("R0001", 2, 1, "0")])
    assert labels.resolve(tmp_path)["grade_outside_both_raters"] == ["R0001"]
    with pytest.raises(ValueError, match="already exists"):
        labels.resolve(tmp_path)
    (tmp_path / "resolved.csv").unlink()
    write_disagreements(tmp_path / "disagreements.csv", [("R0001", 2, 1, "3")])
    with pytest.raises(ValueError, match="not 0, 1, 2 or 'lower'"):
        labels.resolve(tmp_path)


def test_a_disagreement_left_open_takes_the_lower_grade_and_is_counted(tmp_path):
    setup(tmp_path, {"R0001": 2, "R0002": 1, "R0003": 0, "R0004": 2}, {"R0001": 1, "R0002": 1, "R0003": 0, "R0004": 2},
          resolved={"R0001": ""})
    stats = labels.finalise(tmp_path)
    final = json.loads((tmp_path / "labels.json").read_text(encoding="utf-8"))["labels"]["cv1"]
    assert final["job1"] == 1 and stats["lower_grade_rule_applied"] == 1


def test_disagreements_with_no_resolved_file_stop_the_run(tmp_path):
    setup(tmp_path, {"R0001": 2, "R0002": 1, "R0003": 0, "R0004": 2}, {"R0001": 1, "R0002": 1, "R0003": 0, "R0004": 2})
    with pytest.raises(ValueError, match="no resolved.csv"):
        labels.finalise(tmp_path)


def test_a_blank_or_out_of_range_grade_stops_the_run(tmp_path):
    setup(tmp_path, {"R0001": 2, "R0002": "", "R0003": 0, "R0004": 2}, {"R0001": 2, "R0002": 1, "R0003": 0, "R0004": 2})
    with pytest.raises(ValueError, match="use 0, 1 or 2"):
        labels.finalise(tmp_path)


def test_a_resolution_for_a_job_the_raters_agreed_on_is_rejected(tmp_path):
    setup(tmp_path, {"R0001": 2, "R0002": 1, "R0003": 0, "R0004": 2}, {"R0001": 2, "R0002": 1, "R0003": 0, "R0004": 2},
          resolved={"R0001": 0})
    with pytest.raises(ValueError, match="was not a disagreement"):
        labels.finalise(tmp_path)


def test_the_pool_is_per_cv_and_joins_every_system_and_both_settings():
    systems = {"queries": {
        "cv1|A": {"cv": "cv1", "systems": {"full": {"top": ["a"], "pool": ["a", "b"]}, "b1": {"top": ["c"]}}},
        "cv1|B": {"cv": "cv1", "systems": {"full": {"top": ["b"], "pool": ["b", "d"]}, "b1": {"top": ["c"]}}}}}
    pools = labels.pool_by_cv(systems)
    assert set(pools["cv1"]) == {"a", "b", "c", "d"}
    assert pools["cv1"]["b"] == {"full"} and pools["cv1"]["c"] == {"b1"}


def test_the_rater_files_show_no_system_name_and_the_order_differs_between_raters(tmp_path, monkeypatch):
    import sqlite3
    db = tmp_path / "s.db"
    conn = sqlite3.connect(db)
    conn.execute("create table jobs (job_id, title, employer, location, description)")
    conn.executemany("insert into jobs values (?,?,?,?,?)", [(f"j{i}", f"T{i}", "E", "L", "D") for i in range(30)])
    conn.commit()
    conn.close()
    monkeypatch.setattr(labels, "SNAPSHOT", db)
    systems = {"queries": {"cv1|A": {"cv": "cv1", "systems": {"full": {"top": [], "pool": [f"j{i}" for i in range(30)]}}}}}
    labels.make_packs(systems, tmp_path)
    one = (tmp_path / "rater1.csv").read_text(encoding="utf-8-sig")
    two = (tmp_path / "rater2.csv").read_text(encoding="utf-8-sig")
    assert "full" not in one.lower().replace("fulltime", "") and "system" not in one.lower()
    ids_one = [r["item_id"] for r in csv.DictReader(one.splitlines())]
    ids_two = [r["item_id"] for r in csv.DictReader(two.splitlines())]
    assert sorted(ids_one) == sorted(ids_two) and ids_one != ids_two


def test_audit_counts_a_b2_quote_failure_as_unsupported_even_when_the_auditor_says_yes(tmp_path):
    key = {"C001": {"system": "full", "cv": "c", "job_id": "j", "quotes_found": True, "valid": True},
           "C002": {"system": "full", "cv": "c", "job_id": "j", "quotes_found": True, "valid": True},
           "C003": {"system": "b2", "cv": "c", "job_id": "j", "quotes_found": True, "valid": True},
           "C004": {"system": "b2", "cv": "c", "job_id": "j", "quotes_found": False, "valid": True},
           "C005": {"system": "b2", "cv": "c", "job_id": "j", "quotes_found": False, "valid": True}}
    (tmp_path / "audit-key.json").write_text(json.dumps(key), encoding="utf-8")
    with (tmp_path / "audit.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, audit.FIELDS)
        writer.writeheader()
        for cid, answer in {"C001": "yes", "C002": "no", "C003": "yes", "C004": "yes", "C005": "no"}.items():
            writer.writerow({"claim_id": cid, "supported": answer})
    totals = audit.read(tmp_path)
    counts = lambda t: {k: t[k] for k in ("audited", "unsupported", "by_quote_failure_only")}
    assert counts(totals["full"]) == {"audited": 2, "unsupported": 1, "by_quote_failure_only": 0}
    assert counts(totals["b2"]) == {"audited": 3, "unsupported": 2, "by_quote_failure_only": 1}
    assert totals["full"]["jobs"] == 1  # all five test claims share one job id


def test_generating_again_refuses_to_overwrite_files_a_person_may_have_filled(tmp_path):
    (tmp_path / "rater1.csv").write_text("item_id,grade\nR0001,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="already exist"):
        labels.make_packs({"queries": {}}, tmp_path)
    assert (tmp_path / "rater1.csv").read_text(encoding="utf-8") == "item_id,grade\nR0001,2\n"
    (tmp_path / "audit.csv").write_text("claim_id,supported\nC001,yes\n", encoding="utf-8")
    with pytest.raises(ValueError, match="already exist"):
        audit.write({"queries": {}}, tmp_path)
    assert (tmp_path / "audit.csv").read_text(encoding="utf-8") == "claim_id,supported\nC001,yes\n"


def test_is_filled_tells_an_empty_sheet_from_a_half_filled_one_from_a_done_one(tmp_path):
    assert audit.is_filled(tmp_path) is False  # no sheet at all

    def sheet(answers):
        with (tmp_path / "audit.csv").open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, audit.FIELDS)
            writer.writeheader()
            for n, answer in enumerate(answers):
                writer.writerow({"claim_id": f"C{n}", "supported": answer})

    sheet(["", "", ""])
    assert audit.is_filled(tmp_path) is False
    sheet(["yes", "", "no"])
    with pytest.raises(ValueError, match="half filled: 2 of 3"):
        audit.is_filled(tmp_path)
    sheet(["yes", "no", "yes"])
    assert audit.is_filled(tmp_path) is True


def test_the_job_clustered_interval_is_wider_when_one_job_holds_many_claims():
    spread = [[True], [False], [True], [False]] * 5          # 20 jobs, one claim each, half unsupported
    clumped = [[True, True, True, True, True], [False, False, False, False, False]] * 2   # 4 jobs, same 10/20 rate
    low_s, high_s = audit.job_clustered_interval(spread)
    low_c, high_c = audit.job_clustered_interval(clumped)
    assert low_s < 0.5 < high_s and high_c - low_c > high_s - low_s
    assert audit.job_clustered_interval(spread) == audit.job_clustered_interval(spread)  # seeded, repeatable
    assert audit.job_clustered_interval([[False]] * 6) == (0.0, 0.0)


def test_audit_rejects_an_answer_that_is_not_yes_or_no(tmp_path):
    (tmp_path / "audit-key.json").write_text(json.dumps({"C001": {"system": "full", "quotes_found": True}}), encoding="utf-8")
    (tmp_path / "audit.csv").write_text("claim_id,supported\nC001,maybe\n", encoding="utf-8")
    with pytest.raises(ValueError, match="yes or no"):
        audit.read(tmp_path)


def test_a_claim_shown_under_both_settings_is_audited_once():
    claim = {"job_id": "j", "requirement": "r", "cv_quote": "a", "job_quote": "b"}
    systems = {"queries": {"cv|A": {"cv": "cv", "systems": {"full": {"claims": [claim]}}},
                           "cv|B": {"cv": "cv", "systems": {"full": {"claims": [claim, {**claim, "requirement": "r2"}]}}}}}
    assert len(audit.distinct_claims(systems, "full")) == 2
