"""Unit tests for the ported reading-age scoring — pure, no network."""

from audit_assembler.reading_age import html_to_text, reading_age, score_text


def test_html_to_text_terminates_block_tags_as_sentences():
    html = "<ul><li>First point</li><li>Second point</li></ul><p>A paragraph</p>"
    text = html_to_text(html)
    assert text == "First point. Second point. A paragraph."


def test_html_to_text_strips_script_and_style():
    html = "<p>Keep this</p><script>drop()</script><style>.x{}</style>"
    assert html_to_text(html) == "Keep this."


def test_reading_age_needs_three_sentences():
    assert reading_age("One sentence only.") is None


def test_reading_age_dense_text_is_high_but_capped():
    # Long, dense clauses push SMOG high; the result must never exceed the cap.
    dense = (
        "The aforementioned multifarious environmental considerations necessitate "
        "comprehensive interdisciplinary collaboration. Notwithstanding the "
        "aforementioned regulatory frameworks, stakeholders must conscientiously "
        "evaluate consequential ramifications. Subsequently, the implementation "
        "demands meticulous, painstaking, methodological documentation throughout."
    )
    score = reading_age(dense)
    assert score is not None
    assert 18 <= score <= 25


def test_score_text_counts_words():
    result = score_text("This is a short body of text with words.")
    assert result["word_count"] == 9
    assert result["error"] is None
