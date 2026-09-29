from guidance_proposition_extractor.prompt import PROMPT, render


def test_prompt_mentions_all_three_metadata_fields():
    assert "subject_area" in PROMPT
    assert "instrument" in PROMPT
    assert "actor" in PROMPT


def test_prompt_mentions_regulatory_kind_and_vocab():
    assert "regulatory_kind" in PROMPT
    for value in (
        "statutory_obligation",
        "permit_requirement",
        "grant_condition",
        "code_of_practice",
        "procedural_step",
        "factual_statement",
        "definition",
    ):
        assert value in PROMPT


def test_prompt_mentions_derives_from_with_never_guess_rule():
    assert "derives_from" in PROMPT
    assert "NEVER guess" in PROMPT


def test_render_preserves_new_fields():
    out = render(body="BODY", source_url="https://gov.uk/x", topic="t")
    assert "regulatory_kind" in out
    assert "derives_from" in out
    assert "statutory_obligation" in out
    assert "grant_condition" in out


def test_prompt_points_at_emit_tool():
    assert "emit_propositions" in PROMPT
    assert "{body}" in PROMPT
    assert "{topic}" in PROMPT
    assert "{source_url}" in PROMPT


def test_render_substitutes_placeholders():
    out = render(body="HELLO BODY", source_url="https://gov.uk/x", topic="test-topic")
    assert "HELLO BODY" in out
    assert "https://gov.uk/x" in out
    assert "test-topic" in out
    assert "{body}" not in out
    assert "{topic}" not in out
    assert "{source_url}" not in out
    assert "emit_propositions" in out
