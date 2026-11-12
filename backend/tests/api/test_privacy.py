from pdfs import text_pdf

MARKER = "ZQX-MARKER-7431"


def files_holding(folder, marker):
    return [p.name for p in folder.rglob("*") if p.is_file() and marker.encode() in p.read_bytes()]


def test_cv_text_and_summary_never_reach_a_file(upload, client, runner, tmp_path):
    runner.answers["cv-summary"] = {"summary": f"Analyst, see {MARKER}.", "keywords": ["SQL"],
                                    "target_role": "Data analyst"}

    review = upload(text_pdf(f"Analyst {MARKER} at a retail bank")).json()
    client.post(f"/api/search-requests/{review['id']}/search", json=review)

    # The marker did travel through the app, and the scan did look at the database.
    assert MARKER in runner.submissions[0][0]["prompt"]
    assert MARKER in review["summary"]
    assert [p.name for p in tmp_path.rglob("*.db")] == ["jpilot.db"]
    assert files_holding(tmp_path, MARKER) == []
