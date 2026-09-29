# Export composition trace report

**Date:** 2026-06-12
**Corpus:** Slurry GB principal-5 (regenerated export)
**Export:** `/Users/bram/Code/defra/ai-eu-trade-accelerator/law-proposition-extractor/runs/slurry-gb-principal-5-current-export`

## Executive summary

- **1415** / 1415 statements carry export `composition_trace`.
- Among **732** composition-opaque statements: trace-reviewable **480 → 480** (65.6% → 65.6%) after export trace packaging.
- **252** opaque statements remain trace-blocked.
- **386** statements flagged `should_inline`.
- **119** statements flagged `should_split`.
- **20** statements flagged `reviewer_required`.

## Population

| Metric | Count |
| --- | ---: |
| Statements with composition_trace | 1415 |
| Opaque statements | 732 |
| Trace-reviewable (derived, before export field) | 480 |
| Trace-reviewable (with export trace) | 480 |
| Trace-blocked | 252 |
| should_inline | 386 |
| should_split | 119 |
| reviewer_required | 20 |
| external_context entries | 96 |

## Sample statements

### 1. `lawstmt:01a80b20889c33f1`

- Trace-reviewable: yes
- Spans: 1
- Incorporation: should_split

> SEPA shall withdraw, extend, or modify a notice under regulation 8(5) if directed to do so by the Scottish Ministers under regulation 9(5).

### 2. `lawstmt:01dd1df2d41109e0`

- Trace-reviewable: yes
- Spans: 1
- Incorporation: none

> Fuel oil storage areas must comply with the requirements set out in Schedule 3.

### 3. `lawstmt:022b9a6fec8ccef2`

- Trace-reviewable: no
- Spans: 1
- Incorporation: none

> The Secretary of State must make adequate arrangements to enable the public to prepare and participate effectively in the review.

### 4. `lawstmt:02903d9bcb2a1f03`

- Trace-reviewable: yes
- Spans: 1
- Incorporation: should_inline

> For each area planted or intended to be planted, the nutrient management plan must record the soil nitrogen supply calculated in accordance with regulation 6(1) and the method used to establish that figure.

### 5. `lawstmt:029914423a5c5021`

- Trace-reviewable: no
- Spans: 1
- Incorporation: none

> Where paragraph (4)(b) applies, storage facilities for an additional one week's manure must be provided as a contingency measure in the event that spreading is not possible on some dates.

### 6. `lawstmt:030a536762dc5059`

- Trace-reviewable: yes
- Spans: 1
- Incorporation: none

> A silo must either comply with the provisions of Schedule 1, or be designed and constructed in accordance with BS 5502 (parts relating to Cylindrical Forage Towers).

### 7. `lawstmt:040001c967a640a6`

- Trace-reviewable: yes
- Spans: 1
- Incorporation: should_inline

> Before 30th April each year, the occupier of a holding with livestock must record for the previous storage period the number of animals in a building or hardstanding on the holding during that period and the category for…

### 8. `lawstmt:04c567b56533e739`

- Trace-reviewable: yes
- Spans: 1
- Incorporation: none

> The amount of nitrogen produced by livestock must be calculated in accordance with Schedule 1.

### 9. `lawstmt:052448652136cca3`

- Trace-reviewable: yes
- Spans: 1
- Incorporation: should_inline

> Before 30 April each year, the occupier of a holding with livestock must record, for the previous storage period referred to in regulation 29, the number and category of animals in a building or on a hardstanding during …

### 10. `lawstmt:0680345870bebcae`

- Trace-reviewable: yes
- Spans: 1
- Incorporation: should_inline

> Regulation 22 does not apply to the spreading of nitrogen fertiliser in a greenhouse.

### 11. `lawstmt:069650b20d51ed36`

- Trace-reviewable: yes
- Spans: 1
- Incorporation: should_inline

> A person who has custody or control of silage being made or stored must ensure the silage is kept in a silo satisfying the requirements of Schedule 1, or compressed into bales that are wrapped/sealed in impermeable membr…

### 12. `lawstmt:06dc597544dec2a7`

- Trace-reviewable: yes
- Spans: 1
- Incorporation: should_inline

> Regulation 4(1) does not apply to slurry while it is stored temporarily in a tanker that is used for transporting slurry on roads or about a farm.

## Reproduction

```bash
uv run --package law-proposition-extractor-pipeline python scripts/generate_export_composition_trace_report.py
```

