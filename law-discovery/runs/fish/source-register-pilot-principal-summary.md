# Fish pilot principal source register summary

Pilot subset of `source-register-expanded-flat.json` for Law Proposition Extractor/Proposition Matcher extraction.
Output: `source-register-pilot-principal.json`
Prompt: `fish-pilot-priority-order-BR1`
Register id: `ada-register-fish-pilot-principal`

## Selection counts

| Metric | Count |
| --- | ---: |
| Selected sources | 15 |
| Accepted sources | 12 |
| Historical context | 3 |
| Uncertain sources | 0 |
| Parked sources | 0 |
| Rejected sources | 0 |
| Full relationships (both endpoints in pilot) | 2 |
| Relationship stubs (principal ↔ off-pilot amendment) | 3 |
| Flat register sources (input) | 436 |

## Counts by source_role

| source_role | Count |
| --- | ---: |
| amendment | 2 |
| related_principal | 10 |
| related_supporting | 3 |

## Counts by temporal_status

| temporal_status | Count |
| --- | ---: |
| historical | 3 |
| unknown | 12 |

## Selected source titles

- Fisheries Act 2020 (`lex-83a291a8360fedb0`)
- Regulation (EU) No 1380/2013 of the European Parliament and of the Council of 11 December 2013 on the Common Fisheries Policy, amending Council Regulations (EC) No 1954/2003 and (EC) No 1224/2009 and repealing Council Regulations (EC) No 2371/2002 and (EC) No 639/2004 and Council Decision 2004/585/EC (`lex-9d099c48e30e9000`)
- Council Regulation (EC) No 1224/2009 of 20 November 2009 establishing a Union control system for ensuring compliance with the rules of the common fisheries policy, amending Regulations (EC) No 847/96, (EC) No 2371/2002, (EC) No 811/2004, (EC) No 768/2005, (EC) No 2115/2005, (EC) No 2166/2005, (EC) No 388/2006, (EC) No 509/2007, (EC) No 676/2007, (EC) No 1098/2007, (EC) No 1300/2008, (EC) No 1342/2008 and repealing Regulations (EEC) No 2847/93, (EC) No 1627/94 and (EC) No 1966/2006 (`lex-fb482060f2991955`)
- Council Regulation (EC) No 1005/2008 of 29 September 2008 establishing a Community system to prevent, deter and eliminate illegal, unreported and unregulated fishing, amending Regulations (EEC) No 2847/93, (EC) No 1936/2001 and (EC) No 601/2004 and repealing Regulations (EC) No 1093/94 and (EC) No 1447/1999 (`lex-01e77542fcd2a3c7`)
- Regulation (EU) No 1379/2013 of the European Parliament and of the Council of 11 December 2013 on the common organisation of the markets in fishery and aquaculture products, amending Council Regulations (EC) No 1184/2006 and (EC) No 1224/2009 and repealing Council Regulation (EC) No 104/2000 (`lex-f20bfdf3e99a2264`)
- The Fish Labelling Regulations 2013 (`lex-59be772b83070d26`)
- Regulation (EC) No 853/2004 of the European Parliament and of the Council of 29 April 2004 laying down specific hygiene rules for food of animal origin (`lex-bba56f07da7a7b26`)
- Marine and Coastal Access Act 2009 (`lex-574221db1516c47e`)
- Council Directive 2006/88/EC of 24 October 2006 on animal health requirements for aquaculture animals and products thereof, and on the prevention and control of certain diseases in aquatic animals (`lex-94cb8d40849fefcb`)
- Fisheries Act 1981 (`lex-8857a84dcad0d639`)
- Sea Fish Industry Act 1959 (`lex-50529677787d481a`)
- Sea Fish Industry Act 1973 (`lex-33a0aee28e649862`)
- Sea Fisheries (Shellfish) Act 1967 (`lex-1d7dc8c1608c123b`)
- The Specific Food Hygiene (Regulation (EC) No. 853/2004) (Amendment) (EU Exit) Regulations 2019 (`lex-c0936e9ec1554c50`)
- Regulation (EU) 2015/812 of the European Parliament and of the Council of 20 May 2015 amending Council Regulations (EC) No 850/98, (EC) No 2187/2005, (EC) No 1967/2006, (EC) No 1098/2007, (EC) No 254/2002, (EC) No 2347/2002 and (EC) No 1224/2009, and Regulations (EU) No 1379/2013 and (EU) No 1380/2013 of the European Parliament and of the Council, as regards the landing obligation, and repealing Council Regulation (EC) No 1434/98 (`lex-70eb2c4a481eaedf`)

## Why each source was selected

### Fisheries Act 2020

- **source_id:** `lex-83a291a8360fedb0`
- **selection_key:** `fisheries_act_2020`
- **source_role:** related_principal
- **register_bucket:** accepted_sources
- **temporal_status:** unknown
- **Rationale:** Core UK fisheries framework Act; primary post-Brexit domestic fisheries legislation.
- **Extraction risk:** Large framework Act; extraction may surface cross-cutting marine/conservation provisions beyond trade.

### Regulation (EU) No 1380/2013 of the European Parliament and of the Coun…

- **source_id:** `lex-9d099c48e30e9000`
- **selection_key:** `eu_1380_2013`
- **source_role:** related_principal
- **register_bucket:** accepted_sources
- **temporal_status:** unknown
- **Rationale:** Assimilated EU Common Fisheries Policy principal regulation.
- **Extraction risk:** Assimilated EU law; post-Brexit domestic modifications may not be reflected in Lex metadata.

### Council Regulation (EC) No 1224/2009 of 20 November 2009 establishing a…

- **source_id:** `lex-fb482060f2991955`
- **selection_key:** `eu_1224_2009`
- **source_role:** related_principal
- **register_bucket:** accepted_sources
- **temporal_status:** unknown
- **Rationale:** EU fisheries control and enforcement system — catch certificates, inspections, VMS.
- **Extraction risk:** Control-system regulation is lengthy; implementing/delegated acts mostly excluded from pilot.

### Council Regulation (EC) No 1005/2008 of 29 September 2008 establishing …

- **source_id:** `lex-01e77542fcd2a3c7`
- **selection_key:** `eu_1005_2008`
- **source_role:** related_principal
- **register_bucket:** accepted_sources
- **temporal_status:** unknown
- **Rationale:** IUU fishing and catch-certification regime for fishery products trade.
- **Extraction risk:** IUU/catch-certificate rules cross-cut trade and enforcement; third-country lists excluded.

### Regulation (EU) No 1379/2013 of the European Parliament and of the Coun…

- **source_id:** `lex-f20bfdf3e99a2264`
- **selection_key:** `eu_1379_2013`
- **source_role:** related_principal
- **register_bucket:** accepted_sources
- **temporal_status:** unknown
- **Rationale:** Assimilated EU common organisation of markets in fishery and aquaculture products.
- **Extraction risk:** Market organisation rules overlap with general food marketing — watch for non-fishery COM articles.

### The Fish Labelling Regulations 2013

- **source_id:** `lex-59be772b83070d26`
- **selection_key:** `fish_labelling_2013`
- **source_role:** related_principal
- **register_bucket:** accepted_sources
- **temporal_status:** unknown
- **Rationale:** Key retained fish marketing/labelling instrument (England-wide SI).
- **Extraction risk:** England instrument; devolved labelling SIs excluded — jurisdiction fragmentation risk.

### Regulation (EC) No 853/2004 of the European Parliament and of the Counc…

- **source_id:** `lex-bba56f07da7a7b26`
- **selection_key:** `eu_853_2004`
- **source_role:** related_principal
- **register_bucket:** accepted_sources
- **temporal_status:** unknown
- **Rationale:** Specific hygiene rules for food of animal origin — core seafood processing hygiene.
- **Extraction risk:** General animal-origin hygiene — fish-specific annexes need careful scoping.

### Marine and Coastal Access Act 2009

- **source_id:** `lex-574221db1516c47e`
- **selection_key:** `marine_and_coastal_access_act_2009`
- **source_role:** related_principal
- **register_bucket:** accepted_sources
- **temporal_status:** unknown
- **Rationale:** Marine planning, licensing and inshore fisheries management framework.
- **Extraction risk:** Broad marine statute — fisheries provisions mixed with access/conservation.

### Council Directive 2006/88/EC of 24 October 2006 on animal health requir…

- **source_id:** `lex-94cb8d40849fefcb`
- **selection_key:** `aquatic_animal_health_2006_88`
- **source_role:** related_principal
- **register_bucket:** accepted_sources
- **temporal_status:** unknown
- **Rationale:** Principal EU aquaculture and aquatic animal health instrument.
- **Extraction risk:** Aquaculture health scope may pull disease-control provisions beyond food trade.

### Fisheries Act 1981

- **source_id:** `lex-8857a84dcad0d639`
- **selection_key:** `fisheries_act_1981`
- **source_role:** related_principal
- **register_bucket:** accepted_sources
- **temporal_status:** unknown
- **Rationale:** Long-standing UK fisheries principal Act covering licensing, enforcement and sea fish industry powers.
- **Extraction risk:** Long-lived Act with extensive amendments; temporal_status unknown in register.

### Sea Fish Industry Act 1959

- **source_id:** `lex-50529677787d481a`
- **selection_key:** `sea_fish_industry_act_1959`
- **source_role:** related_supporting
- **register_bucket:** historical_context
- **temporal_status:** historical
- **Rationale:** Foundational Sea Fish Industry Authority / levy framework explicitly named in pilot scope.
- **Extraction risk:** Marked historical in register; may yield superseded industry-governance provisions.

### Sea Fish Industry Act 1973

- **source_id:** `lex-33a0aee28e649862`
- **selection_key:** `sea_fish_industry_act_1973`
- **source_role:** related_supporting
- **register_bucket:** historical_context
- **temporal_status:** historical
- **Rationale:** Principal Sea Fish Industry Act amendment era instrument; supports industry governance lineage.
- **Extraction risk:** Marked historical; overlapping Sea Fish Industry Authority powers with 1959 Act.

### Sea Fisheries (Shellfish) Act 1967

- **source_id:** `lex-1d7dc8c1608c123b`
- **selection_key:** `sea_fisheries_shellfish_act_1967`
- **source_role:** related_supporting
- **register_bucket:** historical_context
- **temporal_status:** historical
- **Rationale:** Shellfish fisheries licensing and bed regulation — direct shellfish scope.
- **Extraction risk:** Marked historical; devolved shellfish licensing may need jurisdiction disambiguation.

### The Specific Food Hygiene (Regulation (EC) No. 853/2004) (Amendment) (E…

- **source_id:** `lex-c0936e9ec1554c50`
- **selection_key:** `lex-c0936e9ec1554c50`
- **source_role:** amendment
- **register_bucket:** accepted_sources
- **temporal_status:** unknown
- **Rationale:** UK EU Exit amendment directly transposing Reg 853/2004 seafood hygiene — tests hygiene amendment chain.
- **Extraction risk:** Amendment-only SI — extraction depends on reading amendments against Reg 853/2004 base text.

### Regulation (EU) 2015/812 of the European Parliament and of the Council …

- **source_id:** `lex-70eb2c4a481eaedf`
- **selection_key:** `lex-70eb2c4a481eaedf`
- **source_role:** amendment
- **register_bucket:** accepted_sources
- **temporal_status:** unknown
- **Rationale:** EU 2015/812 landing-obligation amendment to Reg 1224/2009 — tests EU-to-EU amendment relationship.
- **Extraction risk:** Amends multiple CFP regulations; fish-specific landing-obligation articles need targeting.

## Relationships (both endpoints in pilot)

- `lex-bba56f07da7a7b26` → `lex-c0936e9ec1554c50` (amended_by)
- `lex-fb482060f2991955` → `lex-70eb2c4a481eaedf` (amended_by)

## Relationship stubs (off-pilot amendment endpoint)

- `lex-01e77542fcd2a3c7` → `lex-6704406fee2f40bd` (amended_by) — stub
- `lex-f20bfdf3e99a2264` → `lex-6704406fee2f40bd` (amended_by) — stub
- `lex-fb482060f2991955` → `lex-b5be4907f680752a` (amended_by) — stub
