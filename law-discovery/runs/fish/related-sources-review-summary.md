# Fish related sources review summary

Reviewed **31** related sources and **20** relationships from `related-sources-run-ai-triage.json`.
Output: `related-sources-reviewed.json`
Prompt: `fish-related-sources-review-BR1`

## Counts by source review_decision

| review_decision | Count |
| --- | ---: |
| include | 17 |
| include_needs_legal_review | 9 |
| park_contextual | 3 |
| exclude | 2 |

## Counts by source_role

| source_role | Count |
| --- | ---: |
| amendment | 20 |
| excluded_false_positive | 2 |
| framework_context | 5 |
| implementing_measure | 2 |
| related_supporting | 2 |

## Counts by relationship_type

| relationship_type | Count |
| --- | ---: |
| amended_by | 18 |
| unknown_needs_review | 2 |

## Counts by relationship_review

| relationship_review | Count |
| --- | ---: |
| accepted | 17 |
| needs_legal_review | 3 |
| park_contextual | 0 |
| rejected | 0 |

## Relationships (joined titles)

| relationship_review | relationship_type | from | to | confidence |
| --- | --- | --- | --- | --- |
| accepted | amended_by | Commission Regulation (EC) No 1010/2009 of 22 October 2009 laying down … | Commission Regulation (EU) No 395/2010 of 7 May 2010 amending Commissio… | high |
| accepted | amended_by | Commission Regulation (EC) No 2074/2005 of 5 December 2005 laying down … | The Food and Feed Hygiene and Safety (Miscellaneous Amendments) (EU Exi… | medium |
| accepted | amended_by | Commission Regulation (EC) No 2074/2005 of 5 December 2005 laying down … | The Specific Food Hygiene (Amendment etc.) (EU Exit) Regulations 2019 | high |
| accepted | amended_by | Commission Regulation (EU) No 202/2011 of 1 March 2011 amending Annex I… | The Common Fisheries Policy (Amendment etc.) (EU Exit) (No. 2) Regulati… | high |
| accepted | amended_by | Council Regulation (EC) No 1005/2008 of 29 September 2008 establishing … | The Common Fisheries Policy (Amendment etc.) (EU Exit) Regulations 2019 | high |
| accepted | amended_by | Council Regulation (EC) No 1005/2008 of 29 September 2008 establishing … | The Common Fisheries Policy (Amendment etc.) (EU Exit) (No. 2) Regulati… | high |
| accepted | amended_by | Council Regulation (EC) No 1224/2009 of 20 November 2009 establishing a… | The Common Fisheries Policy and Animals (Amendment etc.) (EU Exit) Regu… | high |
| accepted | amended_by | Council Regulation (EC) No 1224/2009 of 20 November 2009 establishing a… | Regulation (EU) 2015/812 of the European Parliament and of the Council … | high |
| accepted | amended_by | Regulation (EC) No 853/2004 of the European Parliament and of the Counc… | The Food and Feed Hygiene and Safety (Miscellaneous Amendments) (EU Exi… | medium |
| accepted | amended_by | Regulation (EC) No 853/2004 of the European Parliament and of the Counc… | The Specific Food Hygiene (Amendment etc.) (EU Exit) Regulations 2019 | high |
| accepted | amended_by | Regulation (EC) No 853/2004 of the European Parliament and of the Counc… | The Specific Food Hygiene (Regulation (EC) No. 853/2004) (Amendment) (E… | high |
| accepted | amended_by | Regulation (EU) No 1379/2013 of the European Parliament and of the Coun… | The Common Fisheries Policy (Amendment etc.) (EU Exit) Regulations 2019 | high |
| accepted | amended_by | Regulation (EU) No 1379/2013 of the European Parliament and of the Coun… | Regulation (EU) 2020/560 of the European Parliament and of the Council … | high |
| accepted | amended_by | The Common Fisheries Policy and Aquaculture (Amendment etc.) (EU Exit) … | The Common Fisheries Policy (Amendment etc.) (EU Exit) Regulations 2019 | high |
| accepted | amended_by | The Common Fisheries Policy and Aquaculture (Amendment etc.) (EU Exit) … | The Common Fisheries Policy (Amendment etc.) (EU Exit) (No. 2) Regulati… | high |
| accepted | amended_by | The Common Fisheries Policy and Aquaculture (Amendment etc.) (EU Exit) … | The Common Fisheries Policy and Animals (Amendment etc.) (EU Exit) Regu… | high |
| accepted | amended_by | The Common Fisheries Policy and Aquaculture (Amendment etc.) (EU Exit) … | The Common Fisheries Policy (Amendment etc.) (EU Exit) Regulations 2020 | medium |
| needs_legal_review | amended_by | Regulation (EC) No 853/2004 of the European Parliament and of the Counc… | The Animal Health (EU Exit) (Scotland) (Amendment) Regulations 2019 | medium |
| needs_legal_review | unknown_needs_review | The Common Fisheries Policy and Aquaculture (Amendment etc.) (EU Exit) … | The Aquatic Animal Health and Alien Species in Aquaculture, Animals, an… | low |
| needs_legal_review | unknown_needs_review | The Common Fisheries Policy and Aquaculture (Amendment etc.) (EU Exit) … | The Fisheries, Aquaculture and Marine (Functions Exercisable in or as R… | low |

## Unknown / needs legal review relationships

- **amended_by** (`rel:lex-bba56f07da7a7b26:lex-5d68d58988f41b40`): Regulation (EC) No 853/2004 of the European Parliament and … → The Animal Health (EU Exit) (Scotland) (Amendment) Regulati…
  - Regulation (EC) No 853/2004 lays down specific hygiene rules for food of animal origin, materially covering fish and shellfish for human con
- **unknown_needs_review** (`rel:lex-c4dfeb90d697b1d4:lex-87d3d001cfd651ba`): The Common Fisheries Policy and Aquaculture (Amendment etc.… → The Aquatic Animal Health and Alien Species in Aquaculture,…
  - The seed is The Common Fisheries Policy and Aquaculture (Amendment etc.) (EU Exit) Regulations 2019 (SI 2019/753). The candidate is The Aqua
- **unknown_needs_review** (`rel:lex-c4dfeb90d697b1d4:lex-61a86f9486e7fd6b`): The Common Fisheries Policy and Aquaculture (Amendment etc.… → The Fisheries, Aquaculture and Marine (Functions Exercisabl…
  - The seed is The Common Fisheries Policy and Aquaculture (Amendment etc.) (EU Exit) Regulations 2019 (SI 2019/753). The candidate is The Fish

## Excluded false positives

- The Alternative Investment Fund Managers (Amendment etc.) (EU Exit) Regulations 2019 (revoked) (`lex-d87bdb1e26a9809c`)
- The Bovine Products (Restriction on Placing on the Market) (Scotland) (No. 2) Regulations 2005 (`lex-cbea33336a7a255e`)

## Framework-context sources

- **Regulation (EC) No 852/2004 of the european parliament and of the council of 29 April 2004 on the hygiene of foodstuffs** (`lex-6cd739d13947ecca`) — include_needs_legal_review / framework_context
- **The Food Hygiene Regulations (Northern Ireland) 2005** (`lex-0bae7a364b3ed852`) — include_needs_legal_review / framework_context
- **The Animal Health (EU Exit) (Scotland) (Amendment) Regulations 2019** (`lex-5d68d58988f41b40`) — park_contextual / framework_context
- **The Aquatic Animal Health and Alien Species in Aquaculture, Animals, and Marketing of Seed, Plant and Propagating Material (Legislative Functions and Miscellaneous Provisions) (Amendment) (EU Exit) Regulations 2020** (`lex-87d3d001cfd651ba`) — park_contextual / framework_context
- **The Windsor Framework (Retail Movement Scheme: Public Health, Marketing and Organic Product Standards and Miscellaneous Provisions) Regulations 2023** (`lex-913f9e433ac478a5`) — park_contextual / framework_context

## Newly reviewed sources (formerly unreviewed)

- **The Bovine Products (Restriction on Placing on the Market) (Scotland) (No. 2) Regulations 2005** (`lex-cbea33336a7a255e`) — exclude / excluded_false_positive
- **Council Regulation (EC) No 1591/2006 of 24 October 2006 amending Regulation (EC) No 51/2006 as regards provisions on vessels engaged in illegal, unreported and unregulated fisheries in the North-East Atlantic** (`lex-c619d90b6b772116`) — include / amendment
- **Council Regulation (EC) No 2370/2002 of 20 December 2002 establishing an emergency Community measure for scrapping fishing vessels** (`lex-caec2afd773e8a91`) — include / related_supporting
- **Regulation (EU) No 605/2013 of the European Parliament and of the Council of 12 June 2013 amending Council Regulation (EC) No 1185/2003 on the removal of fins of sharks on board vessels** (`lex-b6a512185e10664e`) — include / amendment
- **The European Maritime and Fisheries Fund (Grants) (Wales) Regulations 2016** (`lex-067d1a8ff1ca8c99`) — include / related_supporting
- **The Fishery Products (Official Controls Charges) (Scotland) Regulations 2007** (`lex-40933b6d54a77e62`) — include / implementing_measure
- **The Sea Fisheries (Amendment etc.) (No. 2) Regulations 2021** (`lex-a1937e2cabf9d05b`) — include / amendment
- **The Sea Fisheries (International Commission for the Conservation of Atlantic Tunas) (Amendment) Regulations 2024** (`lex-151ca7f8501c8266`) — include / amendment
- **The Sea Fishing (EU Control Measures) (Scotland) Order 2015** (`lex-2d9bd8f115d0067b`) — include / implementing_measure
- **Regulation (EC) No 852/2004 of the european parliament and of the council of 29 April 2004 on the hygiene of foodstuffs** (`lex-6cd739d13947ecca`) — include_needs_legal_review / framework_context
- **The Food (Miscellaneous Amendments and Revocations) Regulations (Northern Ireland) 2019** (`lex-4b10f9ce94cc6de3`) — include_needs_legal_review / amendment
- **The Food and Feed (Miscellaneous Amendments) Regulations 2022** (`lex-edd3fce31ba4962f`) — include_needs_legal_review / amendment
- **The Food and Feed Hygiene and Safety (Miscellaneous Amendments) (England) Regulations 2020** (`lex-1f8f3283ec08837c`) — include_needs_legal_review / amendment
- **The Food Hygiene (Scotland) Amendment Regulations 2012** (`lex-8d151b0b0bb5ff15`) — include_needs_legal_review / amendment
- **The Food Hygiene Regulations (Northern Ireland) 2005** (`lex-0bae7a364b3ed852`) — include_needs_legal_review / framework_context
- **The Official Feed and Food Controls (Miscellaneous Amendments) (Scotland) Regulations 2019** (`lex-645388a4783af79a`) — include_needs_legal_review / amendment
- **The Windsor Framework (Retail Movement Scheme: Public Health, Marketing and Organic Product Standards and Miscellaneous Provisions) Regulations 2023** (`lex-913f9e433ac478a5`) — park_contextual / framework_context
