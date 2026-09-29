# Historic component names

Permanent glossary of personal codenames replaced by descriptive corpus+capability names.
After deprecated aliases are removed, this file remains the canonical historic glossary.

Canonical live mapping: root [README.md](README.md) component table (from
[`components.manifest.yaml`](components.manifest.yaml)).

Migration / compat contract: [docs/migration-component-rename.md](docs/migration-component-rename.md).

## Mapping

| Legacy codename | Canonical name | Canonical slug | Canonical as of | Legacy commands / packages |
| --- | --- | --- | --- | --- |
| Grace | Scope Planner | `scope-planner` | rename release | Manual step only (no package) |
| Mary | Guidance Discovery | `guidance-discovery` | rename release | dir `mary/`, scripts via `mary/run.sh` |
| Ada | Law Discovery | `law-discovery` | rename release | CLI `ada`, `ada-viewer`; dist `ada-source-discovery`; env `ADA_*` |
| Radia | Guidance Relevance Filter | `guidance-relevance-filter` | rename release | CLI `radia`; env `RADIA_*` |
| Susan | Guidance Proposition Extractor | `guidance-proposition-extractor` | rename release | CLI `susan` |
| Judit | Law Proposition Extractor | `law-proposition-extractor` | rename release | CLI `judit-*`; packages `judit_*`; env `JUDIT_*` |
| Beatrice | Proposition Matcher | `proposition-matcher` | rename release | CLI `beatrice`; artifact `beatrice_law_candidates.json` |
| Anna | Match Adjudicator | `match-adjudicator` | rename release | CLI `anna`; flag `--proposition-matcher-run` |
| Esther | Audit Assembler | `audit-assembler` | rename release | CLI `esther` |

Deprecated aliases are removed in release **`rename+1`**.

## Interpreting historic material

### Run artifacts

- Historic MODEL.md titles and directory names under `$DATA/{mary,radia,…}` use legacy
  codenames. Readers accept those labels; new runs emit canonical `producer_component`
  slugs and prefer kebab-case `$DATA` directories.
- Handoff file `beatrice_law_candidates.json` may appear in old exports; canonical writers
  prefer `proposition_matcher_law_candidates.json` while still reading the old name.

### Frozen domain identifiers (never rewritten)

These embed legacy personal names or opaque prefixes and **must remain byte-identical**:

| Pattern | Meaning |
| --- | --- |
| `susan-<slug>-<n>` | Guidance proposition IDs assigned when ingesting Guidance Proposition Extractor output into Proposition Matcher |
| `extraction_method="susan"` | Field value on guidance propositions |
| `judit_extraction_meta:` / `judit_extraction_reuse:` | Notes prefixes in Law Proposition Extractor |
| `prop:…` | Opaque law proposition machine IDs |
| `lawstmt:…` / `bcand:…` / `m-…` | Statement, candidate, and match-row IDs |

### Metrics and project notes

Per-run `metrics.json` files may name the step with a personal codename. Treat those as
historic display labels. New runs set `component_id` to the canonical slug.

Screenshots, decks, and notes that say “Judit” / “Beatrice” refer to Law Proposition
Extractor / Proposition Matcher respectively.
