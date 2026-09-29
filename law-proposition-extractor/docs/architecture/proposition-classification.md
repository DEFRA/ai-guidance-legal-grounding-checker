# Proposition classification and normalisation

After LLM or heuristic **proposition extraction**, Law Proposition Extractor runs a deterministic **post-extraction normalisation** pass before inventory, export, and UI review. This separates *what the model guessed* from *how Law Proposition Extractor classifies, labels, and links* propositions for browsing and comparison.

Normalisation is **not** a second extraction: it does not change `proposition_text`. It enriches structured fields (`proposition_tier`, `legal_effect_type`, territory, labels, relationship keys) and moves machine metadata out of human review surfaces.

Pipeline order (current version **1**):

1. **Classification** — tier, legal effect, compliance/comparison flags, territory hints from text.
2. **Jurisdiction** — `source_jurisdiction`, instrument `extent` inheritance.
3. **Labelling** — specific `label`, `short_name`, `slug` (replaces generic extraction titles like “Territorial application”).
4. **Relationship keys** — `source_scoped_key`, `semantic_comparison_key`, explicit cross-reference targets (at record assembly).

Runs record this in `pipeline_case_inputs.proposition_normalisation` and **`MODEL.md`** (Settings section). Regression fixture: `tests/fixtures/regression/agricultural_land_england_territorial_application.json`.

---

## 1. Proposition tiers

Tiers group propositions for **explorer defaults** and review priority. They are derived primarily from `legal_effect_type`.

| Tier | Meaning | Typical legal effect types |
| --- | --- | --- |
| `instrument_metadata` | About the instrument itself, not a substantive duty | `citation`, `commencement`, `extent` |
| `scope_rule` | Where or to whom the instrument applies | `application_scope` |
| `definitional_rule` | Defines a term used elsewhere | `definition` |
| `substantive_rule` | Core rights, duties, prohibitions, permissions | `obligation`, `prohibition`, `permission`, `power`, … |
| `procedural_rule` | Process steps (records, notices, inspections, enforcement, appeals) | `recordkeeping`, `notification`, `certification`, `inspection`, `enforcement`, `appeal`, `derogation` |
| `relationship_reference` | Points at another provision without restating its substance | `cross_reference` |
| `unknown` | Could not classify confidently | `unknown` |

**Explorer default:** substantive, procedural, definitional, and scope tiers are shown; `instrument_metadata` (citation, commencement, extent rows) is hidden unless **Show instrument metadata** is enabled.

---

## 2. Legal effect types

`legal_effect_type` is the finest-grained normalised category. It drives tier, labelling templates, territory derivation, and relationship keys.

| Type | Role |
| --- | --- |
| `citation` | Short title / citation clause |
| `commencement` | In-force date or commencement trigger |
| `extent` | Geographic or territorial extent of the instrument as a whole |
| `application_scope` | What the instrument applies *to* (e.g. agricultural land in England) |
| `definition` | “X means …” / defined terms |
| `obligation` | Positive duty |
| `prohibition` | Prohibition or negative duty |
| `permission` | May / permitted conduct |
| `power` | Authority conferred on a person or body |
| `recordkeeping` | Records, registers, retention |
| `notification` | Notice or reporting duty |
| `certification` | Certificates or approvals |
| `inspection` | Inspection or audit powers/duties |
| `enforcement` | Offences, penalties, enforcement mechanics |
| `appeal` | Appeal or review rights |
| `derogation` | Exceptions or derogations |
| `cross_reference` | Explicit pointer to another provision |
| `unknown` | Unclassified |

Frontier models often mis-tag boilerplate (e.g. reg 1(d) application scope as `categories: ["obligation"]`). **`categories` is non-authoritative legacy LLM/tag output** — never use it to decide whether a row is an obligation, compliance-relevant, or a comparison anchor. Normalisation sets `proposition_tier`, `legal_effect_type`, `is_compliance_relevant`, and `is_comparison_anchor` from text and action patterns; `categories` is preserved for audit/display only. New code must not branch on `"obligation" in categories`.

---

## 3. Jurisdiction vs extent vs territorial application

| Field | Scope | Example |
| --- | --- | --- |
| **`jurisdiction` (legacy)** | Coarse host / routing label on the proposition and source (often `UK` or `EU`). Still used for jurisdiction chips and coarse filters. | `UK` on a retained EU regulation implemented in GB |
| **`source_jurisdiction`** | Normalised jurisdiction of the **source instrument** (host legal system). | `UK` for legislation.gov.uk principal regulations |
| **`extent`** | Territories where the **instrument as a whole** extends (from an extent proposition or source metadata). Inherited onto scope/obligation rows on the same source. | `England`, `Wales` from “These Regulations extend to England and Wales.” |
| **`territorial_application`** | Where **this proposition’s rule** applies (subset or application target). | `England` from “apply to agricultural land in England.” |

Do not treat legacy `jurisdiction` as a substitute for `territorial_application` when browsing scope: prefer territory chips and `territorial_application` filters in the proposition explorer.

---

## 4. Review notes vs extraction debug vs trace artifacts

| Surface | Storage | Shown to reviewers? |
| --- | --- | --- |
| **`review_notes`** | Dedicated field; human text only | Yes — “Review note” in UI |
| **`extraction_debug_meta`** | Structured dict on the proposition (slimmed: mode, evidence quote, display class; no raw LLM blobs) | No in default UI; optional in **raw** display mode |
| **`notes` (legacy)** | May have held `judit_extraction_meta:{...}`; split on load | Meta line is **not** shown as human notes |
| **Trace artifacts** | `proposition_extraction_traces.json`, `extraction_llm_call_traces.json`, per-chunk diagnostics | Ops / quality / “view extraction trace” — not inline on the card |

Rule of thumb: if it came from the model or pipeline diagnostics, it belongs in **debug meta or traces**, not `review_notes`.

---

## 5. Proposition explorer UI defaults

| Control | Default behaviour |
| --- | --- |
| **Tier / effect filters** | Any tier except hidden metadata; citation and commencement hidden unless instrument metadata is shown |
| **Compliance-relevant only** | Off; when on, keeps rows with `is_compliance_relevant === true` |
| **Comparison anchors only** | Off; when on, keeps rows with `is_comparison_anchor === true` |
| **Collapse scope/application** | On; `scope_rule` / `application_scope` groups move to a secondary “Scope & application” section |
| **Show instrument metadata** | Off |

**Flags (set by classification):**

- **`is_compliance_relevant`** — substantive duties and similar rules analysts must track; `false` for citation, commencement, extent, application scope, definitions (unless overridden).
- **`is_comparison_anchor`** — useful for cross-instrument alignment (definitions, scope, key structural anchors); `true` for application scope and definitions; `false` for pure citation/commencement.

Example: *“These Regulations apply to agricultural land in England.”* → tier `scope_rule`, effect `application_scope`, label **Application to agricultural land in England**, `is_compliance_relevant: false`, `is_comparison_anchor: true` — visible in default browse, excluded from compliance-only filter.

Cards show **Tier**, **Type**, **Label**, **Territory**, **Extent**, and the two flags. Stored extraction labels like “Territorial application” are preserved in `extraction_debug_meta.display_label`, not as the primary card title.

---

## 6. Relationship keys

| Key | Purpose |
| --- | --- |
| **`source_scoped_key`** | Stable id for this effect **within one source record** (includes source id + effect + subject/territory tokens). Used for inventory grouping and same-instrument dedup. |
| **`semantic_comparison_key`** | Effect + semantic tokens **without** source id — for “same kind of rule” across instruments, not automatic linking. |
| **`explicit_cross_reference_targets`** | Normalised targets parsed from text (“regulation 5”, “Article 10”). |
| **`cross_reference_targets`** | Auto-linked proposition ids — **only** same `source_record_id` + matching `source_scoped_key` (duplicate extractions). |

**Deprecated:** `cross_reference_key` — alias of `source_scoped_key` when set; do not generate new generic keys.

### Why generic keys are unsafe

Legacy keys such as `uk:these-regulations:apply-to` were built from placeholder subjects (“These Regulations”) and shallow actions (“apply to”). Many unrelated instruments share that wording, so:

- Inventory and graph edges **false-positive** across sources.
- Comparison UI implied equivalence where only the boilerplate matched.

Current keys hash **legal effect type**, **normalised subject/target text**, and **territory tokens**, and scope auto-links to a single source. Cross-instrument alignment uses `semantic_comparison_key` only as a **browse/compare hint**, not as an automatic merge.

---

## Related code and tests

| Area | Location |
| --- | --- |
| Enums | `packages/domain/src/law_proposition_extractor_domain/enums.py` |
| Classification | `proposition_classification.py`, `proposition_classification_pass.py` |
| Jurisdiction / territory | `proposition_jurisdiction.py`, `territory_normalization.py` |
| Labelling | `proposition_labelling.py` |
| Relationship keys | `proposition_relationship_keys.py` |
| Notes separation | `proposition_notes.py` |
| Explorer filters | `apps/web/components/proposition-classification-ui.tsx` |
| Regression fixture | `tests/fixtures/regression/agricultural_land_england_territorial_application.json` |

See also [ADR-0014: Proposition-first architecture](../decisions/adr-0014-proposition-first-architecture.md), [ADR-0018: Proposition identity and naming](../decisions/adr-0018-proposition-identity-and-naming.md), and [Artifacts — `MODEL.md`](../reference/artifacts.md).

---

## Run metadata (`MODEL.md` and case.json)

Every persisted or exported run should record whether normalisation ran.

| Source | Field | Content |
| --- | --- | --- |
| Run bundle | `pipeline_case_inputs.proposition_normalisation` | `{ "enabled": true, "version": "1", "passes": ["classification", "jurisdiction", "labelling", "relationship_keys"] }` |
| **`MODEL.md`** | Settings bullet + **Proposition normalisation** subsection (version/passes + quality counts) | Human-readable summary of the same |
| **`normalisation_quality.json`** | Per-check finding counts and rows (see [Artifacts](../reference/artifacts.md)) | Written on export; summarised in **MODEL.md** |
| **`case.json`** (optional) | `model_metadata.proposition_normalisation` | Operator note when replaying or ablating passes (e.g. disabled for a baseline) |
| **`case.json`** (optional) | `model_metadata.notes` | Free text; appears under Operator notes |

Example optional case overlay (does not disable passes unless the pipeline is changed to honour it):

```json
{
  "model_metadata": {
    "description": "Slurry principal-only frontier run",
    "notes": "Includes proposition normalisation v1 (classification + jurisdiction + labelling + keys).",
    "proposition_normalisation": {
      "enabled": true,
      "version": "1"
    }
  }
}
```

Runs produced **before** this metadata was added show `not recorded` in **MODEL.md**; re-export or inspect `propositions.json` for `proposition_tier` / `legal_effect_type` to infer whether normalisation was applied.

### Normalisation quality (export gates)

Each export runs deterministic **proposition normalisation quality gates** after classification, jurisdiction, labelling, and relationship-key passes. Results are written to `normalisation_quality.json` (and `NORMALISATION_QUALITY.md`) and summarised under **Proposition normalisation** in **`MODEL.md`**:

- **Warnings** do not necessarily invalidate a run (e.g. legacy `categories: ["obligation"]` on a scope row while `is_compliance_relevant` is correctly `false`).
- **Errors** mean the export should **not** be used for downstream comparison without review (e.g. retained `uk:these-regulations:*` keys after normalisation, or `judit_extraction_meta:` leaked into `review_notes`).
- **Legacy category conflicts** are expected during migration while LLM `categories` arrays are not rewritten; counts should trend down as extraction improves.

If `normalisation_quality.json` is absent, **MODEL.md** shows `Proposition normalisation quality: not recorded`.

**Slurry acceptance:** `tests/integration/test_slurry_normalisation_acceptance.py` re-applies normalisation v1 to `runs/slurry-gb-principal-5-frontier-export/propositions.json` (no LLM) and asserts count stability, relationship-key hygiene, explorer hiding, and 2018 reg 1(a)/(d) classification. Skipped when that export is not present locally.
