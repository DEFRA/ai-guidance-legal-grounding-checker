# External name inventory

Bounded list of locations outside this repository that may still use personal component
codenames. Searched before the rename implementation began (2026-07-30).

Alias removal target: `rename+1` (see [migration-component-rename.md](migration-component-rename.md)).

## Sibling repositories

| Location | Role | Codename surface |
| --- | --- | --- |
| `../content-audit-data-assets` | Inter-step run artifact store | Directory layout `steps/{grace,mary,radia,susan,ada,judit,beatrice,anna,esther,…}`; MODEL.md / metrics titles |
| `../ai-sdlc-content-audit` | Frontend consumer of Audit Assembler output | Scripts (`sync-esther-runs.mjs`), audit run MODEL.md, loaders mentioning Esther |
| `../ai-sdlc-content-audit-backend` | Backend companion (if present) | Check for Esther / pipeline step names |
| `../ai-eu-trade-accelerator-BACKUP-PRE-RENAME` | Local backup snapshot | Historic only — do not migrate |
| `../defra-ai-eu-trade-accelerator` | Alternate / older checkout | May contain parallel personal-name layout |
| `../judit`, `../judit-v0`, `../judit-blind`, `../ada` | Standalone historic checkouts | Historic only |

## In-repo docs that previously duplicated maps

After this change, those documents link to the root [README.md](../README.md) component table
rather than maintaining independent full mapping tables.

## Obsidian / vault

No Obsidian vault path is referenced from this repository. If a team vault exists, run the
same expression as `scripts/check_legacy_component_names.py` against it and attach results
to the story (vault is not available to repository CI).

## Search transcript (pre-implementation)

### content-audit-data-assets

- `steps/` directories named: `grace`, `mary`, `radia`, `susan`, `ada`, `judit`, `beatrice`, `anna`, `esther`, plus `searchapi`
- Codename hits in MODEL.md / metrics / READMEs under those step trees
- **Action:** accept old step directory names during compat; document canonical kebab slugs for new runs; do not rewrite historic artifacts

### ai-sdlc-content-audit

- `scripts/sync-esther-runs.mjs`
- Audit run MODEL.md under `src/server/services/audit/runs/`
- Loader / service strings referencing Esther
- **Action:** update script names and docs to Audit Assembler / `audit-assembler` with deprecated alias where needed; leave historic run folders intact

### Dashboards / metrics TSDB

None found in this repository or the sibling inventory (no Datadog/Grafana/Prometheus product refs).
Per-run `metrics.json` continuity is documented in the migration guide.


## Post-rename verification

Run (outside CI, against sibling checkouts):

```bash
python scripts/check_legacy_component_names.py \
  --external ../content-audit-data-assets \
  --external ../ai-sdlc-content-audit
```

Attach stdout/stderr to the story. Historic `$DATA` step directories and Audit Assembler sync
scripts are expected hits until those sibling repos are updated.
