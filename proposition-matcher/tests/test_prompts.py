from types import SimpleNamespace

from proposition_matcher.matching.prompts import (
    build_group_rerank_prompt,
    build_summarise_prompt,
    law_citation,
    parse_group_rerank_json,
)


def _gp(regulatory_kind="statutory_obligation"):
    return SimpleNamespace(
        source_url="https://www.gov.uk/x",
        section_locator="section:1",
        proposition_text="A farmer must store slurry safely.",
        regulatory_kind=regulatory_kind,
    )


def _lp(law_id="prop:abc", article_reference=None, fragment_locator=None):
    return SimpleNamespace(
        id=law_id,
        proposition_text="Slurry stores must be impermeable.",
        article_reference=article_reference,
        fragment_locator=fragment_locator,
    )


def test_law_citation_falls_back_to_fragment_locator():
    assert law_citation(_lp(article_reference="reg 4")) == "reg 4"
    assert law_citation(_lp(fragment_locator="regulation 1(1)")) == "regulation 1(1)"
    assert law_citation(_lp()) == "—"
    assert law_citation({"fragment_locator": "reg 9"}) == "reg 9"


def test_law_citation_from_candidate_presentation():
    assert law_citation({
        "presentation": {"locator_label": "regulation 2(1)"},
        "evidence": {"fragment_locators": ["regulation 9"]},
    }) == "regulation 2(1)"
    assert law_citation({
        "evidence": {"fragment_locators": ["regulation 4(2)"]},
    }) == "regulation 4(2)"


def test_law_citation_from_law_unit_citation_attr():
    unit = SimpleNamespace(citation="regulation 1(1)", article_reference=None, fragment_locator=None)
    assert law_citation(unit) == "regulation 1(1)"


def test_group_rerank_prompt_renders_regulatory_kind_and_candidates():
    p = build_group_rerank_prompt(_gp(), [(_lp(fragment_locator="regulation 1(1)"), 0.81)])
    assert "[regulatory_kind: statutory_obligation]" in p
    assert "(regulation 1(1))" in p
    assert "Slurry stores must be impermeable." in p
    assert "[prop:abc]" in p


def test_group_rerank_prompt_regulatory_kind_degrades_to_unknown():
    p = build_group_rerank_prompt(_gp(regulatory_kind=""), [(_lp(), 0.7)])
    assert "[regulatory_kind: unknown]" in p


def test_parse_group_rerank_json_normalises_and_handles_prose():
    raw = (
        'Here is the result:\n{"best_anchor_id": "prop:abc", "anchor_rationale": "fits", '
        '"matches": [{"law_id": "prop:abc", "relationship": "GROUNDED", "confidence": "high", '
        '"explanation": "ok", "correctness_score": 0.9}, '
        '{"law_id": "prop:zzz", "relationship": "nonsense", "confidence": "low", '
        '"explanation": "no", "correctness_score": 0}]}'
    )
    out = parse_group_rerank_json(raw)
    assert out["best_anchor_id"] == "prop:abc"
    assert out["matches"][0]["relationship"] == "GROUNDED"
    assert out["matches"][1]["relationship"] == "UNGROUNDED"  # unknown label normalised


def test_summarise_prompt_renders_matches():
    matches = [{"relationship": "GROUNDED", "explanation": "matches",
                "law_proposition": {"proposition_text": "L", "fragment_locator": "reg 4"}}]
    p = build_summarise_prompt(_gp(), matches)
    assert "Relationship: GROUNDED" in p and "Citation: reg 4" in p
    assert "No relevant law matches" in build_summarise_prompt(_gp(), [])


def test_summarise_prompt_uses_candidate_statement_text():
    matches = [{
        "relationship": "GROUNDED",
        "explanation": "matches",
        "law_proposition": {
            "statement_text": "Candidate law statement.",
            "presentation": {"locator_label": "regulation 2(1)"},
        },
    }]
    p = build_summarise_prompt(_gp(), matches)
    assert "Law: Candidate law statement." in p
    assert "Citation: regulation 2(1)" in p
