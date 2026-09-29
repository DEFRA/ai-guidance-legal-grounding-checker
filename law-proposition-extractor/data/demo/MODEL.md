# Model & run metadata

Human-readable summary of how this Law Proposition Extractor run was produced.
Generated **2026-06-03T15:29:04.301510Z**.

> **Run quality:** pass_with_warnings — 2 warnings.

## Run identity

| Field | Value |
| --- | --- |
| **Description** | Movement record keeping |
| **Input pipeline** | Law Proposition Extractor case file |
| **Input asset** | traceability |
| **Run ID** | `run-001` |
| **Workflow** | `single_jurisdiction` |
| **Completed** | 2026-06-03T15:29:04.300281Z |
| **Output directory** | `.` |

## Models used

_Provider models resolved from: config:/Users/bram/Code/defra/ai-eu-trade-accelerator/law-proposition-extractor/config/litellm.yaml._

_No model aliases recorded (heuristic run or traces not retained)._

## Runtime

| Phase | Duration |
| --- | --- |
| source intake | 0s |
| proposition extraction | 0s |
| proposition inventory | 0s |
| proposition pairing | 0s |
| divergence classification | 0s |
| narrative generation | 0s |
| Σ stage traces (excl. export) | 0s |

## Indicative cost estimate

| Measure | Value |
| --- | --- |
| Estimated input tokens (all traces) | 0 |
| Estimated input tokens (live calls only) | 0 |

_No USD estimate for heuristic runs._

## Additional cost estimates

_Not estimated. Add `model_metadata.additional_cost_estimates` in case.json (e.g. `co2_kg`, `water_litres`) to record CO₂, water, or other impacts._

## Settings & notes

- **Extraction mode:** `heuristic` (requested `heuristic`)
- **Fallback policy:** `fallback`
- **Sources / bundled propositions:** 2 / 4
- **Run quality:** pass_with_warnings (2 warnings)
- **Pipeline version:** `0.1.0`

### Operator notes

_None. Set `model_metadata.notes` in case.json for free-text about prompts, ablations, or why this run is interesting._
