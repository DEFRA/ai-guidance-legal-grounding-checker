# Follow-up: remove deprecated component aliases

**Status:** stub (create tracker ticket when GitHub auth available; link here)

**Target release:** `rename+1` — the coordinated pipeline release immediately after the
descriptive-name rename lands.

## Scope

- Delete the isolated compatibility layer under [`compat/`](../compat/) and per-package
  deprecated console-script / import shims
- Delete compatibility-only tests
- Remove deprecated env-var aliases (`ADA_*`, `JUDIT_*`, `RADIA_*`, legacy CLI names, etc.)
- Final verification that supported callers (RUNBOOK users, sibling repos, local scripts)
  have migrated to canonical names
- Confirm `scripts/check_legacy_component_names.py` allowlist can drop compat-layer paths

## Out of scope

- Rewriting historic run artifacts
- Changing frozen domain ID prefixes (`susan-…`, `judit_extraction_meta:`, `prop:`, …)
- Behaviour / prompt / model changes

## Links

- Migration guide: [migration-component-rename.md](migration-component-rename.md)
- Manifest: [`components.manifest.yaml`](../components.manifest.yaml)
- Historic glossary: [`NAMES.md`](../NAMES.md)
