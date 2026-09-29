# Article 49a legal-structure acceptance fixture

Offline regression fixture for EUR 2009/1224 Article 49a.

**Not an authoritative current-law snapshot.** Captured for deterministic CI only.

## Provenance

See [`PROVENANCE.json`](./PROVENANCE.json).

| Field | Value |
| --- | --- |
| Source URL | https://www.legislation.gov.uk/eur/2009/1224/data.xml |
| Live run | `runs/fish/article-49a-acceptance-2026-07-14-br1-qualified` |
| Live export | `runs/fish/article-49a-acceptance-2026-07-14-br1-qualified-export` |
| Capture date | 2026-07-14 |
| Model | `frontier_extract` → `anthropic/claude-sonnet-4-6` |
| Parser | `legislation_gov_uk_data_xml_v1` / `v1` |

## Contents

- `source.xml` — reduced CLML (Title I + Article 1; Title IV + Article 14 stub + full Article 49a; retained commentaries; 2 UnappliedEffects)
- `frontier_responses/` — captured validated frontier rows for paragraphs 1–3
- `case.json` — required-locator + focus-term selection config
- `serialized/` — optional slim export slice for frontend view-model tests

## Deliberate reductions

- Dropped all other titles/articles of the 1224/2009 instrument
- Dropped most Type=F commentaries (sequential F-labels therefore differ from live F228–F230; assert by `annotation_id`)
- Article 14 body replaced with a short stub that preserves the locator
- Frontier paragraph 1–2 responses taken from qualified derived-cache validated rows (export traces truncated raw output at 2048 chars)

## Run

```bash
cd law-proposition-extractor
uv run --all-packages pytest tests/acceptance/test_article_49a_legal_structure.py tests/acceptance/test_article_49a_legal_structure_mutations.py -q
# or:
just test-acceptance-article-49a
```
