# Glossary

Controlled terminology for Law Proposition Extractor explainability. Prefer the **preferred term**
in UI and documentation.

| Preferred term | Definition | Avoid or qualify | Related concepts |
| --- | --- | --- | --- |
| source | Legal instrument Law Proposition Extractor is asked to analyse | “the law” as if already concluded | source record, snapshot |
| source record | Run-level identity/metadata row for a source | conflating with snapshot bytes | `sources.json` |
| source snapshot | Immutable consumed text instance with hash/provenance | treating retrieval time as legal as-of | manifestation, version |
| manifestation | Authority-supplied version label/evidence on a snapshot | “Law Proposition Extractor applied amendments” | revised/as-made fields |
| version | Run/cache identity or publisher revision field — always qualify which | bare “version” without qualifier | `version_id`, revision date |
| legal as-of date | Legal question: applicable law at a date | equating to `retrieved_at` | manifestation as-of fields |
| source fragment | Structural subdivision with locator | calling fragments propositions | hierarchy, frontier |
| extraction frontier | Fragments selected for extraction after coverage rules | bare “frontier” | structural extraction frontier |
| frontier extraction model | LLM extraction mode/alias for selected fragments | bare “frontier” | local/heuristic modes |
| proposition | Atomic retained legal statement | “complete applicable law” | effective-law statement |
| effective-law statement | Presentation unit with required context | raw proposition | required context |
| group | Qualify: legal rule group vs duplicate group | bare “group” | see below |
| legal rule group | Shared-fragment proposition set for legal targeting | UI explorer folder | typed relationships |
| duplicate group | Soft dedupe cluster for matching hygiene | legal target group | Proposition Matcher candidates |
| relationship | Qualify: generic locator vs typed legal | bare “relationship” | see below |
| typed legal relationship | `exception_to` / `triggered_by` with cue + safe target | ordinary cross-reference | legal rule group |
| source legal effect | Publisher-reported amendment/effect annotation in consumed XML | independent amendment application | outstanding effects |
| affecting instrument | Instrument that amends/affects another | assuming Law Proposition Extractor consumed it | independent consumption status |
| amendment applied | Claim that an amending change was applied to text | inferring from manifestation alone | source legal effect |
| resolved | Locator/reference resolved to a unique safe target | “understood legally” | resolution_basis |
| complete | Proposition completeness for pipeline/review | complete statement of all applicable law | completeness assessment |
| context | Attached material needed to read a statement | “Law Proposition Extractor knows full context” | required context |
| required context | Typed/ordinary context rows on effective-law statements | optional commentary | applicable_exception, … |
| candidate | Proposed or matching-queue row not yet a governance conclusion | retained proposition | extraction candidate, Proposition Matcher candidate |
| composition | Deterministic joining of stem/branch/leaf into a terminal proposition | model free-writing | structured-list path |
| decision explanation | Recorded processing decision with rule ID/evidence | chain-of-thought | heuristic |
| heuristic | Versioned registered rule | prompt ad-lib | registry |
| diagnostic | Structured warning/unresolved condition | silent failure | DecisionExplanation diagnostics |

## “Frontier” conflict

Three different ideas use the word *frontier*:

1. **Structural extraction frontier** — which fragments are selected for
   extraction after coverage rules.
2. **Frontier model / extraction mode** — an LLM extraction configuration
   (alias such as `frontier_extract`).
3. **Divergence frontier reasoning** — optional model-assisted divergence
   classification, where enabled.

**Preferred expanded wording in UI and docs:**

- say **structural extraction frontier** for selection sets
- say **frontier extraction mode** (or local/heuristic mode) for model routing
- say **divergence frontier reasoning** only for divergence

Avoid bare “frontier” in lawyer-facing copy.
