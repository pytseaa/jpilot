from pdfs import text_pdf

CV = text_pdf("Analyst at a retail bank")
EDITED = {"summary": "Edited summary.", "keywords": ["Excel"], "target_role": "Accountant",
          "employment_types": ["contractor"], "experience_band": "6-9", "industry": "Insurance"}


def test_search_with_the_review_left_unchanged_is_accepted(upload, client):
    review = upload(CV, employment_types=["part-time"], experience_band="0-2").json()

    response = client.post(f"/api/search-requests/{review['id']}/search", json=review)

    assert response.status_code == 200
    assert response.json() == review


def test_search_keeps_the_edited_values_and_makes_no_second_submission(upload, client, runner):
    review = upload(CV).json()

    response = client.post(f"/api/search-requests/{review['id']}/search", json=EDITED)

    assert response.status_code == 200
    assert response.json() == {"id": review["id"], **EDITED}
    assert len(runner.submissions) == 1  # the CV summary from the upload, and nothing since


def test_search_without_an_employment_type_is_rejected(upload, client):
    review = upload(CV).json()

    response = client.post(f"/api/search-requests/{review['id']}/search",
                           json={**EDITED, "employment_types": []})

    assert response.status_code == 422


def test_search_for_an_unknown_request_is_not_found(client):
    response = client.post("/api/search-requests/nope/search", json=EDITED)

    assert response.status_code == 404
