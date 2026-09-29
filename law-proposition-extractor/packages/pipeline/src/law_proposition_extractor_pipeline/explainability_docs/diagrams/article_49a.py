"""Generate the Article 49a explainability walkthrough D2 from the acceptance fixture."""

from __future__ import annotations

import re
from typing import Any

from law_proposition_extractor_pipeline.heuristics import REGISTRY_VERSION

from ..fixture_bundle import (
    fixture_content_hash,
    load_serialized_bundle,
    prop_by_id,
    resolve_roles,
    structured_list_path,
)
from ..paths import FIXTURE_RELATIVE, fixture_dir

_ROLE_ORDER = ("P1", "P2", "E1", "E2", "E3", "P3")
_ROLE_LABELS = {
    "P1": "P1 — separate-identification obligation",
    "P2": "P2 — no-mixing prohibition",
    "E1": "E1 — derogation 2-a-i",
    "E2": "E2 — derogation 2-a-ii",
    "E3": "E3 — derogation 2-b",
    "P3": "P3 — monitoring obligation",
}


def render_article_49a_walkthrough_d2() -> str:
    """Return complete D2 source for the Article 49a walkthrough diagram."""
    fixture = fixture_dir()
    bundle = load_serialized_bundle(fixture)
    roles = resolve_roles(bundle)
    content_hash = fixture_content_hash(fixture)

    missing = [r for r in _ROLE_ORDER if r not in roles]
    if missing:
        raise RuntimeError(f"Missing semantic roles for diagram: {missing!r}")

    paths = {
        role: structured_list_path(prop_by_id(bundle, roles[role])) for role in ("E1", "E2", "E3")
    }
    if paths != {"E1": "2-a-i", "E2": "2-a-ii", "E3": "2-b"}:
        raise RuntimeError(f"Unexpected Article 49a structured paths: {paths!r}")

    groups = _groups(bundle)
    sizes = sorted(len(g.get("member_proposition_ids") or []) for g in groups)
    if sizes != [2, 3]:
        raise RuntimeError(f"Expected group sizes [2, 3]; found {sizes!r}")

    rels = _relationships(bundle)
    exception_count = sum(1 for r in rels if r.get("relationship_type") == "exception_to")
    trigger_count = sum(1 for r in rels if r.get("relationship_type") == "triggered_by")
    if exception_count != 3 or trigger_count != 1:
        raise RuntimeError(
            f"Expected 3 exception_to and 1 triggered_by; found "
            f"{exception_count} / {trigger_count}."
        )

    short_hash = content_hash[:12]
    # Opaque proposition IDs must not appear in visible labels.
    for role in _ROLE_ORDER:
        prop_id = roles[role]
        if prop_id.startswith("prop:") and prop_id in _ROLE_LABELS[role]:
            raise RuntimeError("Semantic labels must not embed opaque IDs.")

    return _d2_source(short_hash=short_hash, fixture_rel=str(FIXTURE_RELATIVE.as_posix()))


def _groups(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("legal_rule_groups")
    if isinstance(raw, dict):
        return [g for g in (raw.get("groups") or []) if isinstance(g, dict)]
    if isinstance(raw, list):
        return [g for g in raw if isinstance(g, dict)]
    return []


def _relationships(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("legal_rule_relationships")
    if isinstance(raw, dict):
        return [r for r in (raw.get("relationships") or []) if isinstance(r, dict)]
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    return []


def _d2_source(*, short_hash: str, fixture_rel: str) -> str:
    """Hand-shaped D2 layout; node labels are semantic roles only (no opaque IDs)."""
    return f"""\
# explainability-diagram: article-49a-walkthrough
# title: Article 49a — fragments to effective law
# audience: lawyers, policy specialists, developers, auditors
# purpose: Walk Article 49a from hierarchy through six propositions to typed context.
# authorship: generated
# source-of-truth: {fixture_rel}; article_49a_legal_structure_acceptance.py
# compatible-registry-version: {REGISTRY_VERSION}
# compatible-fixture-hash: {short_hash}
# note: Opaque proposition/relationship IDs are intentionally omitted from labels.

direction: down

classes: {{
  section: {{
    style: {{
      fill: "#F8FAFC"
      stroke: "#64748B"
      stroke-width: 1
      border-radius: 10
      font-size: 14
    }}
  }}
  structural: {{
    shape: rectangle
    style: {{
      fill: "#FFFFFF"
      stroke: "#334155"
      stroke-width: 1
      border-radius: 6
      font-size: 13
    }}
  }}
  selected: {{
    shape: rectangle
    style: {{
      fill: "#ECFDF5"
      stroke: "#047857"
      stroke-width: 2
      border-radius: 6
      font-size: 13
    }}
  }}
  suppressed: {{
    shape: rectangle
    style: {{
      fill: "#F1F5F9"
      stroke: "#64748B"
      stroke-dash: 4
      border-radius: 6
      font-size: 12
    }}
  }}
  semantic_prop: {{
    shape: rectangle
    style: {{
      fill: "#EEF2FF"
      stroke: "#3730A3"
      stroke-width: 2
      border-radius: 6
      font-size: 13
    }}
  }}
  group: {{
    shape: hexagon
    style: {{
      fill: "#F5F3FF"
      stroke: "#5B21B6"
      stroke-width: 2
      font-size: 13
    }}
  }}
  det: {{
    shape: rectangle
    style: {{
      fill: "#F0FDF4"
      stroke: "#166534"
      stroke-width: 2
      border-radius: 4
      font-size: 12
    }}
  }}
  llm: {{
    shape: diamond
    style: {{
      fill: "#FFF7ED"
      stroke: "#C2410C"
      stroke-width: 2
      stroke-dash: 5
      font-size: 12
    }}
  }}
  ref: {{
    shape: parallelogram
    style: {{
      fill: "#FFFFFF"
      stroke: "#475569"
      stroke-dash: 3
      font-size: 12
    }}
  }}
  note: {{
    shape: page
    style: {{
      fill: "#FFFBEB"
      stroke: "#B45309"
      font-size: 12
    }}
  }}
}}

title: |md
  **Article 49a walkthrough** — hierarchy → frontier → six propositions → groups → relationships → effective law
|
title.style.font-size: 16

hierarchy: {{
  label: "1. Source hierarchy (structural fragments)"
  class: section

  art: "Article 49a"
  art.class: structural
  p1: "paragraph 1"
  p1.class: structural
  p2: "paragraph 2"
  p2.class: structural
  a: "branch (a)"
  a.class: structural
  ai: "point (i) → path 2-a-i"
  ai.class: structural
  aii: "point (ii) → path 2-a-ii"
  aii.class: structural
  b: "branch (b) → path 2-b"
  b.class: structural
  p3: "paragraph 3"
  p3.class: structural

  art -> p1
  art -> p2
  art -> p3
  p2 -> a
  p2 -> b
  a -> ai
  a -> aii
}}

frontier: {{
  label: "2. Structural extraction frontier"
  class: section

  f_parent: "[suppressed] Article 49a parent"
  f_parent.class: suppressed
  f_p1: "[selected] paragraph 1"
  f_p1.class: selected
  f_p2: "[selected] paragraph 2"
  f_p2.class: selected
  f_a: "[suppressed] paragraph 2(a) descendant"
  f_a.class: suppressed
  f_p3: "[selected] paragraph 3"
  f_p3.class: selected
}}

props: {{
  label: "3. Six semantic propositions (no opaque IDs)"
  class: section

  P1: "{_ROLE_LABELS["P1"]}"
  P1.class: semantic_prop
  P2: "{_ROLE_LABELS["P2"]}"
  P2.class: semantic_prop
  E1: "{_ROLE_LABELS["E1"]}"
  E1.class: semantic_prop
  E2: "{_ROLE_LABELS["E2"]}"
  E2.class: semantic_prop
  E3: "{_ROLE_LABELS["E3"]}"
  E3.class: semantic_prop
  P3: "{_ROLE_LABELS["P3"]}"
  P3.class: semantic_prop
}}

groups: {{
  label: "4. Legal rule groups"
  class: section

  g1: "paragraph-1 group\\n= P1 + P2\\n(2 members)"
  g1.class: group
  g2: "paragraph-2 group\\n= E1 + E2 + E3\\n(3 members)"
  g2.class: group
}}

rels: {{
  label: "5. Typed legal relationships"
  class: section

  E1n: "E1"
  E1n.class: semantic_prop
  E2n: "E2"
  E2n.class: semantic_prop
  E3n: "E3"
  E3n.class: semantic_prop
  P3n: "P3"
  P3n.class: semantic_prop
  g1n: "paragraph-1 group"
  g1n.class: group
  g2n: "paragraph-2 group"
  g2n.class: group

  E1n -> g1n: "exception_to"
  E2n -> g1n: "exception_to"
  E3n -> g1n: "exception_to"
  P3n -> g2n: "triggered_by"
}}

eff: {{
  label: "6. Effective-law projection (required context)"
  class: section

  e_p1: "P1 / P2 statements\\nreceive E1, E2, E3\\nas applicable exceptions"
  e_p1.class: det
  e_ex: "E1 / E2 / E3 statements\\nshow P1 / P2\\nas rules displaced"
  e_ex.class: det
  e_p3: "P3 statement\\nreceives E1, E2, E3\\nas trigger conditions"
  e_p3.class: det
}}

art14: {{
  label: "7. Article 14 (ordinary reference only)"
  class: section

  a14: "Article 14\\nordinary reference on E3\\nNOT an exception_to target"
  a14.class: ref
}}

e2_method: {{
  label: "8. E2 processing sequence (LLM proposal → deterministic finish)"
  class: section

  m1: "[LLM] Model-proposed candidate\\n(path 2-a-ii)"
  m1.class: llm
  m2: "[DET] Deterministic terminal composition"
  m2.class: det
  m3: "[DET] Deterministic derogation classification"
  m3.class: det
  m4: "[DET] Deterministic exception relationship"
  m4.class: det
  m5: "[DET] Deterministic group expansion\\n(exception targets paragraph-1 group)"
  m5.class: det

  m1 -> m2 -> m3 -> m4 -> m5
}}

cautions: {{
  label: "Cautions"
  class: section

  c1: "Fixture is an offline regression slice — not authoritative current law."
  c1.class: note
  c2: "Revised manifestation ≠ independently applied amendments."
  c2.class: note
  c3: "Human review remains required."
  c3.class: note
}}

hierarchy -> frontier: "coverage rules"
frontier -> props: "extract + reconcile"
props -> groups: "shared-fragment grouping"
props -> rels: "typed inference"
groups -> rels
rels -> eff: "context expansion"
props -> art14: "ordinary cross-reference"
props.E2 -> e2_method: "method detail for E2"
"""


def assert_article_49a_d2_contract(d2_text: str) -> None:
    """Validate audience-facing contract for the Article 49a diagram source."""
    for role_label in _ROLE_LABELS.values():
        if role_label.split(" — ", 1)[0] not in d2_text:
            raise AssertionError(f"Missing semantic role label in D2: {role_label}")
    for path in ("2-a-i", "2-a-ii", "2-b"):
        if path not in d2_text:
            raise AssertionError(f"Missing structured path {path!r} in D2")
    if d2_text.count("exception_to") < 3:
        raise AssertionError("Expected three exception_to edges in D2")
    if "triggered_by" not in d2_text:
        raise AssertionError("Expected triggered_by edge in D2")
    if "ordinary reference" not in d2_text.lower() and "ordinary reference" not in d2_text:
        # Labels use "ordinary reference"
        if "ordinary reference" not in d2_text:
            raise AssertionError("Article 14 must be labelled as ordinary reference")
    if "NOT an exception_to target" not in d2_text:
        raise AssertionError("Article 14 must be marked as not an exception target")
    # Opaque live IDs must not appear in visible label strings (allow comments only).
    visible = "\n".join(
        line for line in d2_text.splitlines() if not line.lstrip().startswith("#")
    )
    if re.search(r"\bprop:[0-9a-f]+\b", visible):
        raise AssertionError("Opaque proposition IDs must not appear in visible D2 labels")
    if re.search(r"\b(?:rulegrp|legalrel|lawstmt|decision):[0-9a-f]+\b", visible):
        raise AssertionError("Opaque artifact IDs must not appear in visible D2 labels")
    if "[LLM]" not in d2_text or "[DET]" not in d2_text:
        raise AssertionError("E2 method sequence must distinguish LLM from deterministic steps")
    if "Model-proposed candidate" not in d2_text:
        raise AssertionError("E2 sequence must start with model-proposed candidate")
