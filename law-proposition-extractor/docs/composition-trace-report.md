# Composition trace report

**Date:** 2026-06-12
**Corpus:** Slurry GB principal-5 (regenerated export)
**Export:** `/Users/bram/Code/defra/ai-eu-trade-accelerator/law-proposition-extractor/runs/slurry-gb-principal-5-current-export`

Prototypes first-class **composition traces** for statements currently flagged **composition opacity**, using deterministic reconstruction from statement recipes and proposition links (no LLM).

## Executive summary

- **732** / 1415 statements carry composition opacity triggers (same class as Prompt 82 reviewability blockers).
- **480** (65.6%) become **trace-reviewable** when decomposed into ordered composition traces with role labels and provenance.
- **252** (34.4%) remain opaque: traces exist but fail reviewability gates (unknown coverage, missing context surfacing, or incomplete provenance).
- **Verdict:** Explicit composition traces eliminate composition opacity for **65.6%** of opaque statements; the remainder need better text-span alignment or context fragments, not just export packaging.

## 1. Methodology

### Opacity population

A statement is **composition-opaque** when any of:

- `high_composition` — 3+ unique linked propositions
- `standalone_status` is `context_dependent` or `partially_resolved`
- 3+ `required_context` entries
- non-empty `connector_context`

### Trace construction (deterministic)

1. `buildStatementRecipe()` — one row per proposition ref (source, supporting, required context, connector/via)
2. `buildStatementCompositionSegments()` — ordered text spans aligned to statement text
3. Role classification per fragment from ref role + `legal_effect_type` / `proposition_tier` / `presentation_role`

### Trace-reviewability gates

A trace **resolves opacity** when all hold:

- Not a single `unknown` span covering the statement
- **Structural decomposition** for multi-proposition / context-dependent statements: ≥2 non-unknown fragments, or one fragment with ≥2 proposition IDs and a `required_context` role
- **Context surfacing** for `context_dependent` / `partially_resolved` with linked context: at least one `required_context` trace fragment
- Unknown text coverage ≤ 15%
- ≥ 90% of linked propositions appear in trace fragments
- Every `required_context` proposition appears in a `required_context` trace fragment
- Every non-unknown fragment has proposition linkage and source excerpt

## 2. Population breakdown

| Opacity trigger | Statements |
| --- | ---: |
| high composition | 471 |
| context dependent | 413 |
| partially resolved | 33 |
| many required context | 16 |
| connector context | 0 |

_Triggers are non-exclusive._

### Resolution rate by trigger

| Opacity trigger | Opaque statements | Trace-reviewable | Rate |
| --- | ---: | ---: | ---: |
| high composition | 471 | 470 | 99.8% |
| context dependent | 413 | 179 | 43.3% |
| partially resolved | 33 | 16 | 48.5% |
| many required context | 16 | 15 | 93.8% |
| connector context | 0 | 0 | — |

### Trace outcome

| Outcome | Count | Share of opaque |
| --- | ---: | ---: |
| Trace-reviewable (opacity resolvable) | 480 | 65.6% |
| Trace present but blocked | 252 | 34.4% |

### Residual opacity reasons (blocked statements)

| Reason | Statements |
| --- | ---: |
| monolithic composition | 252 |
| high unknown coverage | 2 |
| missing proposition mapping | 2 |
| incomplete provenance | 2 |
| unsurfaced required context | 1 |

### Fragment role distribution (across all trace fragments)

| Role | Fragments |
| --- | ---: |
| Core proposition | 203 |
| Supporting proposition | 0 |
| Definition | 25 |
| Exception | 22 |
| Required context | 480 |
| Connector / inference | 0 |
| Unknown | 5 |

## 3. Sampled statements

15 opaque statements sampled across triggers and trace outcomes. Ordered composition traces shown below.

### Sample 1: `lawstmt:138ee3b1027c255c`

- **Standalone:** `context_dependent`
- **Triggers:** context_dependent
- **Trace-reviewable:** yes
- **Fragments:** 1; unknown coverage: 0.0%

> Incorporating organic manure and manufactured fertiliser into the soil within 12 hours of, or as soon as possible after, application is an example of a reasonable precaution for the purposes of compliance with regulation 4(3).

**Composition trace:**

1. **Required context** `0–226` — Incorporating organic manure and manufactured fertiliser into the soil within 12 hours of, or as soon as possible after… _(props: prop:7bcf96772813b4f1, prop:c5c6b83bddffd553; locators: regulation 4(3); excerpt: present)_

### Sample 2: `lawstmt:31bd9b71d470d467`

- **Standalone:** `context_dependent`
- **Triggers:** context_dependent
- **Trace-reviewable:** yes
- **Fragments:** 1; unknown coverage: 0.0%

> For the purposes of regulation 10(5), 'land management and cultivation practices' includes irrigating crops or spraying them with pesticides, herbicides or fungicides.

**Composition trace:**

1. **Required context** `0–167` — For the purposes of regulation 10(5), 'land management and cultivation practices' includes irrigating crops or spraying… _(props: prop:1dc0a9ba773bf95f, prop:96f3a42999a65e36; locators: regulation 10(5); excerpt: present)_

### Sample 3: `lawstmt:022b9a6fec8ccef2`

- **Standalone:** `context_dependent`
- **Triggers:** context_dependent
- **Trace-reviewable:** no (monolithic_composition)
- **Fragments:** 1; unknown coverage: 0.0%

> The Secretary of State must make adequate arrangements to enable the public to prepare and participate effectively in the review.

**Composition trace:**

1. **Core proposition** `0–129` — The Secretary of State must make adequate arrangements to enable the public to prepare and participate effectively in t… _(props: prop:3345c7503e28326f; locators: —; excerpt: present)_

### Sample 4: `lawstmt:029914423a5c5021`

- **Standalone:** `context_dependent`
- **Triggers:** context_dependent
- **Trace-reviewable:** no (monolithic_composition)
- **Fragments:** 1; unknown coverage: 0.0%

> Where paragraph (4)(b) applies, storage facilities for an additional one week's manure must be provided as a contingency measure in the event that spreading is not possible on some dates.

**Composition trace:**

1. **Core proposition** `0–187` — Where paragraph (4)(b) applies, storage facilities for an additional one week's manure must be provided as a contingenc… _(props: prop:09266dbb071b84a3; locators: —; excerpt: present)_

### Sample 5: `lawstmt:3a964ef07e332c4a`

- **Standalone:** `partially_resolved`
- **Triggers:** partially_resolved, many_required_context
- **Trace-reviewable:** yes
- **Fragments:** 1; unknown coverage: 0.0%

> For the purposes of regulation 36(2), paragraph 2(b) of Annex 3 to Council Directive 91/676/EEC is to be read as if the third subparagraph were omitted.

**Composition trace:**

1. **Required context** `0–152` — For the purposes of regulation 36(2), paragraph 2(b) of Annex 3 to Council Directive 91/676/EEC is to be read as if the… _(props: prop:9d18b1619412d0b3, prop:06ecd0c9491cdde6; locators: paragraph 2, regulation 36(2); excerpt: present)_

### Sample 6: `lawstmt:0e34c64386553bcb`

- **Standalone:** `partially_resolved`
- **Triggers:** partially_resolved
- **Trace-reviewable:** no (monolithic_composition)
- **Fragments:** 1; unknown coverage: 0.0%

> "Derogation" means a derogation granted under this Part from the limit on the total amount of nitrogen in livestock manure that can be applied to land each year in accordance with paragraph 2(b) of Annex III to Council Directive 91/676/EEC.

**Composition trace:**

1. **Definition** `0–240` — "Derogation" means a derogation granted under this Part from the limit on the total amount of nitrogen in livestock man… _(props: prop:06ecd0c9491cdde6, prop:9d18b1619412d0b3; locators: —; excerpt: present)_

### Sample 7: `lawstmt:1081be6063de27cb`

- **Standalone:** `partially_resolved`
- **Triggers:** partially_resolved
- **Trace-reviewable:** no (monolithic_composition)
- **Fragments:** 1; unknown coverage: 0.0%

> In the case of permanent grassland, the occupier must comply with the duties under paragraph 3(1) in each calendar year before spreading phosphate fertiliser.

**Composition trace:**

1. **Core proposition** `0–158` — In the case of permanent grassland, the occupier must comply with the duties under paragraph 3(1) in each calendar year… _(props: prop:9f9a73758310fd56; locators: —; excerpt: present)_

### Sample 8: `lawstmt:01a80b20889c33f1`

- **Standalone:** `context_dependent`
- **Triggers:** high_composition, context_dependent
- **Trace-reviewable:** yes
- **Fragments:** 1; unknown coverage: 0.0%

> SEPA shall withdraw, extend, or modify a notice under regulation 8(5) if directed to do so by the Scottish Ministers under regulation 9(5).

**Composition trace:**

1. **Required context** `0–139` — SEPA shall withdraw, extend, or modify a notice under regulation 8(5) if directed to do so by the Scottish Ministers un… _(props: prop:565937b2eec031ef, prop:3bbb1f05c635891a, prop:4545b43fd4b1d0a5, prop:7c1379b82c60e3c4, prop:aebfcc952d5c0716, prop:c1426a1e74c7c350, prop:1f17bcb6cd04200f, prop:0e64a774a712d58e; locators: regulation 8(5), regulation 9(5); excerpt: present)_

### Sample 9: `lawstmt:01dd1df2d41109e0`

- **Standalone:** `fragmentary`
- **Triggers:** high_composition
- **Trace-reviewable:** yes
- **Fragments:** 1; unknown coverage: 0.0%

> Fuel oil storage areas must comply with the requirements set out in Schedule 3.

**Composition trace:**

1. **Required context** `0–79` — Fuel oil storage areas must comply with the requirements set out in Schedule 3. _(props: prop:a6a3db69e51ced62, prop:b0be359c700e0081, prop:170f9d614f353a29, prop:7c69cd597536c9b3, prop:008ef6cdd76e9148, prop:e3d0d081e957dc82, prop:7adeae6e20097049, prop:a0cafb1fc3190ebe, prop:2e41e99927241f1d, prop:622a6b6e9ce2e295, prop:c2909862335debde, prop:f28e133ab973f96c; locators: schedule 3; excerpt: present)_

### Sample 10: `lawstmt:8761d3219f9bbae8`

- **Standalone:** `standalone`
- **Triggers:** high_composition
- **Trace-reviewable:** no (monolithic_composition, high_unknown_coverage, missing_proposition_mapping, unsurfaced_required_context, incomplete_provenance)
- **Fragments:** 2; unknown coverage: 100.0%

> Regulation 31 does not apply where, in any calendar year, (a) the requirements under regulation 31(5) are met, and (b) the occupier makes a record demonstrating that they are met. The requirements under regulation 31(5) are that throughout the year: (a) at least 80% of the holding's agricultural ar…

**Composition trace:**

1. **Unknown** `0–180` — Regulation 31 does not apply where, in any calendar year, (a) the requirements under regulation 31(5) are met, and (b) … _(props: —; locators: —; excerpt: missing)_
2. **Unknown** `180–563` — The requirements under regulation 31(5) are that throughout the year: (a) at least 80% of the holding's agricultural ar… _(props: —; locators: —; excerpt: missing)_

### Sample 11: `lawstmt:02903d9bcb2a1f03`

- **Standalone:** `standalone`
- **Triggers:** high_composition
- **Trace-reviewable:** yes
- **Fragments:** 1; unknown coverage: 0.0%

> For each area planted or intended to be planted, the nutrient management plan must record the soil nitrogen supply calculated in accordance with regulation 6(1) and the method used to establish that figure.

**Composition trace:**

1. **Required context** `0–206` — For each area planted or intended to be planted, the nutrient management plan must record the soil nitrogen supply calc… _(props: prop:dcb84df61fabd600, prop:f039a29182a40e3d, prop:909d275b41ea21dd, prop:8210056fc23cd9cd; locators: regulation 6(1); excerpt: present)_

### Sample 12: `lawstmt:030a536762dc5059`

- **Standalone:** `context_dependent`
- **Triggers:** high_composition, context_dependent
- **Trace-reviewable:** yes
- **Fragments:** 1; unknown coverage: 0.0%

> A silo must either comply with the provisions of Schedule 1, or be designed and constructed in accordance with BS 5502 (parts relating to Cylindrical Forage Towers).

**Composition trace:**

1. **Required context** `0–165` — A silo must either comply with the provisions of Schedule 1, or be designed and constructed in accordance with BS 5502 … _(props: prop:bc3aee98801090d8, prop:a24a904922d66466, prop:556f7a6f89a5b18c, prop:cc5cd22a0b29f8a9, prop:14e6ca0f1e5f8cf1, prop:08e211add43f94a7, prop:1b3fa51c77f3d2d6, prop:b29aca6f0598c9fa, prop:3f3fc86f01eebcaa, prop:2cfdd66fb6752bf6, prop:3fd65493a5b9b52d, prop:949a5cca66961ffd, prop:45d8a80188ea2036, prop:243ddb5752cd66c3, prop:82b600d06fff2311; locators: schedule 1; excerpt: present)_

### Sample 13: `lawstmt:040001c967a640a6`

- **Standalone:** `standalone`
- **Triggers:** high_composition
- **Trace-reviewable:** yes
- **Fragments:** 1; unknown coverage: 0.0%

> Before 30th April each year, the occupier of a holding with livestock must record for the previous storage period the number of animals in a building or hardstanding on the holding during that period and the category for each animal by reference to Schedule 1.

**Composition trace:**

1. **Required context** `0–260` — Before 30th April each year, the occupier of a holding with livestock must record for the previous storage period the n… _(props: prop:115cb6afd8c5578d, prop:00bad868a6dd8365, prop:7f3bf329ab870da0, prop:b5bfe4b27103d0e5, prop:5f2f1a02f088417b; locators: schedule 1; excerpt: present)_

### Sample 14: `lawstmt:04c567b56533e739`

- **Standalone:** `context_dependent`
- **Triggers:** high_composition, context_dependent
- **Trace-reviewable:** yes
- **Fragments:** 1; unknown coverage: 0.0%

> The amount of nitrogen produced by livestock must be calculated in accordance with Schedule 1.

**Composition trace:**

1. **Required context** `0–94` — The amount of nitrogen produced by livestock must be calculated in accordance with Schedule 1. _(props: prop:28d95e5dd8818886, prop:39e23189039fc1b6, prop:05d2632d0c5a8130, prop:21e6cef188deb8f9, prop:3b8f3c1051205056; locators: schedule 1; excerpt: present)_

### Sample 15: `lawstmt:052448652136cca3`

- **Standalone:** `standalone`
- **Triggers:** high_composition
- **Trace-reviewable:** yes
- **Fragments:** 1; unknown coverage: 0.0%

> Before 30 April each year, the occupier of a holding with livestock must record, for the previous storage period referred to in regulation 29, the number and category of animals in a building or on a hardstanding during that storage period.

**Composition trace:**

1. **Required context** `0–240` — Before 30 April each year, the occupier of a holding with livestock must record, for the previous storage period referr… _(props: prop:6c5b57cc2b54172b, prop:3b7cb873eeb1ff69, prop:f3ca2ba1257a4515, prop:f703f77afee974c4, prop:da64b96f67d8c96a, prop:c3db9989546d68e1, prop:a26ee7da7f787ffb, prop:f2f127fa77f9b1ba, prop:a3e95bc09c147915, prop:0bd2f787ce0cbc8a, prop:94250913541aa526, prop:b31f7ec2f517dc43, prop:7e03c4c446af90b7; locators: regulation 29; excerpt: present)_

## 4. Findings

1. **Traces are buildable today** from existing export fields — no LLM required. Current export has no `statement_recipe` or `composition_trace`; workbench derives recipes from proposition links.
2. **65.6% resolvable** — explicit traces clear composition opacity only where structural decomposition and context surfacing already succeed; monolithic single-fragment traces do not count.
3. **Dominant residual blocker:** `monolithic_composition` (252 statements) — most opaque statements collapse to one source-proposition span; context and supporting propositions are linked in metadata but not text-positioned.
4. **High-composition statements** with multiple proposition refs in one aligned span can pass when `required_context` role is assigned — but `context_dependent` statements without `required_context` fragments remain monolithic.
5. **Exporting traces is necessary but not sufficient** — pipeline must also emit `statement_fragments` with text-aligned spans per proposition, or opacity persists despite trace metadata.

## 5. Proposed export extension

### Schema

Add optional `composition_trace` to each `effective_law_statements` entry:

```json
{
  "composition_trace": [
    {
      "order": 0,
      "text": "fragment text as it appears in statement_text",
      "start": 0,
      "end": 42,
      "role": "core_proposition",
      "proposition_ids": [
        "prop-abc"
      ],
      "context_locators": [],
      "source_locator": "SI 2010/2211, reg 4(1)",
      "source_excerpt": "verbatim excerpt from source fragment",
      "support_status": "supported"
    }
  ]
}
```

**`role` enum:** `core_proposition` | `supporting_proposition` | `definition` | `exception` | `required_context` | `connector_inference` | `unknown`

**Invariants:**

- Fragments are ordered; `start`/`end` are half-open offsets into `statement_text`
- `text` must equal `statement_text.slice(start, end)`
- `proposition_ids` must be subset of statement's linked propositions
- `required_context` fragments must include `context_locators` from `required_context`

### Migration strategy

1. **Phase 0 (now):** Workbench computes traces client-side via `buildCompositionTrace()` — no export change.
2. **Phase 1:** Pipeline emits `composition_trace` on export using the same deterministic functions (shared TS module or Python port).
3. **Phase 2:** Backfill existing runs on read; `statement_recipe` remains the per-proposition row view, `composition_trace` is the ordered text-span view.
4. **Phase 3:** Use trace quality gates in `run_quality_summary` — count `trace_reviewable` vs `composition_opaque` per run.

### Workbench rendering implications

- **Statement review panel:** Render `composition_trace` as the primary highlighted text (replacing derived `buildStatementCompositionSegments` when export field present).
- **Role colours:** Map roles to existing segment surface classes — core/supporting → composition source; required_context → assessment context; unknown → dashed inferred.
- **Inspector stack:** Click fragment → scroll proposition stack filtered to `proposition_ids`; show `source_excerpt` inline.
- **Queue filters:** Add "trace-blocked" preset for statements where `composition_trace` exists but fails reviewability gates.
- **No regression:** When `composition_trace` absent, keep current derived path (`buildStatementRecipe` + `buildStatementCompositionSegments`).

## Methodology notes

- Export analysed: `runs/slurry-gb-principal-5-current-export`
- Functions: `buildStatementRecipe`, `buildStatementCompositionSegments`, `propositionRefsForStatement`
- Re-run: `uv run --package law-proposition-extractor-pipeline python scripts/generate_composition_trace_report.py`

