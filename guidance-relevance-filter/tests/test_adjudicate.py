"""Guidance Relevance Filter's pass-2 adjudicator: it re-reads pass-1 positives and drops false
positives, kept honest by FakeCompletions (no network, no API key).
"""

import json
from importlib.resources import files

import pytest

from guidance_relevance_filter.adjudicate import adjudicate, build_prompt, full_spec, parse_verdict

from .fakes import llm

SLURRY_CATEGORY = {
    "name": "slurry",
    "description": "Inclusion: animal slurry storage and handling.",
    "exclusion_criteria": "Exclusion Criteria\n\nNot coal slurry or sewage sludge.",
    "adjudication_hints": {
        "keep": [
            "Slurry store construction grants and lagoon capacity rules",
            "NVZ or SSAFO rules that mention slurry spreading",
        ],
        "drop": [
            "Coal slurry, bentonite slurry or laboratory sample slurrying",
            "Sewage sludge or biosolids as the main subject",
        ],
    },
}
FISH_CATEGORY = {
    "name": "fish",
    "description": "Inclusion: commercial fishery products and aquaculture.",
    "exclusion_criteria": (
        "Exclusion Criteria\n\nNot ornamental aquarium fish or recreational angling."
    ),
    "adjudication_hints": {
        "keep": ["Catch certificates for fishery product exports to the EU"],
        "drop": ["Ornamental aquarium fish and pet-fish trade only"],
    },
}
SLURRY_KEEP = '{"keep": true, "exclusion_hit": "none", "verdict_reason": "slurry stores"}'
SLURRY_DROP = '{"keep": false, "exclusion_hit": "homonym", "verdict_reason": "coal slurry"}'
FISH_KEEP = '{"keep": true, "exclusion_hit": "none", "verdict_reason": "catch certificates"}'
FISH_DROP = '{"keep": false, "exclusion_hit": "wrong_domain", "verdict_reason": "ornamental aquarium fish"}'


def _page(url="https://example.gov.uk/p", body="slurry store guidance"):
    return {"url": url, "content_id": "x",
            "meta_data": {"title": "T", "body_text": body}}


def _positive(cat, url="https://example.gov.uk/p", reason="mentions topic", score=0.3):
    return {"url": url, "content_id": "x", "meta_data": {
        "title": "T", "labels": {cat: True},
        "scores": {cat: score}, "reasons": {cat: reason}}}


def test_full_spec_reattaches_the_exclusion_criteria():
    spec = full_spec(SLURRY_CATEGORY)
    assert "Inclusion" in spec and "Exclusion Criteria" in spec


@pytest.mark.parametrize("category,needle", [
    (SLURRY_CATEGORY, "coal slurry"),
    (FISH_CATEGORY, "ornamental aquarium fish"),
])
def test_prompt_carries_the_full_spec_and_category_hints(category, needle):
    prompt = build_prompt(category, "T", "body", "pass-1 note")
    assert "Exclusion Criteria" in prompt
    assert category["name"].upper() in prompt
    assert needle in prompt


def test_parse_verdict_handles_code_fenced_and_rejects_junk():
    fenced = parse_verdict(f"```json\n{SLURRY_DROP}\n```")
    assert fenced is not None and fenced["keep"] is False
    assert parse_verdict("not json") is None
    assert parse_verdict('{"verdict_reason": "no label"}') is None


@pytest.mark.parametrize("category,body,keep_reply,drop_reply,drop_reason", [
    (
        SLURRY_CATEGORY,
        "slurry store guidance",
        SLURRY_KEEP,
        SLURRY_DROP,
        "coal slurry",
    ),
    (
        FISH_CATEGORY,
        "catch certificate guidance for fishery product exports",
        FISH_KEEP,
        FISH_DROP,
        "ornamental aquarium fish",
    ),
], ids=["slurry", "fish"])
def test_adjudication_drops_and_keeps_by_category(
    category, body, keep_reply, drop_reply, drop_reason,
):
    cat = category["name"]
    results, stats, audit = adjudicate(
        [_page(body=body)], [_positive(cat, reason=f"mentions {cat}")], [category],
        completions=llm(drop_reply),
    )
    assert results[0]["meta_data"]["labels"][cat] is False
    assert stats["n_dropped"] == 1 and stats["n_kept"] == 0
    assert stats["batch"]["id"] == "batch-test"
    assert stats["batch"]["submitted"] == 1
    assert stats["batch"]["collected"] == 1
    assert audit[0]["pass2_keep"] is False
    assert audit[0]["stage"] == "pass2_drop"
    assert results[0]["meta_data"]["reasons"][cat] == drop_reason
    funnel = results[0]["meta_data"]["funnel"]
    assert funnel["stage"] == "pass2_drop"
    assert funnel["pass1_reason"] == f"mentions {cat}"
    assert funnel["pass2_reason"] == drop_reason
    assert funnel["exclusion_hit"] in {"homonym", "wrong_domain"}

    results, stats, _ = adjudicate(
        [_page(body=body)], [_positive(cat, reason=f"mentions {cat}")], [category],
        completions=llm(keep_reply),
    )
    assert results[0]["meta_data"]["labels"][cat] is True
    assert stats["n_kept"] == 1 and stats["n_dropped"] == 0
    assert results[0]["meta_data"]["funnel"]["stage"] == "pass2_keep"


def test_keeps_a_page_it_cannot_adjudicate_rather_than_dropping_it():
    cat = SLURRY_CATEGORY["name"]
    results, stats, audit = adjudicate(
        [_page()], [_positive(cat)], [SLURRY_CATEGORY],
        completions=llm("not json at all"),
    )
    assert results[0]["meta_data"]["labels"][cat] is True
    assert stats["n_unadjudicated"] == 1
    assert results[0]["meta_data"]["reasons"][cat].startswith(
        "[pass-2 adjudication unavailable"
    )
    assert audit[0]["exclusion_hit"] == "unadjudicated"
    assert results[0]["meta_data"]["funnel"]["stage"] == "pass2_unadjudicated"


def test_stamps_truncation_for_an_oversized_body():
    cat = SLURRY_CATEGORY["name"]
    page = _page(body="slurry " * 100)
    results, _, _ = adjudicate(
        [page], [_positive(cat)], [SLURRY_CATEGORY], max_words=5,
        completions=llm(SLURRY_DROP),
    )
    assert results[0]["meta_data"]["reasons"][cat].startswith(
        "[body truncated to 5 words from 100]"
    )


def test_ignores_pass1_negatives_and_makes_no_call_when_there_are_none(capsys):
    cat = SLURRY_CATEGORY["name"]
    negative = {"url": "https://example.gov.uk/n", "content_id": "y",
                "meta_data": {"labels": {cat: False}, "reasons": {cat: "no"},
                              "scores": {cat: 0.0}}}
    # No batch stub: a call would raise, proving the empty-positive path is API-free.
    results, stats, audit = adjudicate([_page()], [negative], [SLURRY_CATEGORY])
    assert stats["n_positives"] == 0 and audit == []
    assert stats["batch"] is None
    assert results[0]["meta_data"]["labels"][cat] is False
    err = capsys.readouterr().err
    assert "0 pass-1 positives" in err
    assert "skipping adjudication" in err


def test_the_baked_in_category_actually_carries_exclusion_criteria():
    categories = json.loads((files("guidance_relevance_filter.data") / "categories.json").read_text())
    assert "Exclusion Criteria" in full_spec(categories[0])
    assert categories[0].get("adjudication_hints")
