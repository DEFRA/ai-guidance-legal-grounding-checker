"""Effective-law composition from typed LegalRuleGroup / LegalRuleRelationship edges."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_pipeline.effective_law import (
    attach_effective_law_artifacts,
    build_effective_law_statements,
    effective_law_payload_digest,
)
from law_proposition_extractor_pipeline.legal_rule_groups import build_legal_rule_groups, legal_rule_group_id
from law_proposition_extractor_pipeline.legal_rule_relationships import build_legal_rule_relationships
from law_proposition_extractor_pipeline.linting import lint_bundle

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "structural_child_extraction"
    / "article_49a_shaped_fragments.json"
)

SOURCE = "src-control-regulation-demo"
SNAPSHOT = "snap-src-control-regulation-demo-v1"

P1 = "prop-demo-49a-p1-separate"
P2 = "prop-demo-49a-p1-no-mixing"
E1 = "prop-demo-49a-p2-pelagic"
E2 = "prop-demo-49a-p2-industrial"
E3 = "prop-demo-49a-p2-small-vessels"
P3 = "prop-demo-49a-p3-monitoring"


def _load_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _fragments_from_fixture(payload: dict) -> list[dict]:
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
    return rows


def _prop_from_row(row: dict) -> dict:
    return {
        "id": row["id"],
        "source_record_id": SOURCE,
        "source_snapshot_id": SNAPSHOT,
        "source_fragment_id": row["source_fragment_id"],
        "fragment_locator": row["fragment_locator"],
        "source_order": row.get("source_order"),
        "proposition_text": row["proposition_text"],
        "legal_effect_type": row.get("legal_effect_type") or "obligation",
        "proposition_tier": "substantive_rule",
        "is_compliance_relevant": True,
        "topic_id": "topic-demo",
        "jurisdiction": "UK",
        "legal_subject": "operator",
        "action": "comply",
        "explicit_cross_reference_targets": list(row.get("explicit_cross_reference_targets") or []),
        "extraction_debug_meta": dict(row.get("extraction_debug_meta") or {}),
    }


def _49a_bundle_inputs(*, shuffle: bool = False) -> tuple[list[dict], list[dict], dict, dict]:
    payload = _load_fixture()
    props = [_prop_from_row(row) for row in payload["exported_propositions"]]
    frags = _fragments_from_fixture(payload)
    if shuffle:
        props = list(reversed(props))
        frags = list(reversed(frags))
    groups = build_legal_rule_groups(props, run_id="run-49a", source_fragments=frags)
    rels = build_legal_rule_relationships(
        props, run_id="run-49a", source_fragments=frags, legal_rule_groups=groups
    )
    return props, frags, groups, rels


def _statements_by_prop(payload: dict) -> dict[str, dict]:
    return {
        stmt["source_proposition_ids"][0]: stmt
        for stmt in payload["statements"]
        if stmt.get("source_proposition_ids")
    }


def _typed_ctx(stmt: dict, *, kind: str) -> list[dict]:
    return [c for c in stmt.get("required_context") or [] if c.get("kind") == kind]


def _ctx_prop_ids(entries: list[dict]) -> list[str]:
    ids: list[str] = []
    for entry in entries:
        for pid in entry.get("proposition_ids") or []:
            if pid not in ids:
                ids.append(str(pid))
    return ids


def test_article_49a_incoming_exceptions_on_p1_and_p2() -> None:
    props, frags, groups, rels = _49a_bundle_inputs()
    payload = build_effective_law_statements(
        props,
        run_id="run-49a",
        source_fragments=frags,
        legal_rule_groups=groups,
        legal_rule_relationships=rels,
    )
    by_prop = _statements_by_prop(payload)
    p1_group = legal_rule_group_id(
        source_snapshot_id=SNAPSHOT,
        source_fragment_id="frag-demo-49a-p1",
        canonical_locator="article:49a:paragraph:1",
    )

    for prop_id in (P1, P2):
        stmt = by_prop[prop_id]
        exceptions = _typed_ctx(stmt, kind="applicable_exception")
        assert _ctx_prop_ids(exceptions) == [E1, E2, E3]
        assert stmt["standalone_status"] == "context_dependent"
        for entry in exceptions:
            assert entry["resolution_status"] == "resolved"
            assert entry["inherited_via_group"] is True
            assert entry["legal_rule_group_id"] == p1_group
            assert entry["relationship_type"] == "exception_to"
            assert entry["relationship_direction"] == "incoming"
            assert entry["relationship_id"].startswith("legalrel:")
            assert entry["resolution_basis"] == "structural_relative"
            assert entry["inference_basis"] == "explicit_exception_cue"

    # Persisted relationships remain group-targeted (not rewritten to six edges).
    exception_edges = [
        r for r in rels["relationships"] if r["relationship_type"] == "exception_to" and r["source_id"] in {E1, E2, E3}
    ]
    assert len(exception_edges) == 3
    assert all(r["target_kind"] == "legal_rule_group" and r["target_id"] == p1_group for r in exception_edges)


def test_article_49a_exception_target_context_and_article_14() -> None:
    props, frags, groups, rels = _49a_bundle_inputs()
    payload = build_effective_law_statements(
        props,
        run_id="run-49a",
        source_fragments=frags,
        legal_rule_groups=groups,
        legal_rule_relationships=rels,
    )
    by_prop = _statements_by_prop(payload)

    for prop_id in (E1, E2, E3):
        stmt = by_prop[prop_id]
        targets = _typed_ctx(stmt, kind="exception_target")
        assert _ctx_prop_ids(targets) == [P1, P2]
        assert all(t["inherited_via_group"] is True for t in targets)
        assert all(t["relationship_direction"] == "outgoing" for t in targets)
        assert not any(c.get("kind") == "exception_target" and "14" in ",".join(c.get("proposition_ids") or []) for c in stmt["required_context"])
        assert not any(
            c.get("kind") == "exception_target" and "14" in str(c.get("locator") or "")
            for c in stmt["required_context"]
        )

    e3 = by_prop[E3]
    art14 = [
        c
        for c in e3["required_context"]
        if "14" in str(c.get("locator") or "").lower()
        or any("14" in str(pid) for pid in (c.get("proposition_ids") or []))
    ]
    assert art14
    assert all(c.get("kind") != "exception_target" for c in art14)


def test_article_49a_trigger_context_on_p3_not_incoming_to_exceptions() -> None:
    props, frags, groups, rels = _49a_bundle_inputs()
    payload = build_effective_law_statements(
        props,
        run_id="run-49a",
        source_fragments=frags,
        legal_rule_groups=groups,
        legal_rule_relationships=rels,
    )
    by_prop = _statements_by_prop(payload)
    p2_group = legal_rule_group_id(
        source_snapshot_id=SNAPSHOT,
        source_fragment_id="frag-demo-49a-p2",
        canonical_locator="article:49a:paragraph:2",
    )

    p3 = by_prop[P3]
    triggers = _typed_ctx(p3, kind="trigger_condition")
    assert _ctx_prop_ids(triggers) == [E1, E2, E3]
    for entry in triggers:
        assert entry["inherited_via_group"] is True
        assert entry["legal_rule_group_id"] == p2_group
        assert entry["relationship_type"] == "triggered_by"
        assert entry["relationship_direction"] == "outgoing"
        assert entry["relationship_id"].startswith("legalrel:")

    for prop_id in (E1, E2, E3):
        stmt = by_prop[prop_id]
        assert P3 not in {
            pid for c in stmt["required_context"] for pid in (c.get("proposition_ids") or [])
        }
        assert not _typed_ctx(stmt, kind="trigger_condition")


def test_typed_vs_generic_dedupe_and_ordering() -> None:
    props, frags, groups, rels = _49a_bundle_inputs()
    payload = build_effective_law_statements(
        props,
        run_id="run-49a",
        source_fragments=frags,
        legal_rule_groups=groups,
        legal_rule_relationships=rels,
    )
    by_prop = _statements_by_prop(payload)

    e3 = by_prop[E3]
    # Paragraph-1 generic locator context should be suppressed in favour of typed targets.
    assert not any(
        c.get("kind") not in {"applicable_exception", "exception_target", "trigger_condition"}
        and set(c.get("proposition_ids") or []) <= {P1, P2}
        and c.get("proposition_ids")
        for c in e3["required_context"]
    )
    # Article 14 ordinary locator context remains.
    assert any("14" in str(c.get("locator") or "").lower() for c in e3["required_context"])

    p3 = by_prop[P3]
    # Generic paragraph-2 locator duplicate removed once typed triggers cover members.
    assert not any(
        c.get("kind") == "incorporated_rule" or c.get("kind") == "referenced_locator"
        for c in p3["required_context"]
        if set(c.get("proposition_ids") or []) == {E1, E2, E3}
    )
    assert _ctx_prop_ids(_typed_ctx(p3, kind="trigger_condition")) == [E1, E2, E3]

    # Duplicate relationship processing does not duplicate required context.
    doubled = {
        **rels,
        "relationships": list(rels["relationships"]) + list(rels["relationships"]),
    }
    again = build_effective_law_statements(
        props,
        run_id="run-49a",
        source_fragments=frags,
        legal_rule_groups=groups,
        legal_rule_relationships=doubled,
    )
    assert effective_law_payload_digest(payload) == effective_law_payload_digest(again)


def test_direct_proposition_target_without_group_expansion() -> None:
    props, frags, groups, rels = _49a_bundle_inputs()
    payload = build_effective_law_statements(
        props,
        run_id="run-49a",
        source_fragments=frags,
        legal_rule_groups=groups,
        legal_rule_relationships=rels,
    )
    by_prop = _statements_by_prop(payload)
    host = by_prop["prop-demo-art30-p1-only"]
    exceptions = _typed_ctx(host, kind="applicable_exception")
    assert _ctx_prop_ids(exceptions) == ["prop-demo-art30-p2-exception"]
    assert exceptions[0]["inherited_via_group"] is False
    assert "legal_rule_group_id" not in exceptions[0]

    exception = by_prop["prop-demo-art30-p2-exception"]
    targets = _typed_ctx(exception, kind="exception_target")
    assert _ctx_prop_ids(targets) == ["prop-demo-art30-p1-only"]
    assert targets[0]["inherited_via_group"] is False


def test_missing_group_member_diagnostic_non_blocking() -> None:
    props, frags, groups, rels = _49a_bundle_inputs()
    p1_group_id = legal_rule_group_id(
        source_snapshot_id=SNAPSHOT,
        source_fragment_id="frag-demo-49a-p1",
        canonical_locator="article:49a:paragraph:1",
    )
    broken_groups = {
        **groups,
        "groups": [
            {
                **next(g for g in groups["groups"] if g["id"] == p1_group_id),
                "member_proposition_ids": [P1, "prop-missing-member"],
            },
            *[g for g in groups["groups"] if g["id"] != p1_group_id],
        ],
    }
    payload = build_effective_law_statements(
        props,
        run_id="run-49a",
        source_fragments=frags,
        legal_rule_groups=broken_groups,
        legal_rule_relationships=rels,
    )
    assert any(
        d["code"] == "effective_law_relationship_group_member_missing"
        and d.get("member_id") == "prop-missing-member"
        for d in payload["diagnostics"]
    )
    by_prop = _statements_by_prop(payload)
    assert P1 in _ctx_prop_ids(_typed_ctx(by_prop[E1], kind="exception_target"))


def test_scope_mismatch_produces_no_context_edge() -> None:
    props, frags, groups, rels = _49a_bundle_inputs()
    mismatched = []
    for row in rels["relationships"]:
        if row["source_id"] == E1:
            mismatched.append({**row, "source_snapshot_id": "snap-other"})
        else:
            mismatched.append(row)
    payload = build_effective_law_statements(
        props,
        run_id="run-49a",
        source_fragments=frags,
        legal_rule_groups=groups,
        legal_rule_relationships={**rels, "relationships": mismatched},
    )
    assert any(
        d["code"] == "effective_law_relationship_source_scope_mismatch"
        for d in payload["diagnostics"]
    )
    by_prop = _statements_by_prop(payload)
    assert E1 not in _ctx_prop_ids(_typed_ctx(by_prop[P1], kind="applicable_exception"))


def test_older_bundle_and_empty_typed_artifact_retain_prior_behaviour() -> None:
    props, frags, _groups, _rels = _49a_bundle_inputs()
    locator_only = build_effective_law_statements(
        props,
        run_id="run-49a",
        source_fragments=frags,
    )
    empty_typed = build_effective_law_statements(
        props,
        run_id="run-49a",
        source_fragments=frags,
        legal_rule_groups={"schema_version": "1", "run_id": "run-49a", "groups": []},
        legal_rule_relationships={
            "schema_version": "1",
            "run_id": "run-49a",
            "relationships": [],
            "diagnostics": [],
        },
    )
    assert effective_law_payload_digest(locator_only) == effective_law_payload_digest(empty_typed)
    by_prop = _statements_by_prop(locator_only)
    assert by_prop[P1]["standalone_status"] == "standalone"
    assert _typed_ctx(by_prop[P1], kind="applicable_exception") == []
    # Locator composition for exceptions still present without typed edges.
    assert any(
        set(c.get("proposition_ids") or []) & {P1, P2}
        for c in by_prop[E1]["required_context"]
    )


def test_attach_order_consumes_groups_and_relationships() -> None:
    props, frags, _groups, _rels = _49a_bundle_inputs()
    bundle = {
        "run": {"id": "run-49a-attach"},
        "propositions": props,
        "source_fragments": frags,
        "source_inventory": {"rows": []},
    }
    attach_effective_law_artifacts(bundle)
    assert bundle["legal_rule_groups"]["groups"]
    assert bundle["legal_rule_relationships"]["relationships"]
    by_prop = _statements_by_prop(bundle["effective_law_statements"])
    assert _ctx_prop_ids(_typed_ctx(by_prop[P1], kind="applicable_exception")) == [E1, E2, E3]
    assert _ctx_prop_ids(_typed_ctx(by_prop[P3], kind="trigger_condition")) == [E1, E2, E3]
    assert "composition_trace" in by_prop[P1]
    assert bundle["proposition_matcher_law_candidates"]["candidates"]

    # Serialization round-trip preserves typed provenance.
    dumped = json.loads(json.dumps(bundle["effective_law_statements"]))
    entry = _typed_ctx(_statements_by_prop(dumped)[P1], kind="applicable_exception")[0]
    assert entry["relationship_id"].startswith("legalrel:")
    assert entry["inherited_via_group"] is True
    assert entry["legal_rule_group_id"].startswith("rulegrp:")


def test_deterministic_across_input_ordering() -> None:
    props_a, frags_a, groups_a, rels_a = _49a_bundle_inputs(shuffle=False)
    props_b, frags_b, groups_b, rels_b = _49a_bundle_inputs(shuffle=True)
    a = build_effective_law_statements(
        props_a,
        run_id="run-49a",
        source_fragments=frags_a,
        legal_rule_groups=groups_a,
        legal_rule_relationships=rels_a,
    )
    b = build_effective_law_statements(
        props_b,
        run_id="run-49a",
        source_fragments=frags_b,
        legal_rule_groups=groups_b,
        legal_rule_relationships=rels_b,
    )
    assert effective_law_payload_digest(a) == effective_law_payload_digest(b)


def test_lint_surfaces_effective_law_relationship_diagnostics() -> None:
    report = lint_bundle(
        {
            "source_records": [],
            "source_snapshots": [],
            "source_fragments": [],
            "source_parse_traces": [],
            "proposition_extraction_traces": [],
            "propositions": [],
            "source_inventory": {"rows": []},
            "source_fetch_metadata": [],
            "source_fetch_attempts": [],
            "source_target_links": [],
            "source_categorisation_rationales": [],
            "run_artifacts": [],
            "divergence_observations": [],
            "divergence_assessments": [],
            "divergence_findings": [],
            "legal_scopes": [],
            "proposition_scope_links": [],
            "scope_inventory": {},
            "scope_review_candidates": [],
            "effective_law_statements": {
                "schema_version": "1",
                "run_id": "run-x",
                "statements": [],
                "diagnostics": [
                    {
                        "code": "effective_law_relationship_group_missing",
                        "relationship_id": "legalrel:abc",
                        "target_id": "rulegrp:missing",
                    }
                ],
            },
        }
    )
    assert any("effective_law_relationship_group_missing" in w for w in report["warnings"])
