# Context-dependent construction report

**Date:** 2026-06-12
**Corpus:** Slurry GB principal-5 (regenerated export)
**Export:** `/Users/bram/Code/defra/ai-eu-trade-accelerator/law-proposition-extractor/runs/slurry-gb-principal-5-current-export`

Deterministic comparison of **effective-law statement text**, **core proposition text**, and **required_context** propositions/fragments for `context_dependent` and trace-blocked statements (no LLM).

## Executive summary

- **413** / 1415 statements are `context_dependent`.
- **179** (43.3%) are already **trace-reviewable**; **234** (56.7%) are **trace-blocked**.
- **168** (40.7%) have a **material incorporation gap** — required context is not already present in statement/core text.
- **0** trace-blocked statements (0.0% of blocked) are **structural incorporation candidates** — material resolved context absent from statement text, blocked only by monolithic/unsurfaced-context trace gates.
- **0** pass strict post-inline trace simulation (0.0% of blocked); naive text append alone does not realign composition fragments.
- **413** statements are verbatim (or near-verbatim) copies of the core proposition — effective-law generation is not composing additional wording today.
- **Recommendation:** **inline context selectively** for resolved material context with incorporation gaps; **keep external** for confirm/noise-only dependencies; **defer to reviewer** when context remains unresolved; **emit multiple statements** when several independent substantive context propositions apply.

## 1. Methodology

### Population

- All `effective_law_statements` with `standalone_status = context_dependent`.
- **Trace-blocked** subset: context-dependent statements failing composition-trace reviewability gates (same deterministic logic as Prompt 83 composition trace report).

### Per-statement comparison

For each statement:

1. **Core proposition** — `source_proposition_ids[0]` → `propositions.json` text and `legal_effect_type`.
2. **Effective statement** — `statement_text` (today identical to core proposition text in almost all cases).
3. **Required context** — each `required_context` entry: `kind`, `locator`, `resolution_status`, linked proposition text, fragment excerpt.

### Context role classification (deterministic, per entry)

| Role | Rule |
| --- | --- |
| a) confirm | Context proposition text already contained in statement or core text; or unresolved locator already cited in statement |
| b) constrain | `host_rule` / `incorporated_rule` / `incorporated_factors`; or condition markers in context absent from core |
| c) exception | `legal_effect_type = derogation` or exception/unless markers in context text |
| d) definition | `legal_effect_type = definition`, `proposition_tier = definitional_rule`, or `kind = supporting_definition` |
| e) alter effect | Resolved context with different substantive `legal_effect_type` from core |
| f) noise | Unresolved context with no linked propositions and no material locator signal |

Statement-level primary role = most severe entry role (alter > exception > definition > constrain > confirm > noise).

### Incorporation gap

A statement has an incorporation gap when any context entry has a **material role** (b–e) and its proposition text is **not** already contained in the statement or core text.

### Simulated inlining (reviewability estimate)

Hypothetical `statement_text` = core text + unresolved material context proposition texts (deduplicated). Re-run composition-trace reviewability gates. Count statements that are trace-blocked today but trace-reviewable after simulation.

## 2. Population breakdown

| Metric | Count |
| --- | ---: |
| Context-dependent statements | 413 |
| Trace-reviewable | 179 |
| Trace-blocked | 234 |
| Statement text matches core proposition | 413 |
| No resolved context propositions | 8 |
| Material incorporation gap | 168 |
| Incorporation candidates (gap + resolved context) | 168 |
| — already trace-reviewable | 168 |
| — trace-blocked | 0 |
| Structural reviewability gain if inlined (blocked only) | 0 |
| Strict post-inline trace pass (blocked only) | 0 |

### Context entry roles (non-exclusive across entries)

| Role | Entries |
| --- | ---: |
| a) merely confirm | 25 |
| b) materially constrain | 132 |
| c) introduce exceptions | 21 |
| d) introduce definitions | 45 |
| e) alter legal effect | 19 |
| f) irrelevant noise | 5 |

### Statement primary context role

| Role | Statements |
| --- | ---: |
| a) merely confirm | 17 |
| b) materially constrain | 94 |
| c) introduce exceptions | 21 |
| d) introduce definitions | 35 |
| e) alter legal effect | 19 |
| f) irrelevant noise | 227 |

### Incorporation recommendations

| Recommendation | Statements |
| --- | ---: |
| keep context external | 243 |
| inline context selectively | 138 |
| emit multiple statements | 30 |
| defer to reviewer | 2 |

## 3. Findings

1. **Effective-law statements do not incorporate context into wording.** 413 / 413 statements match the core proposition text exactly; export transform copies `proposition_text` verbatim and leaves `required_context` external.
2. **Most context dependence is locator citation, not missing inline text.** 25 context entries are classified as confirmatory (locator cited in statement or context text already present).
3. **Material gaps with resolved context are already trace-reviewable.** 168 / 168 incorporation candidates pass trace gates today without inlining; 0 blocked candidates remain. Trace-blocked context-dependence is primarily **unresolved locators**, not missing inline wording.
4. **Unresolved context dominates trace-blocked cases.** 8 context-dependent statements have zero resolved `required_context.proposition_ids` — inlining cannot help until locator resolution improves.
5. **Selective inlining is sufficient; full composition is not.** 30 statements warrant multiple emitted statements; 2 should defer to reviewer while locators remain unresolved.

## 4. Sampled statements

14 statements sampled across incorporation recommendations and context roles.

### Sample 1: `lawstmt:07e0f1c97943e1e8`

- **Standalone:** `context_dependent`
- **Trace-reviewable:** yes
- **Primary context role:** b) materially constrain
- **Recommendation:** inline context selectively
- **Incorporation gap:** yes
- **Structural incorporation candidate:** no
- **Strict post-inline trace pass:** no

**Effective statement:**

> For the purposes of paragraph (5), the total amount of nitrogen in organic manure is to be calculated by reference to the methods described in regulation 14.

**Core proposition:**

> For the purposes of paragraph (5), the total amount of nitrogen in organic manure is to be calculated by reference to the methods described in regulation 14. _(effect: obligation)_

**Required context:**

| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |
| --- | --- | --- | --- | :---: | --- |
| regulation 14 | referenced_locator | resolved | b) materially constrain | no | In relation to livestock manure, the nitrogen content must be calculated either by using the standa… |

**Simulated inlined statement:**

> For the purposes of paragraph (5), the total amount of nitrogen in organic manure is to be calculated by reference to the methods described in regulation 14. In relation to livestock manure, the nitrogen content must be calculated either by using the standard table in Part 1 of Schedule 2 or by sampling and analysis i…

### Sample 2: `lawstmt:01a80b20889c33f1`

- **Standalone:** `context_dependent`
- **Trace-reviewable:** yes
- **Primary context role:** b) materially constrain
- **Recommendation:** emit multiple statements
- **Incorporation gap:** yes
- **Structural incorporation candidate:** no
- **Strict post-inline trace pass:** no

**Effective statement:**

> SEPA shall withdraw, extend, or modify a notice under regulation 8(5) if directed to do so by the Scottish Ministers under regulation 9(5).

**Core proposition:**

> SEPA shall withdraw, extend, or modify a notice under regulation 8(5) if directed to do so by the Scottish Ministers under regulation 9(5). _(effect: obligation)_

**Required context:**

| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |
| --- | --- | --- | --- | :---: | --- |
| regulation 8(5) | host_rule | resolved | b) materially constrain | no | SEPA may at any time withdraw a notice served under regulation 8. |
| regulation 9(5) | host_rule | resolved | b) materially constrain | no | On determining an appeal under regulation 9, the Scottish Ministers may direct SEPA to withdraw the… |

**Simulated inlined statement:**

> SEPA shall withdraw, extend, or modify a notice under regulation 8(5) if directed to do so by the Scottish Ministers under regulation 9(5). SEPA may at any time withdraw a notice served under regulation 8. On determining an appeal under regulation 9, the Scottish Ministers may direct SEPA to withdraw the notice.

### Sample 3: `lawstmt:1fd0dc801dba46c1`

- **Standalone:** `context_dependent`
- **Trace-reviewable:** yes
- **Primary context role:** e) alter legal effect
- **Recommendation:** emit multiple statements
- **Incorporation gap:** yes
- **Structural incorporation candidate:** no
- **Strict post-inline trace pass:** no

**Effective statement:**

> For the purposes of regulation 8, the total amount of nitrogen in organic manure must be calculated by reference to the methods described in regulation 14.

**Core proposition:**

> For the purposes of regulation 8, the total amount of nitrogen in organic manure must be calculated by reference to the methods described in regulation 14. _(effect: obligation)_

**Required context:**

| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |
| --- | --- | --- | --- | :---: | --- |
| regulation 8 | host_rule | resolved | e) alter legal effect | no | The occupier of a holding must ensure that in any twelve-month period, the total amount of nitrogen… |
| regulation 14 | referenced_locator | resolved | b) materially constrain | no | In relation to livestock manure, the nitrogen content must be calculated either by using the standa… |

**Simulated inlined statement:**

> For the purposes of regulation 8, the total amount of nitrogen in organic manure must be calculated by reference to the methods described in regulation 14. The occupier of a holding must ensure that in any twelve-month period, the total amount of nitrogen in organic manure spread on any given hectare of land on the ho…

### Sample 4: `lawstmt:c028a995869c1ac1`

- **Standalone:** `context_dependent`
- **Trace-reviewable:** no
- **Trace blockers:** monolithic_composition
- **Primary context role:** a) merely confirm
- **Recommendation:** defer to reviewer
- **Incorporation gap:** no
- **Structural incorporation candidate:** no
- **Strict post-inline trace pass:** no

**Effective statement:**

> The reference to a record required to be made under these Regulations includes a reference to a record required to be made under the Nitrate Pollution Prevention Regulations 2008 in relation to which regulation 45 of those Regulations had effect immediately before the commenceme…

**Core proposition:**

> The reference to a record required to be made under these Regulations includes a reference to a record required to be made under the Nitrate Pollution Prevention Regulations 2008 in relation to which regulation 45 of those Regulations had effect immediately before the commenceme… _(effect: commencement)_

**Required context:**

| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |
| --- | --- | --- | --- | :---: | --- |
| regulation 45 | referenced_locator | unresolved | a) merely confirm | no | regulation 45 |

### Sample 5: `lawstmt:e224333102a62358`

- **Standalone:** `context_dependent`
- **Trace-reviewable:** no
- **Trace blockers:** monolithic_composition
- **Primary context role:** a) merely confirm
- **Recommendation:** defer to reviewer
- **Incorporation gap:** no
- **Structural incorporation candidate:** no
- **Strict post-inline trace pass:** no

**Effective statement:**

> A silo must comply with the provisions of Schedule 5 in order to satisfy the requirement imposed in relation to it.

**Core proposition:**

> A silo must comply with the provisions of Schedule 5 in order to satisfy the requirement imposed in relation to it. _(effect: obligation)_

**Required context:**

| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |
| --- | --- | --- | --- | :---: | --- |
| schedule 5 | referenced_locator | unresolved | a) merely confirm | no | schedule 5 |

### Sample 6: `lawstmt:022b9a6fec8ccef2`

- **Standalone:** `context_dependent`
- **Trace-reviewable:** no
- **Trace blockers:** monolithic_composition
- **Primary context role:** f) irrelevant noise
- **Recommendation:** keep context external
- **Incorporation gap:** no
- **Structural incorporation candidate:** no
- **Strict post-inline trace pass:** no

**Effective statement:**

> The Secretary of State must make adequate arrangements to enable the public to prepare and participate effectively in the review.

**Core proposition:**

> The Secretary of State must make adequate arrangements to enable the public to prepare and participate effectively in the review. _(effect: obligation)_

**Required context:**

| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |
| --- | --- | --- | --- | :---: | --- |

### Sample 7: `lawstmt:029914423a5c5021`

- **Standalone:** `context_dependent`
- **Trace-reviewable:** no
- **Trace blockers:** monolithic_composition
- **Primary context role:** f) irrelevant noise
- **Recommendation:** keep context external
- **Incorporation gap:** no
- **Structural incorporation candidate:** no
- **Strict post-inline trace pass:** no

**Effective statement:**

> Where paragraph (4)(b) applies, storage facilities for an additional one week's manure must be provided as a contingency measure in the event that spreading is not possible on some dates.

**Core proposition:**

> Where paragraph (4)(b) applies, storage facilities for an additional one week's manure must be provided as a contingency measure in the event that spreading is not possible on some dates. _(effect: obligation)_

**Required context:**

| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |
| --- | --- | --- | --- | :---: | --- |

### Sample 8: `lawstmt:09149c28263e2529`

- **Standalone:** `context_dependent`
- **Trace-reviewable:** yes
- **Primary context role:** e) alter legal effect
- **Recommendation:** inline context selectively
- **Incorporation gap:** yes
- **Structural incorporation candidate:** no
- **Strict post-inline trace pass:** no

**Effective statement:**

> The occupier must ensure that the total amount of phosphate from manufactured phosphate fertiliser and phosphate from organic manure spread in the growing season does not, during the relevant period, exceed the limits set out in paragraph 9, irrespective of the figure recorded i…

**Core proposition:**

> The occupier must ensure that the total amount of phosphate from manufactured phosphate fertiliser and phosphate from organic manure spread in the growing season does not, during the relevant period, exceed the limits set out in paragraph 9, irrespective of the figure recorded i… _(effect: obligation)_

**Required context:**

| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |
| --- | --- | --- | --- | :---: | --- |
| paragraph 9 | incorporated_rule | resolved | e) alter legal effect | no | The total amount of phosphate spread on any crop listed in Table 2 (grass) or Table 3 (other crops)… |
| paragraph 7(2) | host_rule | unresolved | a) merely confirm | no | paragraph 7(2) |

**Simulated inlined statement:**

> The occupier must ensure that the total amount of phosphate from manufactured phosphate fertiliser and phosphate from organic manure spread in the growing season does not, during the relevant period, exceed the limits set out in paragraph 9, irrespective of the figure recorded in the enhanced nutrient management plan …

### Sample 9: `lawstmt:0997ae8a20135443`

- **Standalone:** `context_dependent`
- **Trace-reviewable:** yes
- **Primary context role:** d) introduce definitions
- **Recommendation:** inline context selectively
- **Incorporation gap:** yes
- **Structural incorporation candidate:** no
- **Strict post-inline trace pass:** no

**Effective statement:**

> A report under regulation 40A(1) must contain the map published under regulation 3(2), accompanied by a statement detailing the nature of, and reasons for, any revisions to the designated nitrate vulnerable zone since the end of the previous reporting period.

**Core proposition:**

> A report under regulation 40A(1) must contain the map published under regulation 3(2), accompanied by a statement detailing the nature of, and reasons for, any revisions to the designated nitrate vulnerable zone since the end of the previous reporting period. _(effect: obligation)_

**Required context:**

| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |
| --- | --- | --- | --- | :---: | --- |
| regulation 40a(1) | host_rule | resolved | b) materially constrain | no | The Secretary of State must prepare a report on the implementation of these Regulations for each re… |
| regulation 3(2) | host_rule | resolved | d) introduce definitions | no | For the period beginning with 1st December 2016 and ending with the day on which the Secretary of S… |

**Simulated inlined statement:**

> A report under regulation 40A(1) must contain the map published under regulation 3(2), accompanied by a statement detailing the nature of, and reasons for, any revisions to the designated nitrate vulnerable zone since the end of the previous reporting period. The Secretary of State must prepare a report on the impleme…

### Sample 10: `lawstmt:030a536762dc5059`

- **Standalone:** `context_dependent`
- **Trace-reviewable:** yes
- **Primary context role:** a) merely confirm
- **Recommendation:** keep context external
- **Incorporation gap:** no
- **Structural incorporation candidate:** no
- **Strict post-inline trace pass:** no

**Effective statement:**

> A silo must either comply with the provisions of Schedule 1, or be designed and constructed in accordance with BS 5502 (parts relating to Cylindrical Forage Towers).

**Core proposition:**

> A silo must either comply with the provisions of Schedule 1, or be designed and constructed in accordance with BS 5502 (parts relating to Cylindrical Forage Towers). _(effect: obligation)_

**Required context:**

| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |
| --- | --- | --- | --- | :---: | --- |
| BS 5502 | external_standard_reference | external_reference | a) merely confirm | no | BS 5502 |
| schedule 1 | referenced_locator | resolved | a) merely confirm | yes | A silo must either comply with the provisions of Schedule 1, or be designed and constructed in acco… |

### Sample 11: `lawstmt:04c567b56533e739`

- **Standalone:** `context_dependent`
- **Trace-reviewable:** yes
- **Primary context role:** a) merely confirm
- **Recommendation:** keep context external
- **Incorporation gap:** no
- **Structural incorporation candidate:** no
- **Strict post-inline trace pass:** no

**Effective statement:**

> The amount of nitrogen produced by livestock must be calculated in accordance with Schedule 1.

**Core proposition:**

> The amount of nitrogen produced by livestock must be calculated in accordance with Schedule 1. _(effect: obligation)_

**Required context:**

| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |
| --- | --- | --- | --- | :---: | --- |
| schedule 1 | referenced_locator | resolved | a) merely confirm | no | The daily manure, nitrogen and phosphate production figures for grazing livestock set out in Table … |

### Sample 12: `lawstmt:073a09628c75ef28`

- **Standalone:** `context_dependent`
- **Trace-reviewable:** no
- **Trace blockers:** monolithic_composition
- **Primary context role:** f) irrelevant noise
- **Recommendation:** keep context external
- **Incorporation gap:** no
- **Structural incorporation candidate:** no
- **Strict post-inline trace pass:** no

**Effective statement:**

> Having carried out a review, the Secretary of State must set out the conclusions in a report and publish the report; the report must set out the objectives intended to be achieved by these Regulations, include an assessment of the extent to which those objectives are being achie…

**Core proposition:**

> Having carried out a review, the Secretary of State must set out the conclusions in a report and publish the report; the report must set out the objectives intended to be achieved by these Regulations, include an assessment of the extent to which those objectives are being achie… _(effect: obligation)_

**Required context:**

| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |
| --- | --- | --- | --- | :---: | --- |

### Sample 13: `lawstmt:08fb7b6ddb7dfec7`

- **Standalone:** `context_dependent`
- **Trace-reviewable:** yes
- **Primary context role:** b) materially constrain
- **Recommendation:** inline context selectively
- **Incorporation gap:** yes
- **Structural incorporation candidate:** no
- **Strict post-inline trace pass:** no

**Effective statement:**

> A review carried out under regulation 16 must, so far as is reasonable, have regard to how Article 11(3)(h) of Directive 2000/60/EC is implemented in other member States.

**Core proposition:**

> A review carried out under regulation 16 must, so far as is reasonable, have regard to how Article 11(3)(h) of Directive 2000/60/EC is implemented in other member States. _(effect: obligation)_

**Required context:**

| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |
| --- | --- | --- | --- | :---: | --- |
| regulation 16 | host_rule | resolved | b) materially constrain | no | The Secretary of State must from time to time carry out a review of the regulatory provision contai… |
| article 11(3) | incorporated_rule | unresolved | a) merely confirm | no | article 11(3) |

**Simulated inlined statement:**

> A review carried out under regulation 16 must, so far as is reasonable, have regard to how Article 11(3)(h) of Directive 2000/60/EC is implemented in other member States. The Secretary of State must from time to time carry out a review of the regulatory provision contained in these Regulations and publish a report set…

### Sample 14: `lawstmt:096842c64ece19b4`

- **Standalone:** `context_dependent`
- **Trace-reviewable:** yes
- **Primary context role:** b) materially constrain
- **Recommendation:** inline context selectively
- **Incorporation gap:** yes
- **Structural incorporation candidate:** no
- **Strict post-inline trace pass:** no

**Effective statement:**

> A person who applies organic manure onto the surface of bare soil or stubble (other than soil that has been sown) must ensure that the organic manure is incorporated into the soil in accordance with regulation 19.

**Core proposition:**

> A person who applies organic manure onto the surface of bare soil or stubble (other than soil that has been sown) must ensure that the organic manure is incorporated into the soil in accordance with regulation 19. _(effect: obligation)_

**Required context:**

| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |
| --- | --- | --- | --- | :---: | --- |
| regulation 19 | referenced_locator | resolved | b) materially constrain | no | A person who applies organic manure on to the surface of bare soil or stubble (other than soil that… |

**Simulated inlined statement:**

> A person who applies organic manure onto the surface of bare soil or stubble (other than soil that has been sown) must ensure that the organic manure is incorporated into the soil in accordance with regulation 19. A person who applies organic manure on to the surface of bare soil or stubble (other than soil that has b…

## 5. Recommendations for effective-law generation

| Strategy | When | Rationale |
| --- | --- | --- |
| **Keep context external** | 243 statements | Confirmatory or noise-only context; statement already cites locators or text is present |
| **Inline context selectively** | 138 statements | Resolved material context (constrain/exception/definition) not yet in statement text |
| **Emit multiple statements** | 30 statements | Multiple independent substantive context propositions — single sentence would over-compose |
| **Defer to reviewer** | 2 statements | Unresolved locators; inlining would fabricate law |

### Proposed pipeline behaviour

1. **Default:** Keep `statement_text` as core proposition text; attach `required_context` metadata (current behaviour).
2. **When resolved + material gap:** Append or clause-merge resolved context proposition text into `statement_text`; mark `standalone_status` → `standalone` or `partially_resolved` depending on remaining unresolved entries.
3. **When multiple substantive contexts:** Emit sibling statements sharing provenance rather than one compound sentence.
4. **When unresolved:** Retain `context_dependent`; surface locators in review UI; do not inline.
5. **Do not use LLM composition** — all incorporation decisions are deterministic from proposition text, `legal_effect_type`, `required_context.kind`, and resolution status.

## Methodology notes

- Export analysed: `runs/slurry-gb-principal-5-current-export`
- Functions: `analyzeContextDependentConstruction`, `assessCompositionTrace`, proposition/fragment joins
- Re-run: `uv run --package law-proposition-extractor-pipeline python scripts/generate_context_dependent_construction_report.py`

