"""Pure-transform tests for Match Adjudicator's re-adjudication (no network: a stub judge)."""

from __future__ import annotations

import copy

from match_adjudicator.readjudicate import _parse_verdict, page_siblings, readjudicate

PAGE = "https://www.gov.uk/spreading"

# Two propositions on the same page. The law for the first spans both organic
# manure AND manufactured fertiliser; the guidance splits them, so on its own the
# first looks incomplete but the sibling resolves it.
PROPOSITION_MATCHER_OUTPUT = [
    {
        "url": PAGE,
        "id": "susan-aaa-1",
        "proposition_text": "You must not apply organic manure on waterlogged soil.",
        "summary": "",
        "matches": [
            {
                "law_proposition": {
                    "id": "prop:aaa",
                    "proposition_text": "Must not apply organic manure or manufactured fertiliser.",
                },
                "similarity_score": 0.91,
                "relationship": "GUIDANCE_INCOMPLETE",
                "confidence": "high",
                "explanation": "Omits the manufactured-fertiliser arm.",
            },
            {
                "law_proposition": {"id": "prop:zzz", "proposition_text": "..."},
                "relationship": "UNGROUNDED",
            },
        ],
    },
    {
        "url": PAGE,
        "id": "susan-bbb-1",
        "proposition_text": "You must not apply manufactured fertiliser when waterlogged.",
        "summary": "",
        "matches": [
            {
                "law_proposition": {
                    "id": "prop:bbb",
                    "proposition_text": "Must not apply manufactured fertiliser when waterlogged.",
                },
                "similarity_score": 0.95,
                "relationship": "GROUNDED",
                "confidence": "high",
                "explanation": "Matches.",
            }
        ],
    },
]


def _stub_judge(findings):
    # Batch judge: one verdict per finding, in order. Clears a finding when a
    # sibling on its page covers manufactured fertiliser.
    verdicts = []
    for f in findings:
        covered = any("manufactured fertiliser" in s for s in f["siblings"])
        verdicts.append(
            {"new_status": "GROUNDED" if covered else f["old_status"], "reason": "stub"})
    return verdicts


def test_page_siblings_groups_by_url():
    sib = page_siblings(PROPOSITION_MATCHER_OUTPUT)
    assert len(sib[PAGE]) == 2


def test_only_top_match_of_flagged_findings_is_rejudged_and_committed():
    src = copy.deepcopy(PROPOSITION_MATCHER_OUTPUT)
    out, report = readjudicate(src, _stub_judge)

    # The flagged finding is cleared to GROUNDED in place.
    assert out[0]["matches"][0]["relationship"] == "GROUNDED"
    assert out[0]["matches"][0]["explanation"] == "stub"
    # The non-top match is untouched.
    assert out[0]["matches"][1]["relationship"] == "UNGROUNDED"
    # The already-GROUNDED finding is never reviewed or changed.
    assert out[1]["matches"][0]["relationship"] == "GROUNDED"
    assert out[1]["matches"][0]["explanation"] == "Matches."

    assert report["n_flagged_reviewed"] == 1
    assert report["n_changed"] == 1
    assert report["n_cleared_to_grounded"] == 1
    assert report["by_old_status"] == {"GUIDANCE_INCOMPLETE": 1}


def test_input_is_not_mutated():
    src = copy.deepcopy(PROPOSITION_MATCHER_OUTPUT)
    readjudicate(src, _stub_judge)
    assert src == PROPOSITION_MATCHER_OUTPUT


def test_verdict_held_when_no_sibling_covers_it():
    single = [
        {
            "url": PAGE,
            "id": "susan-ccc-1",
            "proposition_text": "Silo must have an effluent system.",
            "summary": "",
            "matches": [{
                "law_proposition": {
                    "id": "prop:ccc",
                    "proposition_text": "Base must drain via channels to an effluent tank.",
                },
                "relationship": "GUIDANCE_INCOMPLETE",
                "explanation": "Lacks the channel detail.",
            }],
        }
    ]
    out, report = readjudicate(single, _stub_judge)
    assert out[0]["matches"][0]["relationship"] == "GUIDANCE_INCOMPLETE"  # unchanged
    assert report["n_changed"] == 0


def test_parse_verdict_ignores_trailing_prose():
    # The model often appends commentary after the JSON object; take the object.
    raw = '{"new_status": "GROUNDED", "reason": "covered by sibling"}\n\nNote: ...'
    v = _parse_verdict(raw)
    assert v == {"new_status": "GROUNDED", "reason": "covered by sibling"}
