from pdfs import text_pdf


def test_common_words_are_removed_from_the_keywords(upload, runner):
    runner.answers["cv-summary"] = {
        "summary": "Analyst.",
        "keywords": ["SQL", "Experience", "team", "  ", "team leadership", "the team", "Python"],
        "target_role": "Data analyst",
    }

    response = upload(text_pdf("Analyst at a retail bank"))

    # A phrase stays when it holds a word that is not on the list; case is kept as Qwen wrote it.
    assert response.json()["keywords"] == ["SQL", "team leadership", "Python"]
