"""Qualified Article 49a reference forms for typed legal relationships (Prompt 18-BR1)."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_pipeline.legal_rule_groups import build_legal_rule_groups, legal_rule_group_id
from law_proposition_extractor_pipeline.legal_rule_relationships import (
    _canonical_comparison_key,
    build_legal_rule_relationships,
    legal_rule_relationship_id,
)
from law_proposition_extractor_pipeline.context_locator_resolution import (
    LocatorSegment,
    LocatorStructuralContext,
)

_STRUCTURAL_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "structural_child_extraction"
    / "article_49a_shaped_fragments.json"
)
_QUALIFIED_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "legal_rule_relationships"
    / "article_49a_qualified_references.json"
)

SOURCE = "src-control-regulation-demo"
SNAPSHOT = "snap-src-control-regulation-demo-v1"
OTHER_SOURCE = "src-other-regulation-demo"
OTHER_SNAPSHOT = "snap-src-other-regulation-demo-v1"


def _load_structural() -> dict:
    return json.loads(_STRUCTURAL_FIXTURE.read_text(encoding="utf-8"))


def _load_qualified() -> dict:
    return json.loads(_QUALIFIED_FIXTURE.read_text(encoding="utf-8"))


def _fragments() -> list[dict]:
    payload = _load_structural()
    rows: list[dict] = []
    source_id = str(payload["source_record_id"])
    snapshot_id = str(payload["source_snapshot_id"])
    for item in payload["fragments"]:
        rows.append(
            {
                "id": item["id"],
                "source_record_id": source_id,
                "source_snapshot_id": snapshot_id,
                "locator": item["locator"],
                "fragment_text": item["fragment_text"],
                "parent_fragment_id": item.get("parent_fragment_id"),
                "order_index": item.get("order_index"),
                "fragment_type": item.get("fragment_type"),
                "fragment_hash": f"hash-{item['id']}",
            }
        )
    other = payload.get("other_instrument") or {}
    other_source = str(other.get("source_record_id") or OTHER_SOURCE)
    other_snapshot = str(other.get("source_snapshot_id") or OTHER_SNAPSHOT)
    for item in other.get("fragments") or []:
        rows.append(
            {
                "id": item["id"],
                "source_record_id": other_source,
                "source_snapshot_id": other_snapshot,
                "locator": item["locator"],
                "fragment_text": item["fragment_text"],
                "parent_fragment_id": item.get("parent_fragment_id"),
                "order_index": item.get("order_index"),
                "fragment_type": item.get("fragment_type"),
                "fragment_hash": f"hash-{item['id']}",
            }
        )
    return rows


def _prop(row: dict, *, source_record_id: str = SOURCE, source_snapshot_id: str = SNAPSHOT) -> dict:
    return {
        "id": row["id"],
        "source_record_id": source_record_id,
        "source_snapshot_id": source_snapshot_id,
        "source_fragment_id": row["source_fragment_id"],
        "fragment_locator": row["fragment_locator"],
        "source_order": row.get("source_order"),
        "proposition_text": row["proposition_text"],
        "legal_effect_type": row.get("legal_effect_type") or "obligation",
        "proposition_tier": "substantive_rule",
        "topic_id": "topic-demo",
        "jurisdiction": "UK",
        "legal_subject": "operator",
        "action": "comply",
        "explicit_cross_reference_targets": list(row.get("explicit_cross_reference_targets") or []),
    }


def _qualified_bundle() -> tuple[list[dict], list[dict], dict]:
    qual = _load_qualified()
    props = [_prop(row) for row in qual["qualified_propositions"]]
    props.extend(_prop(row) for row in qual["negative_cases"])
    # Same locator in another source/snapshot must not collide.
    props.append(
        _prop(
            {
                "id": "prop-other-qual-exception",
                "source_fragment_id": "frag-other-49a-p2",
                "fragment_locator": "article:49a:paragraph:2",
                "proposition_text": "Paragraph 1 of Article 49a shall not apply in the other instrument.",
                "legal_effect_type": "derogation",
                "explicit_cross_reference_targets": ["Paragraph 1 of Article 49a"],
            },
            source_record_id=OTHER_SOURCE,
            source_snapshot_id=OTHER_SNAPSHOT,
        )
    )
    props.append(
        _prop(
            {
                "id": "prop-other-qual-p1-a",
                "source_fragment_id": "frag-other-49a-p1",
                "fragment_locator": "article:49a:paragraph:1",
                "proposition_text": "Other instrument first proposition from paragraph 1.",
                "legal_effect_type": "obligation",
            },
            source_record_id=OTHER_SOURCE,
            source_snapshot_id=OTHER_SNAPSHOT,
        )
    )
    props.append(
        _prop(
            {
                "id": "prop-other-qual-p1-b",
                "source_fragment_id": "frag-other-49a-p1",
                "fragment_locator": "article:49a:paragraph:1",
                "proposition_text": "Other instrument second proposition from paragraph 1.",
                "legal_effect_type": "obligation",
            },
            source_record_id=OTHER_SOURCE,
            source_snapshot_id=OTHER_SNAPSHOT,
        )
    )
    frags = _fragments()
    groups = build_legal_rule_groups(props, run_id="run-qual-49a", source_fragments=frags)
    return props, frags, groups


def _p1_group_id() -> str:
    return legal_rule_group_id(
        source_snapshot_id=SNAPSHOT,
        source_fragment_id="frag-demo-49a-p1",
        canonical_locator="article:49a:paragraph:1",
    )


def _p2_group_id() -> str:
    return legal_rule_group_id(
        source_snapshot_id=SNAPSHOT,
        source_fragment_id="frag-demo-49a-p2",
        canonical_locator="article:49a:paragraph:2",
    )


def test_live_diagnostic_notes_document_four_failure_modes() -> None:
    notes = _load_qualified()["live_diagnostics_notes"]
    assert len(notes) == 4
    stages = {n["failure_stage"] for n in notes}
    assert "cue_regex_capture" in stages
    assert "cue_to_reference_association" in stages
    assert sum(1 for n in notes if n["failure_stage"] == "cue_regex_capture") == 3


def test_qualified_exception_targets_paragraph_1_group() -> None:
    props, frags, groups = _qualified_bundle()
    result = build_legal_rule_relationships(
        props, run_id="run-qual-49a", source_fragments=frags, legal_rule_groups=groups
    )
    rels = result["relationships"]
    p1 = _p1_group_id()

    e1 = next(r for r in rels if r["source_id"] == "prop-qual-49a-e1-pelagic")
    assert e1["relationship_type"] == "exception_to"
    assert e1["target_kind"] == "legal_rule_group"
    assert e1["target_id"] == p1
    assert e1["referenced_locator"] == "article:49a:paragraph:1"
    assert e1["reference_text"] == "Paragraph 1 of Article 49a"

    e2 = next(r for r in rels if r["source_id"] == "prop-qual-49a-e2-industrial")
    assert e2["relationship_type"] == "exception_to"
    assert e2["target_id"] == p1
    assert e2["reference_text"] == "Article 49a(1)"

    e3 = next(r for r in rels if r["source_id"] == "prop-qual-49a-e3-small-vessels")
    assert e3["relationship_type"] == "exception_to"
    assert e3["target_id"] == p1
    assert "Article 14" not in (e3.get("referenced_locator") or "")
    assert e3["reference_text"] == "Paragraph 1 of Article 49a"

    exceptions = [r for r in rels if r["relationship_type"] == "exception_to" and r["source_record_id"] == SOURCE]
    assert len(exceptions) == 3


def test_bare_paragraph_1_exception_still_works() -> None:
    props, frags, groups = _qualified_bundle()
    props.append(
        _prop(
            {
                "id": "prop-bare-p1-exception",
                "source_fragment_id": "frag-demo-49a-p2",
                "fragment_locator": "article:49a:paragraph:2",
                "proposition_text": "Paragraph 1 shall not apply where records are incomplete.",
                "legal_effect_type": "derogation",
                "explicit_cross_reference_targets": ["paragraph 1"],
            }
        )
    )
    # Rebuild groups so membership stays consistent (extra prop on p2 enlarges group).
    groups = build_legal_rule_groups(props, run_id="run-qual-49a", source_fragments=frags)
    result = build_legal_rule_relationships(
        props, run_id="run-qual-49a", source_fragments=frags, legal_rule_groups=groups
    )
    rel = next(r for r in result["relationships"] if r["source_id"] == "prop-bare-p1-exception")
    assert rel["target_id"] == _p1_group_id()
    assert rel["referenced_locator"] == "article:49a:paragraph:1"
    assert rel["resolution_basis"] == "structural_relative"


def test_equivalent_exception_forms_do_not_duplicate() -> None:
    props = [
        _prop(
            {
                "id": "prop-dual-form-exception",
                "source_fragment_id": "frag-demo-49a-p2",
                "fragment_locator": "article:49a:paragraph:2",
                "proposition_text": (
                    "Paragraph 1 of Article 49a shall not apply. "
                    "Article 49a(1) shall not apply in the same circumstances."
                ),
                "legal_effect_type": "derogation",
                "explicit_cross_reference_targets": [
                    "Paragraph 1 of Article 49a",
                    "Article 49a(1)",
                ],
            }
        ),
        _prop(
            {
                "id": "prop-dual-p1-a",
                "source_fragment_id": "frag-demo-49a-p1",
                "fragment_locator": "article:49a:paragraph:1",
                "proposition_text": "Baseline obligation A.",
                "legal_effect_type": "obligation",
            }
        ),
        _prop(
            {
                "id": "prop-dual-p1-b",
                "source_fragment_id": "frag-demo-49a-p1",
                "fragment_locator": "article:49a:paragraph:1",
                "proposition_text": "Baseline obligation B.",
                "legal_effect_type": "obligation",
            }
        ),
    ]
    frags = _fragments()
    groups = build_legal_rule_groups(props, run_id="run-dual", source_fragments=frags)
    result = build_legal_rule_relationships(
        props, run_id="run-dual", source_fragments=frags, legal_rule_groups=groups
    )
    dual = [r for r in result["relationships"] if r["source_id"] == "prop-dual-form-exception"]
    assert len(dual) == 1
    assert dual[0]["target_id"] == _p1_group_id()
    assert dual[0]["id"] == legal_rule_relationship_id(
        relationship_type="exception_to",
        source_id="prop-dual-form-exception",
        target_kind="legal_rule_group",
        target_id=_p1_group_id(),
        referenced_locator="article:49a:paragraph:1",
        inference_basis="explicit_exception_cue",
    )


def test_qualified_trigger_targets_paragraph_2_group() -> None:
    props, frags, groups = _qualified_bundle()
    result = build_legal_rule_relationships(
        props, run_id="run-qual-49a", source_fragments=frags, legal_rule_groups=groups
    )
    monitoring = next(
        r for r in result["relationships"] if r["source_id"] == "prop-qual-49a-p3-monitoring"
    )
    assert monitoring["relationship_type"] == "triggered_by"
    assert monitoring["target_kind"] == "legal_rule_group"
    assert monitoring["target_id"] == _p2_group_id()
    assert monitoring["referenced_locator"] == "article:49a:paragraph:2"
    assert monitoring["reference_text"] == "Article 49a(2)"
    assert monitoring["resolution_basis"] == "explicit"

    # paragraph 2 of Article 49a equivalent
    props.append(
        _prop(
            {
                "id": "prop-qual-trigger-of-form",
                "source_fragment_id": "frag-demo-49a-p3",
                "fragment_locator": "article:49a:paragraph:3",
                "proposition_text": (
                    "In the cases referred to in paragraph 2 of Article 49a, "
                    "a fisheries administration must monitor catch composition."
                ),
                "legal_effect_type": "obligation",
                "explicit_cross_reference_targets": ["paragraph 2 of Article 49a"],
            }
        )
    )
    groups = build_legal_rule_groups(props, run_id="run-qual-49a", source_fragments=frags)
    result = build_legal_rule_relationships(
        props, run_id="run-qual-49a", source_fragments=frags, legal_rule_groups=groups
    )
    of_form = next(r for r in result["relationships"] if r["source_id"] == "prop-qual-trigger-of-form")
    assert of_form["target_id"] == _p2_group_id()

    # bare paragraph 2 still works
    props.append(
        _prop(
            {
                "id": "prop-bare-trigger",
                "source_fragment_id": "frag-demo-49a-p3",
                "fragment_locator": "article:49a:paragraph:3",
                "proposition_text": (
                    "In the cases referred to in paragraph 2, "
                    "a fisheries administration must monitor catch composition."
                ),
                "legal_effect_type": "obligation",
                "explicit_cross_reference_targets": ["paragraph 2"],
            }
        )
    )
    groups = build_legal_rule_groups(props, run_id="run-qual-49a", source_fragments=frags)
    result = build_legal_rule_relationships(
        props, run_id="run-qual-49a", source_fragments=frags, legal_rule_groups=groups
    )
    bare = next(r for r in result["relationships"] if r["source_id"] == "prop-bare-trigger")
    assert bare["target_id"] == _p2_group_id()
    assert bare["resolution_basis"] == "structural_relative"


def test_equivalent_trigger_forms_do_not_duplicate() -> None:
    props = [
        _prop(
            {
                "id": "prop-dual-trigger",
                "source_fragment_id": "frag-demo-49a-p3",
                "fragment_locator": "article:49a:paragraph:3",
                "proposition_text": (
                    "In the cases referred to in Article 49a(2), monitoring applies. "
                    "In the cases referred to in paragraph 2 of Article 49a, sampling applies."
                ),
                "legal_effect_type": "obligation",
            }
        ),
        _prop(
            {
                "id": "prop-dual-e1",
                "source_fragment_id": "frag-demo-49a-p2",
                "fragment_locator": "article:49a:paragraph:2",
                "proposition_text": "Paragraph 1 shall not apply for pelagic catches.",
                "legal_effect_type": "derogation",
                "explicit_cross_reference_targets": ["paragraph 1"],
            }
        ),
        _prop(
            {
                "id": "prop-dual-e2",
                "source_fragment_id": "frag-demo-49a-p2",
                "fragment_locator": "article:49a:paragraph:2",
                "proposition_text": "Paragraph 1 shall not apply for industrial catches.",
                "legal_effect_type": "derogation",
                "explicit_cross_reference_targets": ["paragraph 1"],
            }
        ),
        _prop(
            {
                "id": "prop-dual-e3",
                "source_fragment_id": "frag-demo-49a-p2",
                "fragment_locator": "article:49a:paragraph:2",
                "proposition_text": "Paragraph 1 shall not apply for small vessels.",
                "legal_effect_type": "derogation",
                "explicit_cross_reference_targets": ["paragraph 1"],
            }
        ),
    ]
    frags = _fragments()
    groups = build_legal_rule_groups(props, run_id="run-dual-trig", source_fragments=frags)
    result = build_legal_rule_relationships(
        props, run_id="run-dual-trig", source_fragments=frags, legal_rule_groups=groups
    )
    triggers = [r for r in result["relationships"] if r["source_id"] == "prop-dual-trigger"]
    assert len(triggers) == 1
    assert triggers[0]["target_id"] == _p2_group_id()


def test_article_14_not_exception_target_and_remains_ordinary_context() -> None:
    props, frags, groups = _qualified_bundle()
    result = build_legal_rule_relationships(
        props, run_id="run-qual-49a", source_fragments=frags, legal_rule_groups=groups
    )
    e3 = next(r for r in result["relationships"] if r["source_id"] == "prop-qual-49a-e3-small-vessels")
    assert "14" not in e3["referenced_locator"]
    assert e3["target_canonical_locator"] == "article:49a:paragraph:1"
    assert not any(
        r["relationship_type"] == "exception_to"
        and "14" in str(r.get("referenced_locator") or "")
        for r in result["relationships"]
    )
    # Generic Article 14 reference without exception/trigger cue → no typed edge.
    assert not any(r["source_id"] == "prop-qual-generic-ref" for r in result["relationships"])


def test_qualified_reference_outside_cue_span_not_typed_target() -> None:
    props = [
        _prop(
            {
                "id": "prop-outside-cue",
                "source_fragment_id": "frag-demo-49a-p2",
                "fragment_locator": "article:49a:paragraph:2",
                "proposition_text": (
                    "Paragraph 1 of Article 49a shall not apply where catches are recorded "
                    "in accordance with Article 14."
                ),
                "legal_effect_type": "derogation",
                "explicit_cross_reference_targets": [
                    "Paragraph 1 of Article 49a",
                    "Article 14",
                ],
            }
        ),
        _prop(
            {
                "id": "prop-out-p1-a",
                "source_fragment_id": "frag-demo-49a-p1",
                "fragment_locator": "article:49a:paragraph:1",
                "proposition_text": "P1a",
                "legal_effect_type": "obligation",
            }
        ),
        _prop(
            {
                "id": "prop-out-p1-b",
                "source_fragment_id": "frag-demo-49a-p1",
                "fragment_locator": "article:49a:paragraph:1",
                "proposition_text": "P1b",
                "legal_effect_type": "obligation",
            }
        ),
    ]
    frags = _fragments()
    groups = build_legal_rule_groups(props, run_id="run-out", source_fragments=frags)
    result = build_legal_rule_relationships(
        props, run_id="run-out", source_fragments=frags, legal_rule_groups=groups
    )
    rels = [r for r in result["relationships"] if r["source_id"] == "prop-outside-cue"]
    assert len(rels) == 1
    assert rels[0]["referenced_locator"] == "article:49a:paragraph:1"
    assert rels[0]["reference_text"] == "Paragraph 1 of Article 49a"


def test_canonical_comparison_matches_qualified_forms() -> None:
    ctx = LocatorStructuralContext(
        segments=[
            LocatorSegment(kind="article", num="49a"),
            LocatorSegment(kind="paragraph", num="2"),
        ],
        source_record_id=SOURCE,
    )
    pairs = _load_qualified()["equivalence_pairs"]
    p1_keys = {_canonical_comparison_key(form, ctx) for form in pairs["paragraph_1"]}
    assert p1_keys == {"article 49a(1)"}
    p2_keys = {_canonical_comparison_key(form, ctx) for form in pairs["paragraph_2"]}
    assert p2_keys == {"article 49a(2)"}


def test_other_source_and_snapshot_do_not_collide() -> None:
    props, frags, groups = _qualified_bundle()
    result = build_legal_rule_relationships(
        props, run_id="run-qual-49a", source_fragments=frags, legal_rule_groups=groups
    )
    demo = next(r for r in result["relationships"] if r["source_id"] == "prop-qual-49a-e1-pelagic")
    other = next(r for r in result["relationships"] if r["source_id"] == "prop-other-qual-exception")
    assert demo["source_record_id"] == SOURCE
    assert other["source_record_id"] == OTHER_SOURCE
    assert demo["target_id"] != other["target_id"]


def test_qualified_reference_to_missing_article_creates_no_relationship() -> None:
    props, frags, groups = _qualified_bundle()
    result = build_legal_rule_relationships(
        props, run_id="run-qual-49a", source_fragments=frags, legal_rule_groups=groups
    )
    assert not any(
        r["source_id"] == "prop-qual-other-article-exception" for r in result["relationships"]
    )


def test_downstream_effective_law_typed_contexts_restored() -> None:
    from law_proposition_extractor_pipeline.effective_law import build_effective_law_statements

    props, frags, groups = _qualified_bundle()
    core_ids = {
        "prop-qual-49a-p1-a",
        "prop-qual-49a-p1-b",
        "prop-qual-49a-e1-pelagic",
        "prop-qual-49a-e2-industrial",
        "prop-qual-49a-e3-small-vessels",
        "prop-qual-49a-p3-monitoring",
    }
    core = [p for p in props if p["id"] in core_ids]
    # effective-law composer expects compliance-relevant props
    for p in core:
        p["is_compliance_relevant"] = True
    groups = build_legal_rule_groups(core, run_id="run-qual-49a", source_fragments=frags)
    rels = build_legal_rule_relationships(
        core, run_id="run-qual-49a", source_fragments=frags, legal_rule_groups=groups
    )
    assert sum(1 for r in rels["relationships"] if r["relationship_type"] == "exception_to") == 3
    assert sum(1 for r in rels["relationships"] if r["relationship_type"] == "triggered_by") == 1
    assert not any(d["source_id"] in core_ids for d in rels["diagnostics"])

    p1_members = [p for p in core if p["source_fragment_id"] == "frag-demo-49a-p1"]
    p2_members = [p for p in core if p["source_fragment_id"] == "frag-demo-49a-p2"]
    assert len(p1_members) == 2
    assert len(p2_members) == 3

    payload = build_effective_law_statements(
        core,
        run_id="run-qual-49a",
        source_fragments=frags,
        legal_rule_groups=groups,
        legal_rule_relationships=rels,
    )
    by_prop = {
        stmt["source_proposition_ids"][0]: stmt
        for stmt in payload["statements"]
        if stmt.get("source_proposition_ids")
    }

    def _typed(stmt: dict, kind: str) -> list[dict]:
        return [c for c in stmt.get("required_context") or [] if c.get("kind") == kind]

    def _ids(entries: list[dict]) -> list[str]:
        out: list[str] = []
        for entry in entries:
            for pid in entry.get("proposition_ids") or []:
                if pid not in out:
                    out.append(str(pid))
        return out

    e_ids = [
        "prop-qual-49a-e1-pelagic",
        "prop-qual-49a-e2-industrial",
        "prop-qual-49a-e3-small-vessels",
    ]
    p_ids = ["prop-qual-49a-p1-a", "prop-qual-49a-p1-b"]

    for pid in p_ids:
        assert _ids(_typed(by_prop[pid], "applicable_exception")) == e_ids
    for eid in e_ids:
        assert _ids(_typed(by_prop[eid], "exception_target")) == p_ids
        assert not any(
            "14" in str(c.get("locator") or "")
            for c in by_prop[eid].get("required_context") or []
            if c.get("kind") == "exception_target"
        )
    assert _ids(_typed(by_prop["prop-qual-49a-p3-monitoring"], "trigger_condition")) == e_ids


def test_output_deterministic_across_shuffle() -> None:
    props, frags, groups = _qualified_bundle()
    a = build_legal_rule_relationships(
        props, run_id="run-qual-49a", source_fragments=frags, legal_rule_groups=groups
    )
    b = build_legal_rule_relationships(
        list(reversed(props)),
        run_id="run-qual-49a",
        source_fragments=list(reversed(frags)),
        legal_rule_groups=groups,
    )
    assert [r["id"] for r in a["relationships"]] == [r["id"] for r in b["relationships"]]
    assert a["relationships"] == b["relationships"]
