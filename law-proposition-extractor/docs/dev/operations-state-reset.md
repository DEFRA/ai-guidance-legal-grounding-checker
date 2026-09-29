# Operations export bundle, registry, and reset

**Operations export directory** (`OPERATIONS_EXPORT_DIR`, default `dist/static-report`) holds the static bundle the API and workbench read: root JSON files (`manifest.json`, `sources.json`, `propositions.json`, …) plus per-run trees under `runs/<run-id>/` (manifests, `artifacts/`, stage traces). That is *analysis output* from pipeline exports.

**Source registry** (`SOURCE_REGISTRY_PATH`, default under your temp dir: `…/law-proposition-extractor/source-registry.json`) is a separate JSON file listing *registered* sources (legislation references you saved for repeat runs). It is **not** the same as the `source_records` embedded in a run bundle; the registry is the durable “saved sources” list used by “run from registry” flows.

## Clearing runs vs clearing everything

| Action | Export bundle | Registry file | Snapshot / derived caches |
|--------|----------------|---------------|---------------------------|
| **Clear runs only** | Wiped (directory recreated empty) | **Unchanged** | Unchanged |
| **Clear all** | Wiped | Reset to `{"version":"0.1","sources":[]}` | Cleared (`SOURCE_CACHE_DIR`, `DERIVED_CACHE_DIR`) |

Use **clear runs** when you want a clean slate for analysis output but intend to keep the same registered legislation entries. Use **clear all** when you want to remove registered sources and drop cached snapshots/derived artifacts as well (full local dev reset).

## CLI (law-proposition-extractor-pipeline)

From the repo, using the same paths as the API:

```bash
# Preview what would be removed (no deletion)
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline clear-operations-runs \
  --export-dir dist/static-report --dry-run

# Delete export bundle only; keep registry (requires --confirm)
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline clear-operations-runs \
  --export-dir dist/static-report --confirm

# Optional: align CLI with a custom registry file
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline clear-operations-runs \
  --export-dir dist/static-report --source-registry-path /tmp/law-proposition-extractor/source-registry.json --confirm
```

Full reset (registry + caches + export):

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline clear-operations-all \
  --export-dir dist/static-report --dry-run

uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline clear-operations-all \
  --export-dir dist/static-report --confirm \
  --source-registry-path /tmp/law-proposition-extractor/source-registry.json \
  --source-cache-dir /tmp/law-proposition-extractor/source-snapshots \
  --derived-cache-dir /tmp/law-proposition-extractor/derived-artifacts
```

Defaults for registry and cache dirs match `law_proposition_extractor_api.settings` / `SourceRegistryService` when flags are omitted.

## HTTP API (dev)

- `POST /ops/dev/clear/runs` — body `{"dry_run": true}` or `{"confirmation_text": "CLEAR RUNS"}` for destructive.
- `POST /ops/dev/clear/all` — body `{"dry_run": true}` or `{"confirmation_text": "CLEAR ALL"}` for destructive.

The running API uses its configured `OPERATIONS_EXPORT_DIR`, `SOURCE_REGISTRY_PATH`, and cache dirs from the environment.

## Workbench

On **Operations** → **Operations inspector**, the **Development / admin** card triggers the same endpoints with explicit confirmation phrases.
