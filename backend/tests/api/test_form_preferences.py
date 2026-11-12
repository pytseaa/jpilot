import pytest
from pdfs import text_pdf

CV = text_pdf("Analyst at a retail bank")


def test_the_form_preferences_come_back_for_the_review_screen(upload):
    response = upload(CV, employment_types=["full-time", "contractor"],
                      experience_band="3-5", industry="Banking and finance")

    body = response.json()
    assert body["employment_types"] == ["full-time", "contractor"]
    assert body["experience_band"] == "3-5"
    assert body["industry"] == "Banking and finance"


def test_experience_band_and_industry_may_be_left_blank(upload):
    # A browser sends an empty string for a select left on its blank option.
    response = upload(CV, experience_band="", industry="")

    assert response.status_code == 200
    assert response.json()["experience_band"] is None
    assert response.json()["industry"] is None


@pytest.mark.parametrize("form", [
    {"employment_types": []},
    {"employment_types": ["freelance"]},
    {"experience_band": "11-20"},
    {"industry": "Mining"},
])
def test_a_form_value_outside_the_fixed_lists_is_rejected_before_any_qwen_call(upload, runner, form):
    response = upload(CV, **form)

    assert response.status_code == 422
    assert runner.submissions == []
