# Proposition-fidelity benchmark

Offline multi-instrument regression for whether Law Proposition Extractor converts structurally
parsed legislation into faithful, atomic, context-aware legal propositions.

## Distinctions

| Contract | Question |
| --- | --- |
| Structural-source fidelity | Did Law Proposition Extractor parse the source hierarchy and context correctly? |
| Proposition fidelity | Did Law Proposition Extractor represent the operative legal claims correctly? |
| Legal review | Is the interpretation acceptable for the intended legal use? |

Passing this benchmark does **not** replace legal review.

## Action fidelity

Action fidelity is based on the **legal action**, **polarity**, **legal
effect**, and **material objects**—not exact modal wording alone.

Example (Article 49a prohibited mixing):

- Source / live wording: catches “shall not be mixed”
- Gold invariant: negative `mix` action, classified as a **prohibition**,
  applying to catches

“shall not be mixed” and “must not mix” can represent the same prohibition
when predicate, polarity, legal effect, and material objects align. Active
and passive voice are treated as non-material only where semantic roles
remain preserved.

Modal differences are **not** always immaterial:

- `need not`, `should not`, and `must not` are **not** automatically equivalent
- the evaluator may disregard shall/must surface form only after confirming
  the expected legal effect and polarity

Structured `action_expectation` fields are **evaluation gold only**. They do
not alter Law Proposition Extractor proposition text, production extraction, or prompts.
Benchmark gold remains human-authored.

Legacy gold rows that only set `required_action` keep the historical
substring / token-overlap matcher (no aggressive reinterpretation).

<!-- BEGIN GENERATED: proposition-fidelity-benchmark -->

## Benchmark summary

| Metric | Value |
| --- | --- |
| cases | 8 |
| expected propositions | 18 |
| produced propositions | 18 |
| fully passing roles | 18 |
| warning roles | 0 |
| failed roles | 0 |
| unexpected propositions | 0 |
| benchmark version | 1 |

Runtime is printed on the terminal summary only (not committed), so check
mode stays deterministic across machines.

## Dimension summary

| dimension | pass | warning | fail | not applicable |
| --- | --- | --- | --- | --- |
| coverage | 26 | 0 | 0 | 0 |
| atomicity | 18 | 0 | 0 | 0 |
| no_false_merge | 18 | 0 | 0 | 0 |
| no_false_split | 19 | 0 | 0 | 0 |
| actor_fidelity | 12 | 0 | 0 | 6 |
| action_fidelity | 18 | 0 | 0 | 0 |
| object_fidelity | 18 | 0 | 0 | 0 |
| condition_fidelity | 9 | 0 | 0 | 9 |
| exception_fidelity | 6 | 0 | 0 | 12 |
| threshold_fidelity | 7 | 0 | 0 | 11 |
| cross_reference_fidelity | 3 | 0 | 0 | 15 |
| evidence_fidelity | 18 | 0 | 0 | 0 |
| structural_context_boundary | 18 | 0 | 0 | 0 |
| legal_effect_fidelity | 18 | 0 | 0 | 0 |
| completeness_fidelity | 18 | 0 | 0 | 0 |

## Fixture matrix

| case | structure | jurisdiction | heading | expected | provenance |
| --- | --- | --- | --- | --- | --- |
| `article_49a` | compound_paragraph + structured_list_derogations + trigger + headed_article | EU retained / UK | yes | 6 | reduced_real |
| `uk_regulation_12_spread` | regulation_heading + actor + prohibition + threshold + paragraph_hierarchy | UK | yes | 1 | adapted_repository_fixture |
| `uk_regulation_13_control` | exactly_one_control + unheaded_regulation | UK | no | 1 | adapted_repository_fixture |
| `wsi_regulation_36_4` | regulation_paragraph_hierarchy + record_obligation + missing_regulation_heading | Wales | no | 1 | reduced_real |
| `wsi_schedule_inspection_power` | schedule_heading + schedule_paragraph + structural_title_vs_operative | Wales | yes | 1 | adapted_repository_fixture |
| `uk_compound_spread_and_measure` | compound_obligation_style_restatement + shared_distance_condition | UK | yes | 2 | synthetic_structural_edge |
| `slurry_170kg_holding_cap` | obligation + exception + schedule_cross_reference + threshold | UK | no | 3 | adapted_repository_fixture |
| `compound_rule_exception_shared` | rule_plus_exception + shared_condition + threshold | UK | no | 3 | synthetic_structural_edge |

## Per-case table

| case | structure | expected | produced | result | material findings |
| --- | --- | --- | --- | --- | --- |
| `article_49a` | compound_paragraph + structured_list_derogations + trigger + headed_article | 6 | 6 | pass | — |
| `uk_regulation_12_spread` | regulation_heading + actor + prohibition + threshold + paragraph_hierarchy | 1 | 1 | pass | — |
| `uk_regulation_13_control` | exactly_one_control + unheaded_regulation | 1 | 1 | pass | — |
| `wsi_regulation_36_4` | regulation_paragraph_hierarchy + record_obligation + missing_regulation_heading | 1 | 1 | pass | — |
| `wsi_schedule_inspection_power` | schedule_heading + schedule_paragraph + structural_title_vs_operative | 1 | 1 | pass | accepted limitation recorded |
| `uk_compound_spread_and_measure` | compound_obligation_style_restatement + shared_distance_condition | 2 | 2 | pass | — |
| `slurry_170kg_holding_cap` | obligation + exception + schedule_cross_reference + threshold | 3 | 3 | pass | — |
| `compound_rule_exception_shared` | rule_plus_exception + shared_condition + threshold | 3 | 3 | pass | — |

## Role-level warnings and failures

None.

## Provenance notes

### `article_49a`

- Source fixture: `tests/fixtures/article_49a_legal_structure/source.xml`
- Provenance: **reduced_real** — Directly reduced from EUR 2009/1224 Article 49a offline acceptance fixture (real legislation wording).
- Locator: `article:49a`
- Response fixture prompt: v2 (reflects_prompt_v3=False); model alias `frontier_extract`

### `uk_regulation_12_spread`

- Source fixture: `tests/fixtures/structural_source/uk_regulation_headed.xml`
- Provenance: **adapted_repository_fixture** — Adapted from structural-source uk_regulation_headed.xml (UKSI-shaped offline fixture; illustrative wording, not a live CLML slice of SI 2015/668).
- Locator: `regulation:12`
- Response fixture prompt: v3 (reflects_prompt_v3=True); model alias `fixture_offline_v3_contract`

### `uk_regulation_13_control`

- Source fixture: `tests/fixtures/structural_source/uk_regulation_headed.xml`
- Provenance: **adapted_repository_fixture** — Adapted from uk_regulation_headed.xml regulation 13 (unheaded sibling control).
- Locator: `regulation:13`
- Response fixture prompt: v3 (reflects_prompt_v3=True); model alias `fixture_offline`

### `wsi_regulation_36_4`

- Source fixture: `tests/fixtures/regulation_paragraph_fragmentation/wsi_2021_77_regulation_36_live_clml.xml`
- Provenance: **reduced_real** — Reduced from WSI 2021/77 regulation 36 live-CLML offline fixture (paragraph 4 operative record duty).
- Locator: `regulation:36:paragraph:4`
- Response fixture prompt: v3 (reflects_prompt_v3=True); model alias `fixture_offline`

### `wsi_schedule_inspection_power`

- Source fixture: `tests/fixtures/regulation_paragraph_fragmentation/wsi_2021_77_regulation_36_live_clml.xml`
- Provenance: **adapted_repository_fixture** — Schedule paragraph operative power from the WSI 2021/77 offline live-CLML fixture (reduced). Schedule title is structural context, not the operative rule.
- Locator: `schedule:1:paragraph:3`
- Response fixture prompt: v3 (reflects_prompt_v3=True); model alias `fixture_offline`
- Accepted limitations: uk_schedule_1_nitrogen_descriptive_only: UK headed Schedule 1 text is descriptive calculation framing without a clear standalone operative duty; WSI schedule paragraph used instead.

### `uk_compound_spread_and_measure`

- Source fixture: `tests/fixtures/structural_source/uk_regulation_headed.xml`
- Provenance: **synthetic_structural_edge** — Synthetic offline response over the headed UK regulation 12 fixture to exercise compound-rule dimensions (prohibition + independent measurement obligation). Role id distance-measurement-restatement retained for suite stability; wording is an independently operative measurement duty so dependent-qualification suppression must not collapse it. Not presented as authoritative law.
- Locator: `regulation:12`
- Response fixture prompt: v3 (reflects_prompt_v3=True); model alias `fixture_offline`

### `slurry_170kg_holding_cap`

- Source fixture: `tests/fixtures/extraction_prompt_cases/slurry/slurry-good-simple-obligation-170kg-n.json`
- Provenance: **adapted_repository_fixture** — Adapted from slurry prompt-lab fixture slurry-good-simple-obligation-170kg-n.json (NPP regulation 7 fragment text). Offline response is fixture-authored; not a live model trace.
- Locator: `regulation:7`
- Response fixture prompt: v3 (reflects_prompt_v3=True); model alias `fixture_offline`

### `compound_rule_exception_shared`

- Source fixture: `tests/fixtures/structural_source/uk_regulation_headed.xml`
- Provenance: **synthetic_structural_edge** — Synthetic wording only for compound rule/exception/shared-condition dimensions. Not presented as authoritative law. Host XML is uk_regulation_headed.xml; operative text is fragment_text.txt override.
- Locator: `regulation:synthetic`
- Response fixture prompt: v3 (reflects_prompt_v3=True); model alias `fixture_offline`

## Known corpus gaps

- Dedicated Annex (EU) operative fixture with table-adjacent text
- SSI / NISR headed offline fixtures
- Live frontier prompt-v3 traces for non-Article-49a instruments
- UK Schedule 1 in uk_regulation_headed.xml is descriptive calculation framing only — no clear atomic operative duty suitable as gold; WSI schedule paragraph used instead
- Shared-condition representation via legal_rule_groups for dry_fragment cases (groups require full pipeline)

## Limits

- This is an **offline regression benchmark**.
- Gold contracts are curated human invariants, not authoritative law.
- Fixture responses do **not** measure current frontier-model success rate.
- Passing does **not** establish authoritative legal correctness.
- Human legal review remains required.
- Do not treat a single aggregate percentage as the acceptance signal;
  use the dimension summary above.

## Commands

```bash
just run-proposition-fidelity-benchmark
just check-proposition-fidelity-benchmark
```

<!-- END GENERATED: proposition-fidelity-benchmark -->
