from pdfs import text_pdf

CV = text_pdf("Analyst at a retail bank")


def test_an_empty_target_role_is_proposed_from_the_cv(upload, runner):
    response = upload(CV)

    assert response.json()["target_role"] == "Data analyst"
    [[prompt]] = runner.submissions
    assert "target_role" in prompt["prompt"]
    assert "target_role" in prompt["required_keys"]


def test_a_blank_target_role_counts_as_empty(upload, runner):
    response = upload(CV, target_role="   ")

    assert response.json()["target_role"] == "Data analyst"
    assert "target_role" in runner.submissions[0][0]["prompt"]


def test_a_typed_target_role_is_kept_and_qwen_is_not_asked_for_one(upload, runner):
    response = upload(CV, target_role="Product manager")

    assert response.json()["target_role"] == "Product manager"
    [[prompt]] = runner.submissions
    assert "target_role" not in prompt["prompt"]
    assert "target_role" not in prompt["required_keys"]
