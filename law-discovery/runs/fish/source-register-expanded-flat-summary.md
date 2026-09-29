# Fish flattened source register summary

Flattened `source-register-expanded-reviewed.json` into a single `sources` array.
Output: `source-register-expanded-flat.json`
Prompt: `fish-source-register-flat-export-BR1`

## Flatten counts

| Metric | Count |
| --- | ---: |
| Pre-dedupe bucket total | 485 |
| Deduplicated omitted | 49 |
| Flattened source count | 436 |
| Accepted sources | 278 |
| Historical context | 140 |
| Uncertain sources | 49 |
| Included related sources | 18 |
| Relationships preserved | 20 |
| Omitted rejected sources | 151 |
| Omitted parked sources | 23 |

## Counts by source_bucket

| source_bucket | Count |
| --- | ---: |
| accepted_sources | 278 |
| historical_context | 140 |
| included_related_sources | 18 |

## Counts by review_decision

| review_decision | Count |
| --- | ---: |
| include | 428 |
| include_needs_legal_review | 8 |

## Counts by source_role

| source_role | Count |
| --- | ---: |
| amendment | 19 |
| framework_context | 2 |
| implementing_measure | 2 |
| related_principal | 271 |
| related_supporting | 142 |

## Counts by temporal_status

| temporal_status | Count |
| --- | ---: |
| historical | 143 |
| unknown | 293 |

## Counts by source_type

| source_type | Count |
| --- | ---: |
| assimilated_eu_law | 121 |
| ukpga | 38 |
| uksi | 160 |
| unknown | 117 |

## Needs legal review queue

- **Regulation (EC) No 852/2004 of the european parliament and of the council of 29 April 2…** (`lex-6cd739d13947ecca`) — include_needs_legal_review / framework_context [included_related_sources]
- **The Fisheries, Aquaculture and Marine (Functions Exercisable in or as Regards Scotland)…** (`lex-61a86f9486e7fd6b`) — include_needs_legal_review / amendment [included_related_sources]
- **The Food (Miscellaneous Amendments and Revocations) Regulations (Northern Ireland) 2019** (`lex-4b10f9ce94cc6de3`) — include_needs_legal_review / amendment [included_related_sources]
- **The Food and Feed Hygiene and Safety (Miscellaneous Amendments) (England) Regulations 2…** (`lex-1f8f3283ec08837c`) — include_needs_legal_review / amendment [included_related_sources]
- **The Food and Feed Hygiene and Safety (Miscellaneous Amendments) (EU Exit) Regulations 2…** (`lex-7d7c8dabf5b23341`) — include_needs_legal_review / amendment [included_related_sources]
- **The Food Hygiene (Scotland) Amendment Regulations 2012** (`lex-8d151b0b0bb5ff15`) — include_needs_legal_review / amendment [included_related_sources]
- **The Food Hygiene Regulations (Northern Ireland) 2005** (`lex-0bae7a364b3ed852`) — include_needs_legal_review / framework_context [included_related_sources]
- **The Official Feed and Food Controls (Miscellaneous Amendments) (Scotland) Regulations 2…** (`lex-645388a4783af79a`) — include_needs_legal_review / amendment [included_related_sources]

## Relationships

- `lex-4b47b291f898f631` → `lex-9cc294c9aca01db8` (amended_by)
- `lex-210b20412c9f2b5b` → `lex-7d7c8dabf5b23341` (amended_by)
- `lex-210b20412c9f2b5b` → `lex-f3dc0b0810b676d5` (amended_by)
- `lex-0ccefcdcd50caea4` → `lex-970feca6a6cb49a8` (amended_by)
- `lex-01e77542fcd2a3c7` → `lex-6704406fee2f40bd` (amended_by)
- `lex-01e77542fcd2a3c7` → `lex-970feca6a6cb49a8` (amended_by)
- `lex-fb482060f2991955` → `lex-b5be4907f680752a` (amended_by)
- `lex-fb482060f2991955` → `lex-70eb2c4a481eaedf` (amended_by)
- `lex-bba56f07da7a7b26` → `lex-7d7c8dabf5b23341` (amended_by)
- `lex-bba56f07da7a7b26` → `lex-f3dc0b0810b676d5` (amended_by)
- `lex-bba56f07da7a7b26` → `lex-c0936e9ec1554c50` (amended_by)
- `lex-f20bfdf3e99a2264` → `lex-6704406fee2f40bd` (amended_by)
- `lex-f20bfdf3e99a2264` → `lex-e765bc0036b75601` (amended_by)
- `lex-c4dfeb90d697b1d4` → `lex-6704406fee2f40bd` (amended_by)
- `lex-c4dfeb90d697b1d4` → `lex-970feca6a6cb49a8` (amended_by)
- `lex-c4dfeb90d697b1d4` → `lex-b5be4907f680752a` (amended_by)
- `lex-c4dfeb90d697b1d4` → `lex-6deac13df85eb723` (amended_by)
- `lex-bba56f07da7a7b26` → `lex-5d68d58988f41b40` (amended_by)
- `lex-c4dfeb90d697b1d4` → `lex-87d3d001cfd651ba` (unknown_needs_review)
- `lex-c4dfeb90d697b1d4` → `lex-61a86f9486e7fd6b` (unknown_needs_review)
