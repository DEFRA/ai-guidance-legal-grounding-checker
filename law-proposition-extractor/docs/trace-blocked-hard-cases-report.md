# Trace-blocked hard cases report

**Date:** 2026-06-12
**Export:** `/Users/bram/Code/defra/ai-eu-trade-accelerator/law-proposition-extractor/runs/slurry-gb-principal-5-current-export`

## Executive summary

- **254** / 1415 statements have export `composition_trace` but remain trace-blocked by `assessCompositionTrace`.
- Review Workbench queue preset: **Trace-blocked hard cases** — prioritises reviewer_required → should_split → should_inline → context_dependent → apparent overreach → missing propositions.

## Count by trace_block_reason

| Reason | Count |
| --- | ---: |
| Monolithic composition | 252 |
| High unknown coverage | 2 |

## Count by incorporation recommendation

| Flag (statement has ≥1) | Count |
| --- | ---: |
| reviewer_required | 19 |
| should_split | 0 |
| should_inline | 1 |
| external_context | 25 |

## Top source instruments

| Instrument | Hard cases |
| --- | ---: |
| UKSI 2015/668 | 103 |
| WSI 2021/77 | 85 |
| UKSI 2010/639 | 29 |
| UKSI 2018/151 | 26 |
| SSI 2003/531 | 11 |

## Top repeated unresolved locators

| Locator | Statements |
| --- | ---: |
| paragraph 3(1) | 4 |
| article 27 | 2 |
| paragraph 17(2) | 2 |
| regulation 63 | 2 |
| schedule 2 | 2 |
| annex iii | 1 |
| paragraph 10(1) | 1 |
| paragraph 17 | 1 |
| paragraph 17(1) | 1 |
| paragraph 18(1) | 1 |
| paragraph 4(1) | 1 |
| regulation 104 | 1 |
| regulation 32 | 1 |
| regulation 45 | 1 |
| schedule 5 | 1 |

## Sample hard cases (20 representative)

### 1. `lawstmt:87727d58fd5f1741`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2018/151
- priority score: 1015

> "Agri-environmental commitment" means any commitment entered into under Council Regulation (EC) No. 1698/2005 on support for rural development by the European Agricultural Fund for Rural Development or Regulation (EU) No…

### 2. `lawstmt:022b9a6fec8ccef2`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2015/668
- priority score: 1005

> The Secretary of State must make adequate arrangements to enable the public to prepare and participate effectively in the review.

### 3. `lawstmt:029914423a5c5021`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2015/668
- priority score: 1005

> Where paragraph (4)(b) applies, storage facilities for an additional one week's manure must be provided as a contingency measure in the event that spreading is not possible on some dates.

### 4. `lawstmt:073a09628c75ef28`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2015/668
- priority score: 1005

> Having carried out a review, the Secretary of State must set out the conclusions in a report and publish the report; the report must set out the objectives intended to be achieved by these Regulations, include an assessm…

### 5. `lawstmt:096f9a543920df5a`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2010/639
- priority score: 1005

> A person who has custody or control of field silage or silage stored on open land must ensure the place is at least 10 metres from any inland freshwaters or coastal waters, and at least 50 metres from the nearest relevan…

### 6. `lawstmt:0becc44c4eb8b62b`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2015/668
- priority score: 1005

> The written declaration must be sent to the Agency within 28 calendar days of the derogation being granted.

### 7. `lawstmt:0e554a59971e2a04`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: WSI 2021/77
- priority score: 1005

> No person may spread manufactured nitrogen fertiliser on tillage land during the period from 1 September to 15 January (inclusive).

### 8. `lawstmt:0edfc4b392578218`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2018/151
- priority score: 1005

> When planning the application of agricultural diffuse pollution sources, the land manager must ensure that the proximity of the land to inland freshwaters, coastal waters, wetlands, or to a spring, well or borehole is ta…

### 9. `lawstmt:11f8255292238a00`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2015/668
- priority score: 1005

> In the case of permanent grassland, the occupier must comply with the duty to assess the amount of nitrogen fertiliser to be applied each calendar year before the first spreading of nitrogen fertiliser.

### 10. `lawstmt:13fa21c728df1a70`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: WSI 2021/77
- priority score: 1005

> For poultry manure, 30% of the total nitrogen in the livestock manure is assumed to be available for crop uptake in the growing season in which it is spread.

### 11. `lawstmt:13fcda67946c430c`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2015/668
- priority score: 1005

> Throughout the year concerned, the total amount of nitrogen from manufactured nitrogen fertiliser applied to the holding must not exceed 90 kg multiplied by the area of the holding in hectares.

### 12. `lawstmt:177d1f91fe850dbf`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2015/668
- priority score: 1005

> Parts 3 to 8 apply only in relation to holdings that are in nitrate vulnerable zones designated for the purposes of these Regulations.

### 13. `lawstmt:17b7b71baed21128`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2010/639
- priority score: 1005

> A notice must state the period within which any requirement contained in it is to be complied with.

### 14. `lawstmt:18122e82d35db0d8`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: WSI 2021/77
- priority score: 1005

> Any person who contravenes any provision of these Regulations is guilty of an offence and liable on summary conviction, or on conviction on indictment, to a fine.

### 15. `lawstmt:1874ed2df590a468`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2018/151
- priority score: 1005

> Where the application is of livestock manure (other than slurry or poultry manure), the total annual amount of manure applied must not exceed 12.5 tonnes per hectare.

### 16. `lawstmt:1ca6edef6f23a455`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2010/639
- priority score: 1005

> "Relevant water abstraction" means the abstraction of water for use for human consumption.

### 17. `lawstmt:1cefbef4c069ab37`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2015/668
- priority score: 1005

> The Secretary of State must prepare a report on the implementation of the Regulations for each relevant period.

### 18. `lawstmt:1d7673b8a7a1d634`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: WSI 2021/77
- priority score: 1005

> A person who has custody or control of silage being made or stored must ensure that, where silage is compressed into bales, the bales are wrapped and sealed into impermeable membranes or enclosed in impermeable bags, and…

### 19. `lawstmt:1db210c48bc435b2`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: WSI 2021/77
- priority score: 1005

> The requirement in paragraph (1) does not apply to slurry while it is stored temporarily in a tanker used for transporting slurry on roads or about a farm.

### 20. `lawstmt:1db90ef21e065cce`

- trace_block_reason: Monolithic composition
- incorporation: reviewer=0, split=0, inline=0, external=0
- unresolved locators: 0
- material context entries: 0
- proposition count: 1
- source instrument: UKSI 2015/668
- priority score: 1005

> In the case of brassica crops, an additional 50 kg of nitrogen per hectare may be spread every four weeks during the closed period, up to the date of harvest.

## Reproduction

```bash
uv run --package law-proposition-extractor-pipeline python scripts/generate_trace_blocked_hard_cases_report.py
```

