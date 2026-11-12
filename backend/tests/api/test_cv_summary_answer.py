from pdfs import text_pdf

CV = text_pdf("Analyst at a retail bank")
GOOD = {"summary": "Analyst.", "keywords": ["SQL"], "target_role": "Data analyst"}


def test_a_missing_target_role_fails_when_qwen_was_asked_for_one(upload, runner):
    runner.answers["cv-summary"] = {"summary": "Analyst.", "keywords": ["SQL"]}

    response = upload(CV)

    assert response.status_code == 502
    assert "CV summary" in response.json()["detail"]


def test_a_blank_target_role_fails_when_qwen_was_asked_for_one(upload, runner):
    runner.answers["cv-summary"] = {**GOOD, "target_role": "   "}

    assert upload(CV).status_code == 502


def test_a_missing_target_role_is_fine_when_the_candidate_typed_one(upload, runner):
    runner.answers["cv-summary"] = {"summary": "Analyst.", "keywords": ["SQL"]}

    response = upload(CV, target_role="Product manager")

    assert response.status_code == 200
    assert response.json()["target_role"] == "Product manager"


def test_a_blank_summary_fails(upload, runner):
    runner.answers["cv-summary"] = {**GOOD, "summary": "  \n "}

    assert upload(CV).status_code == 502


def test_duplicate_keywords_are_merged_ignoring_case_and_keeping_the_first(upload, runner):
    runner.answers["cv-summary"] = {**GOOD, "keywords": ["SQL", "Python", "sql", "PYTHON", "Excel"]}

    response = upload(CV)

    assert response.json()["keywords"] == ["SQL", "Python", "Excel"]
