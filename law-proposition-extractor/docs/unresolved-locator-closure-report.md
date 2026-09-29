# Unresolved locator closure report

**Date:** 2026-06-12
**Corpus:** Slurry GB principal-5 (regenerated export)
**Export:** `/Users/bram/Code/defra/ai-eu-trade-accelerator/law-proposition-extractor/runs/slurry-gb-principal-5-current-export`

Deterministic analysis of **unresolved `required_context` locators** on `context_dependent` and trace-blocked statements. Classifies closure blockers without LLM inference.

## Executive summary

- **319** unresolved required-context locator entries in focus population.
- **413** context-dependent statements; **419** trace-blocked statements (non-exclusive).
- **268** (84.0%) are **Review Workbench–resolvable** despite empty export `proposition_ids` — export pipeline closure gap, not missing source material.

- Top cause: **1. Internal locator parser miss** (166 entries, 52.0%).

## 1. Methodology

### Population

- Statements with `standalone_status = context_dependent` **or** failing composition-trace reviewability gates.
- `required_context` entries with empty/missing `proposition_ids` or `resolution_status` in `{unresolved, ambiguous, missing}`.

### Cause taxonomy

- **1. Internal locator parser miss**
- **2. Internal locator exists but source fragment missing**
- **3. Internal locator exists but no proposition extracted**
- **4. External instrument reference**
- **5. Generic/broad reference**
- **6. Ambiguous reference**
- **7. Noisy/false required_context**
- **8. Other/unknown**

### Diagnostics per entry

- Export `resolution_status` and `proposition_ids`
- `parseLocatorReference` / structural parse success
- Source fragment match (`locatorMatchesTarget` + heuristic token overlap)
- Proposition linked to matched fragment
- Review Workbench `buildContextRequirementResolutions` outcome

Cause **1 (parser miss)** includes export-side `resolve_locator_in_source` failures where Review Workbench already resolves the same locator against existing fragments/propositions.

## 2. Totals

| Metric | Count |
| --- | ---: |
| Unresolved locator entries | 319 |
| Workbench-resolvable (export empty) | 268 |
| Export has proposition_ids (partial) | 55 |

### Counts by cause

| Cause | Count | % |
| --- | ---: | ---: |
| 1. Internal locator parser miss | 166 | 52.0 |
| 6. Ambiguous reference | 118 | 37.0 |
| 4. External instrument reference | 21 | 6.6 |
| 2. Internal locator exists but source fragment missing | 8 | 2.5 |
| 3. Internal locator exists but no proposition extracted | 6 | 1.9 |
| 5. Generic/broad reference | 0 | 0.0 |
| 7. Noisy/false required_context | 0 | 0.0 |
| 8. Other/unknown | 0 | 0.0 |

## 3. Top 30 unresolved locator strings

| Locator | Count |
| --- | ---: |
| `schedule 1` | 39 |
| `schedule 3` | 17 |
| `schedule 2` | 16 |
| `Fertiliser Advisers Certification and Training Scheme (FACTS)` | 10 |
| `regulation 4b` | 10 |
| `regulation 36` | 9 |
| `regulation 25` | 7 |
| `regulation 8(5)` | 6 |
| `paragraph 7` | 5 |
| `paragraph 9` | 5 |
| `regulation 6(1)` | 5 |
| `schedule 1a` | 5 |
| `schedule 4` | 5 |
| `paragraph 3(1)` | 4 |
| `regulation 10(5)` | 4 |
| `regulation 24(1)` | 4 |
| `regulation 3(1)` | 4 |
| `regulation 31` | 4 |
| `regulation 5` | 4 |
| `regulation 7` | 4 |
| `regulation 7(1)` | 4 |
| `regulation 9` | 4 |
| `regulation 9(5)` | 4 |
| `schedule 5` | 4 |
| `article 27` | 3 |
| `regulation 12` | 3 |
| `regulation 13` | 3 |
| `regulation 16` | 3 |
| `regulation 30` | 3 |
| `regulation 32` | 3 |

## 4. Top source instruments affected

| Instrument | Unresolved entries |
| --- | ---: |
| The Nitrate Pollution Prevention Regulations 2015 | 126 |
| The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021 | 113 |
| The Control of Pollution (Silage, Slurry and Agricultural Fuel Oil) (Scotland) Regulations 2003 | 38 |
| The Water Resources (Control of Pollution) (Silage, Slurry and Agricultural Fuel Oil) (England) Regulations 2010 | 25 |
| The Reduction and Prevention of Agricultural Diffuse Pollution (England) Regulations 2018 | 17 |

## 5. Examples by cause

### 1. Internal locator parser miss

- **Locator:** `regulation 8(5)`
  - Statement: `lawstmt:01a80b20889c33f1` (context_dependent, trace-blocked: yes)
  - Export status: `unresolved`; kind: `host_rule`
  - Source: The Control of Pollution (Silage, Slurry and Agricultural Fuel Oil) (Scotland) Regulations 2003
  - Parsed: yes; fragment exists: yes; proposition on fragment: yes
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-96613ffe71589e1e-029, frag-lex-96613ffe71589e1e-024, frag-lex-96613ffe71589e1e-025…

- **Locator:** `regulation 9(5)`
  - Statement: `lawstmt:01a80b20889c33f1` (context_dependent, trace-blocked: yes)
  - Export status: `unresolved`; kind: `host_rule`
  - Source: The Control of Pollution (Silage, Slurry and Agricultural Fuel Oil) (Scotland) Regulations 2003
  - Parsed: yes; fragment exists: yes; proposition on fragment: yes
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-96613ffe71589e1e-035, frag-lex-96613ffe71589e1e-030, frag-lex-96613ffe71589e1e-031…

- **Locator:** `schedule 1`
  - Statement: `lawstmt:040001c967a640a6` (partially_resolved, trace-blocked: yes)
  - Export status: `unresolved`; kind: `referenced_locator`
  - Source: The Nitrate Pollution Prevention Regulations 2015
  - Parsed: yes; fragment exists: yes; proposition on fragment: yes
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-120b4f9c395b3f94-267

- **Locator:** `schedule 1`
  - Statement: `lawstmt:04c567b56533e739` (context_dependent, trace-blocked: yes)
  - Export status: `unresolved`; kind: `referenced_locator`
  - Source: The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021
  - Parsed: yes; fragment exists: yes; proposition on fragment: yes
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-805b03f284dcf364-175, frag-lex-805b03f284dcf364-176, frag-lex-805b03f284dcf364-177…

- **Locator:** `regulation 40(2)`
  - Statement: `lawstmt:0867d90aaf67b9f4` (partially_resolved, trace-blocked: yes)
  - Export status: `unresolved`; kind: `host_rule`
  - Source: The Nitrate Pollution Prevention Regulations 2015
  - Parsed: yes; fragment exists: yes; proposition on fragment: yes
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-120b4f9c395b3f94-246, frag-lex-120b4f9c395b3f94-244, frag-lex-120b4f9c395b3f94-245…

### 2. Internal locator exists but source fragment missing

- **Locator:** `annex iii`
  - Statement: `lawstmt:0e34c64386553bcb` (partially_resolved, trace-blocked: yes)
  - Export status: `unresolved`; kind: `supporting_definition`
  - Source: The Nitrate Pollution Prevention Regulations 2015
  - Parsed: no; fragment exists: no; proposition on fragment: no
  - Workbench resolvable: no (not found)
  - Candidate fragment locators: 293

- **Locator:** `annex 3`
  - Statement: `lawstmt:3a964ef07e332c4a` (unresolved_reference, trace-blocked: yes)
  - Export status: `unresolved`; kind: `referenced_locator`
  - Source: The Nitrate Pollution Prevention Regulations 2015
  - Parsed: yes; fragment exists: no; proposition on fragment: no
  - Workbench resolvable: no (not found)
  - Candidate fragment locators: 293

- **Locator:** `regulation 104`
  - Statement: `lawstmt:b6647e2844a65361` (partially_resolved, trace-blocked: yes)
  - Export status: `unresolved`; kind: `referenced_locator`
  - Source: The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021
  - Parsed: yes; fragment exists: no; proposition on fragment: no
  - Workbench resolvable: no (not found)
  - Candidate fragment locators: 228

- **Locator:** `regulation 45`
  - Statement: `lawstmt:c028a995869c1ac1` (context_dependent, trace-blocked: yes)
  - Export status: `unresolved`; kind: `referenced_locator`
  - Source: The Nitrate Pollution Prevention Regulations 2015
  - Parsed: yes; fragment exists: no; proposition on fragment: no
  - Workbench resolvable: no (not found)
  - Candidate fragment locators: 293

- **Locator:** `regulation 63`
  - Statement: `lawstmt:c363dfe85437e730` (partially_resolved, trace-blocked: yes)
  - Export status: `unresolved`; kind: `host_rule`
  - Source: The Nitrate Pollution Prevention Regulations 2015
  - Parsed: yes; fragment exists: no; proposition on fragment: no
  - Workbench resolvable: no (not found)
  - Candidate fragment locators: 293

### 3. Internal locator exists but no proposition extracted

- **Locator:** `schedule 2`
  - Statement: `lawstmt:360f9ec896f8f43e` (fragmentary, trace-blocked: yes)
  - Export status: `unresolved`; kind: `referenced_locator`
  - Source: The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021
  - Parsed: yes; fragment exists: yes; proposition on fragment: no
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-805b03f284dcf364-203

- **Locator:** `regulation 14(4)`
  - Statement: `lawstmt:51c1e7227928072b` (partially_resolved, trace-blocked: yes)
  - Export status: `unresolved`; kind: `incorporated_rule`
  - Source: The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021
  - Parsed: yes; fragment exists: yes; proposition on fragment: yes
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-805b03f284dcf364-060, frag-lex-805b03f284dcf364-056, frag-lex-805b03f284dcf364-057…

- **Locator:** `schedule 2`
  - Statement: `lawstmt:7f7897dd32e77eab` (unresolved_reference, trace-blocked: yes)
  - Export status: `unresolved`; kind: `referenced_locator`
  - Source: The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021
  - Parsed: yes; fragment exists: yes; proposition on fragment: no
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-805b03f284dcf364-203

- **Locator:** `schedule 2`
  - Statement: `lawstmt:8ce00a92f94fbe58` (partially_resolved, trace-blocked: yes)
  - Export status: `unresolved`; kind: `referenced_locator`
  - Source: The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021
  - Parsed: yes; fragment exists: yes; proposition on fragment: no
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-805b03f284dcf364-203

- **Locator:** `schedule 2`
  - Statement: `lawstmt:8e015e534c67fbcb` (fragmentary, trace-blocked: yes)
  - Export status: `unresolved`; kind: `referenced_locator`
  - Source: The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021
  - Parsed: yes; fragment exists: yes; proposition on fragment: no
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-805b03f284dcf364-203

### 4. External instrument reference

- **Locator:** `BS 5502`
  - Statement: `lawstmt:030a536762dc5059` (context_dependent, trace-blocked: yes)
  - Export status: `external_reference`; kind: `external_standard_reference`
  - Source: The Control of Pollution (Silage, Slurry and Agricultural Fuel Oil) (Scotland) Regulations 2003
  - Parsed: no; fragment exists: no; proposition on fragment: no
  - Workbench resolvable: no (external reference)
  - Candidate fragment locators: 69

- **Locator:** `Fertiliser Advisers Certification and Training Scheme (FACTS)`
  - Statement: `lawstmt:0d6770e9e177ecc7` (context_dependent, trace-blocked: no)
  - Export status: `external_reference`; kind: `external_certification_reference`
  - Source: The Nitrate Pollution Prevention Regulations 2015
  - Parsed: no; fragment exists: no; proposition on fragment: no
  - Workbench resolvable: no (external reference)
  - Candidate fragment locators: 293

- **Locator:** `Fertiliser Advisers Certification and Training Scheme (FACTS)`
  - Statement: `lawstmt:2332e0443ddd8d3a` (partially_resolved, trace-blocked: yes)
  - Export status: `external_reference`; kind: `external_certification_reference`
  - Source: The Nitrate Pollution Prevention Regulations 2015
  - Parsed: no; fragment exists: no; proposition on fragment: no
  - Workbench resolvable: no (external reference)
  - Candidate fragment locators: 293

- **Locator:** `Fertiliser Advisers Certification and Training Scheme (FACTS)`
  - Statement: `lawstmt:26e6e9eb1b629cd3` (partially_resolved, trace-blocked: yes)
  - Export status: `external_reference`; kind: `external_certification_reference`
  - Source: The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021
  - Parsed: no; fragment exists: no; proposition on fragment: no
  - Workbench resolvable: no (external reference)
  - Candidate fragment locators: 228

- **Locator:** `Fertiliser Advisers Certification and Training Scheme (FACTS)`
  - Statement: `lawstmt:2e0bff5f767bd498` (partially_resolved, trace-blocked: yes)
  - Export status: `external_reference`; kind: `external_certification_reference`
  - Source: The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021
  - Parsed: no; fragment exists: no; proposition on fragment: no
  - Workbench resolvable: no (external reference)
  - Candidate fragment locators: 228

### 5. Generic/broad reference

_No examples._
### 6. Ambiguous reference

- **Locator:** `schedule 1`
  - Statement: `lawstmt:030a536762dc5059` (context_dependent, trace-blocked: yes)
  - Export status: `unresolved`; kind: `referenced_locator`
  - Source: The Control of Pollution (Silage, Slurry and Agricultural Fuel Oil) (Scotland) Regulations 2003
  - Parsed: yes; fragment exists: yes; proposition on fragment: yes
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-96613ffe71589e1e-040, frag-lex-96613ffe71589e1e-041, frag-lex-96613ffe71589e1e-042…

- **Locator:** `schedule 1`
  - Statement: `lawstmt:069650b20d51ed36` (partially_resolved, trace-blocked: yes)
  - Export status: `unresolved`; kind: `referenced_locator`
  - Source: The Water Resources (Control of Pollution) (Silage, Slurry and Agricultural Fuel Oil) (England) Regulations 2010
  - Parsed: yes; fragment exists: yes; proposition on fragment: yes
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-e71fbbe3342ac0be-045, frag-lex-e71fbbe3342ac0be-046, frag-lex-e71fbbe3342ac0be-047…

- **Locator:** `regulation 16`
  - Statement: `lawstmt:08fb7b6ddb7dfec7` (context_dependent, trace-blocked: no)
  - Export status: `ambiguous`; kind: `host_rule`
  - Source: The Reduction and Prevention of Agricultural Diffuse Pollution (England) Regulations 2018
  - Parsed: yes; fragment exists: yes; proposition on fragment: yes
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-2459c955ee13be52-057, frag-lex-2459c955ee13be52-058, frag-lex-2459c955ee13be52-059…

- **Locator:** `regulation 19`
  - Statement: `lawstmt:096842c64ece19b4` (context_dependent, trace-blocked: no)
  - Export status: `ambiguous`; kind: `referenced_locator`
  - Source: The Nitrate Pollution Prevention Regulations 2015
  - Parsed: yes; fragment exists: yes; proposition on fragment: yes
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-120b4f9c395b3f94-111, frag-lex-120b4f9c395b3f94-112, frag-lex-120b4f9c395b3f94-113…

- **Locator:** `schedule 3`
  - Statement: `lawstmt:0d42cdfdf01e29b2` (context_dependent, trace-blocked: yes)
  - Export status: `unresolved`; kind: `referenced_locator`
  - Source: The Control of Pollution (Silage, Slurry and Agricultural Fuel Oil) (Scotland) Regulations 2003
  - Parsed: yes; fragment exists: yes; proposition on fragment: yes
  - Workbench resolvable: yes
  - Matched fragments: frag-lex-96613ffe71589e1e-062, frag-lex-96613ffe71589e1e-063, frag-lex-96613ffe71589e1e-064…

### 7. Noisy/false required_context

_No examples._
### 8. Other/unknown

_No examples._
## 6. Workbench vs export closure gap

- **213** entries resolve in Review Workbench but export leaves `proposition_ids` empty.
- Sample locators:
  - `regulation 8(5)`
  - `regulation 9(5)`
  - `schedule 1`
  - `regulation 40(2)`
  - `regulation 6(1)`
  - `paragraph 9`
  - `regulation 3(2)`
  - `regulation 7(1)`
  - `schedule 3`
  - `paragraph 4`

## 7. Recommendation

**Highest-leverage fix:** Align export `resolve_locator_in_source` with Review Workbench locator resolution — 268 entries already resolve in workbench but not in export.

**Secondary:** Better locator parser (extend `parseLocatorReference` / colon-path matching) — 166 parser-miss cases with heuristic fragment matches.

Primary cause bucket: **1. Internal locator parser miss** (166 / 319). Addressing this bucket plus the workbench/export alignment (268 entries) closes the majority of trace-reviewability blockers from unresolved context.

## 8. Reproduction

- `uv run --package law-proposition-extractor-pipeline python scripts/generate_unresolved_locator_closure_report.py`
