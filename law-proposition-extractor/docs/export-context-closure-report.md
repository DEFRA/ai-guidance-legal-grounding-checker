# Export context closure report

**Before export:** `/Users/bram/Code/defra/ai-eu-trade-accelerator/law-proposition-extractor/runs/slurry-gb-principal-5-current-export`
**After export:** `/Users/bram/Code/defra/ai-eu-trade-accelerator/law-proposition-extractor/runs/slurry-gb-principal-5-current-export`

Deterministic before/after comparison of required-context locator closure in effective-law export.

## Summary

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Unresolved required_context entries | 283 | 44 | -239 |
| Entries with empty proposition_ids | 283 | 44 | -239 |
| Workbench-resolvable but export-empty divergence | 239 | 0 | -239 |
| Container locator resolutions (all statements) | 86 | 385 | +299 |
| Ambiguous entries (unresolved population) | 0 | 0 | +0 |
| Resolved entries with proposition_ids | 288 | 246 | -42 |

## Top unresolved locators (after)

| Locator | Count |
| --- | ---: |
| `schedule 5` | 6 |
| `article 27` | 5 |
| `paragraph 3(1)` | 4 |
| `annex 1` | 2 |
| `paragraph 17(1)` | 2 |
| `paragraph 17(2)` | 2 |
| `paragraph 18(1)` | 2 |
| `regulation 45` | 2 |
| `regulation 104` | 2 |
| `regulation 63` | 2 |
| `article 11(3)` | 1 |
| `paragraph 7(2)` | 1 |
| `annex iii` | 1 |
| `annex 3` | 1 |
| `paragraph 4(1)` | 1 |
| `article 5` | 1 |
| `paragraph 17` | 1 |
| `paragraph 11(1)` | 1 |
| `paragraph 15(1)` | 1 |
| `paragraph 10(1)` | 1 |
| `regulation 42` | 1 |
| `regulation 42(1)` | 1 |
| `paragraph 7(1)` | 1 |
| `regulation 32` | 1 |
| `paragraph 14(2)` | 1 |

## Reproduction

Re-derive effective law (no LLM):

```bash
uv run --package law-proposition-extractor-pipeline python -c "
from pathlib import Path
import json
from law_proposition_extractor_pipeline.export_context_closure_verification import derive_effective_law_for_export
root = Path('law-proposition-extractor/runs/slurry-gb-principal-5-current-export')
payload = derive_effective_law_for_export(root)
(root / 'effective_law_statements.json').write_text(json.dumps(payload, indent=2))
"
```

Generate this report:

```bash
uv run --package law-proposition-extractor-pipeline python scripts/generate_export_context_closure_report.py
```
