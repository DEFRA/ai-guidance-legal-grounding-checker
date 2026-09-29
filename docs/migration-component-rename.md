# Migration guide — component descriptive rename

Coordinated rename from personal codenames to descriptive corpus+capability names.

- Manifest: [`../components.manifest.yaml`](../components.manifest.yaml)
- Historic glossary: [`../NAMES.md`](../NAMES.md)
- Alias removal follow-up: [alias-removal-follow-up.md](alias-removal-follow-up.md)
- External inventory: [external-name-inventory.md](external-name-inventory.md)

## Compatibility contract (rename → `rename+1`)

During one explicitly named release cycle:

1. **Canonical names** are used for new commands, packages, configuration, and producer metadata.
2. **Deprecated aliases** resolve through the isolated [`compat/`](../compat/) layer and thin
   per-package shims.
3. Using an old name emits a clear **deprecation warning** naming the replacement and
   `alias_removal_release` (`rename+1`).
4. **New outputs** emit canonical `producer_component` (slug) and `source_kind`.
5. **Readers** continue to accept historic artifacts with legacy component names / filenames.
6. Historic artifacts are **not rewritten** in place.
7. **Proposition IDs and other persisted domain identifiers are not transformed**
   (see frozen patterns in `NAMES.md`).
8. If both an old and a new env/config name are supplied with **conflicting values**,
   execution fails with a configuration error.
9. Compatibility code is isolated and marked for removal; **canonical implementation
   modules must not import from legacy-named modules**.

## Surfaces

| Surface | Canonical | Deprecated alias behaviour |
| --- | --- | --- |
| CLI | `proposition-matcher run` | `beatrice` → warn + forward |
| Env | `LAW_PROPOSITION_EXTRACTOR_*`, `LAW_DISCOVERY_*`, `GUIDANCE_RELEVANCE_FILTER_*` | `JUDIT_*`, `ADA_*`, `RADIA_*` accepted if non-conflicting |
| Imports | `law_proposition_extractor_pipeline` | Old `judit_*` shims where practical (see exclusions) |
| Artifacts | `proposition_matcher_law_candidates.json` | Read `beatrice_law_candidates.json` |
| `$DATA` dirs | kebab slugs | Old personal-name dirs accepted when resolving inputs |
| Flags | `--proposition-matcher-run` | `--proposition-matcher-run` alias |
| Ada export cmds | `export-for-law-proposition-extractor` | `export-for-judit` alias |

## Import shim exclusions

Deep Judit workspace import graphs may not expose every historical submodule path as a
shim. Prefer installing/running via the renamed package. Documented impractical paths are
allowed to require canonical imports; CLI and artifact compatibility remain mandatory.

## Metrics continuity (AC-11)

There is no shared metrics TSDB in this repository (no Datadog/Grafana/Prometheus product
integration). Continuity policy:

| Metric surface | Policy |
| --- | --- |
| Per-run `metrics.json` | Add stable `component_id` (canonical slug). Display titles may change. This intentionally begins a new label series for human-facing step names while IDs stay joinable via `component_id`. |
| MODEL.md H1 | Canonical display name / slug — documentation-facing only |
| External dashboards | None in inventory; if discovered, dual-query old+new labels through `rename+1` |

## Audit Assembler responsibility (AC-9)

Audit Assembler (formerly Esther) **joins and presents** already-produced analytical
results for the frontend. It does **not** perform verification, assurance, or scoring
unless a future component explicitly implements those capabilities.

## Deterministic replay

See [baseline-replay/README.md](baseline-replay/README.md).
