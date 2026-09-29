import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import type { PropositionRow } from "@/lib/law-statements-index";

export type SourceEffectCategory =
  | "insertion"
  | "substitution"
  | "omission"
  | "repeal"
  | "revocation"
  | "commencement"
  | "extent"
  | "editorial_note"
  | "other"
  | "unknown";

export type SourceEffectStatus =
  | "source_marks_applied"
  | "source_marks_outstanding"
  | "source_marks_partially_applied"
  | "source_status_unknown";

export type SourceEffectRepresentationStatus =
  | "annotation_present"
  | "effect_metadata_present"
  | "revised_text_reference_present"
  | "unknown";

export type AffectingInstrumentConsumptionStatus =
  | "consumed_in_current_run"
  | "present_in_source_register_but_not_consumed"
  | "not_matched"
  | "not_assessed";

export type ConsumptionMatchBasis =
  | "canonical_authority_uri"
  | "authority_identifier"
  | "celex_identifier"
  | "normalized_citation"
  | "source_register_uri"
  | "no_match"
  | "insufficient_identity"
  | "ambiguous_identity";

export type OutstandingEffectsStatus =
  | "source_reports_none"
  | "source_reports_present"
  | "source_status_unknown";

export type SourceEffectLinkageStatus = "linked" | "locator_only" | "unresolved";

export type ConsumptionMatchEvidenceRow = {
  basis?: ConsumptionMatchBasis | string | null;
  effect_value?: string | null;
  normalized_identity?: string | null;
  matched_source_record_id?: string | null;
  matched_source_snapshot_ids?: string[] | null;
  matched_source_title?: string | null;
  matched_source_citation?: string | null;
  register_uri?: string | null;
  candidate_source_record_ids?: string[] | null;
  [key: string]: unknown;
};

export type SourceLegalEffectRow = {
  id: string;
  source_record_id: string;
  source_snapshot_id: string;
  annotation_id?: string | null;
  annotation_label?: string | null;
  effect_category?: SourceEffectCategory | string | null;
  raw_effect_category?: string | null;
  effect_description?: string | null;
  affected_locator?: string | null;
  affected_source_fragment_id?: string | null;
  affecting_instrument_uri?: string | null;
  affecting_instrument_citation?: string | null;
  affecting_instrument_title?: string | null;
  affecting_instrument_provision?: string | null;
  effect_date?: string | null;
  effect_status?: SourceEffectStatus | string | null;
  source_representation_status?: SourceEffectRepresentationStatus | string | null;
  independent_consumption_status?: AffectingInstrumentConsumptionStatus | string | null;
  matched_source_record_id?: string | null;
  matched_source_snapshot_ids?: string[] | null;
  consumption_match_basis?: ConsumptionMatchBasis | string | null;
  matched_instrument_identity?: string | null;
  consumption_match_evidence?: ConsumptionMatchEvidenceRow[] | null;
  source_evidence?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};

export type SourceLegalEffectLinkRow = {
  id: string;
  effect_id: string;
  source_record_id: string;
  source_snapshot_id: string;
  source_fragment_id?: string | null;
  affected_locator?: string | null;
  linkage_status?: SourceEffectLinkageStatus | string | null;
  source_evidence?: Record<string, unknown>;
};

export type SourceLegalEffectsDiagnosticRow = {
  code?: string;
  effect_id?: string;
  annotation_id?: string;
  affected_locator?: string;
  message?: string;
  [key: string]: unknown;
};

export type SourceLegalEffectsArtifactRow = {
  schema_version?: string;
  run_id?: string;
  effects: SourceLegalEffectRow[];
  effect_links: SourceLegalEffectLinkRow[];
  outstanding_effects_status: OutstandingEffectsStatus | string;
  diagnostics: SourceLegalEffectsDiagnosticRow[];
  metadata?: Record<string, unknown>;
};

export type EffectRelevanceKind = "direct" | "structural";

export type RelevantSourceLegalEffect = {
  effect: SourceLegalEffectRow;
  relevance: EffectRelevanceKind;
  matchedLink: SourceLegalEffectLinkRow | null;
  matchedLocator: string | null;
  matchedFragmentId: string | null;
  ancestorLocator: string | null;
  ancestorFragmentId: string | null;
};

export type SourceLegalEffectsView = {
  sourceRecordId: string;
  sourceSnapshotId: string | null;
  totalEffectCount: number;
  relevant: RelevantSourceLegalEffect[];
  other: SourceLegalEffectRow[];
  outstandingEffectsStatus: OutstandingEffectsStatus;
  diagnostics: SourceLegalEffectsDiagnosticRow[];
  hasEffects: boolean;
  relevantLabels: string[];
};

function trimOrNull(value: unknown): string | null {
  const text = String(value ?? "").trim();
  return text ? text : null;
}

function fragmentRowId(fragment: SourceFragmentRow): string | null {
  return trimOrNull(fragment.id) ?? trimOrNull(fragment.fragment_id);
}

export function emptySourceLegalEffectsArtifact(
  runId?: string | null,
): SourceLegalEffectsArtifactRow {
  return {
    schema_version: "1",
    run_id: trimOrNull(runId) ?? undefined,
    effects: [],
    effect_links: [],
    outstanding_effects_status: "source_status_unknown",
    diagnostics: [],
    metadata: { missing_artifact: true },
  };
}

export function parseSourceLegalEffectsArtifact(
  payload: unknown,
  runId?: string | null,
): SourceLegalEffectsArtifactRow {
  if (!payload || typeof payload !== "object") {
    return emptySourceLegalEffectsArtifact(runId);
  }
  const root = payload as Record<string, unknown>;
  const nested =
    root.source_legal_effects && typeof root.source_legal_effects === "object"
      ? (root.source_legal_effects as Record<string, unknown>)
      : root;

  const effectsRaw = nested.effects;
  const linksRaw = nested.effect_links;
  const diagnosticsRaw = nested.diagnostics;

  return {
    schema_version: trimOrNull(nested.schema_version) ?? "1",
    run_id: trimOrNull(nested.run_id) ?? trimOrNull(runId) ?? undefined,
    effects: Array.isArray(effectsRaw)
      ? (effectsRaw.filter((row) => row && typeof row === "object") as SourceLegalEffectRow[])
      : [],
    effect_links: Array.isArray(linksRaw)
      ? (linksRaw.filter((row) => row && typeof row === "object") as SourceLegalEffectLinkRow[])
      : [],
    outstanding_effects_status:
      trimOrNull(nested.outstanding_effects_status) ?? "source_status_unknown",
    diagnostics: Array.isArray(diagnosticsRaw)
      ? (diagnosticsRaw.filter(
          (row) => row && typeof row === "object",
        ) as SourceLegalEffectsDiagnosticRow[])
      : [],
    metadata:
      nested.metadata && typeof nested.metadata === "object"
        ? (nested.metadata as Record<string, unknown>)
        : {},
  };
}

export function humanCanonicalLocator(locator: string | null | undefined): string | null {
  const raw = trimOrNull(locator);
  if (!raw) {
    return null;
  }
  const parts = raw.split(":").filter(Boolean);
  if (parts.length >= 2 && parts[0] === "article") {
    const article = parts[1];
    if (parts[2] === "paragraph" && parts[3]) {
      return `Article ${article}, paragraph ${parts[3]}`;
    }
    return `Article ${article}`;
  }
  return raw;
}

export function effectCategoryLabel(category: string | null | undefined): string {
  switch (trimOrNull(category)) {
    case "insertion":
      return "Insertion";
    case "substitution":
      return "Substitution";
    case "omission":
      return "Omission";
    case "repeal":
      return "Repeal";
    case "revocation":
      return "Revocation";
    case "commencement":
      return "Commencement";
    case "extent":
      return "Extent";
    case "editorial_note":
      return "Editorial note";
    case "other":
      return "Other";
    case "unknown":
    default:
      return "Unknown category";
  }
}

export function effectStatusLabel(status: string | null | undefined): string {
  switch (trimOrNull(status)) {
    case "source_marks_applied":
      return "Source marks this effect as applied/incorporated";
    case "source_marks_outstanding":
      return "Source marks this effect as outstanding";
    case "source_marks_partially_applied":
      return "Source marks this effect as partially applied";
    case "source_status_unknown":
    default:
      return "Not stated by consumed source";
  }
}

export function sourceRepresentationStatusLabel(status: string | null | undefined): string {
  switch (trimOrNull(status)) {
    case "annotation_present":
      return "Annotation present in consumed CLML";
    case "effect_metadata_present":
      return "Effect metadata present in consumed source";
    case "revised_text_reference_present":
      return "Revised-text reference present in consumed source";
    case "unknown":
    default:
      return "Not stated by consumed source";
  }
}

export function independentConsumptionStatusLabel(status: string | null | undefined): string {
  switch (trimOrNull(status)) {
    case "consumed_in_current_run":
      return "Affecting instrument independently consumed in this run";
    case "present_in_source_register_but_not_consumed":
      return "Present in the run's source register, but not independently consumed";
    case "not_matched":
      return "No matching independently consumed source was found in this run";
    case "not_assessed":
    default:
      return "Independent consumption could not be assessed from the available identifiers";
  }
}

export function consumptionMatchDisplay(effect: SourceLegalEffectRow): {
  title: string | null;
  citation: string | null;
  snapshotCount: number;
  matchedSourceRecordId: string | null;
} {
  const evidenceRows = Array.isArray(effect.consumption_match_evidence)
    ? effect.consumption_match_evidence
    : [];
  const primary = evidenceRows.find(
    (row) => row && typeof row === "object" && (row.matched_source_title || row.matched_source_citation),
  );
  const snapshotIds = Array.isArray(effect.matched_source_snapshot_ids)
    ? effect.matched_source_snapshot_ids.filter((id) => String(id ?? "").trim())
    : [];
  return {
    title: trimOrNull(primary?.matched_source_title),
    citation: trimOrNull(primary?.matched_source_citation),
    snapshotCount: snapshotIds.length,
    matchedSourceRecordId: trimOrNull(effect.matched_source_record_id),
  };
}

export function outstandingEffectsStatusLabel(status: string | null | undefined): string {
  switch (trimOrNull(status)) {
    case "source_reports_present":
      return "The consumed source reports outstanding effects.";
    case "source_reports_none":
      return "The consumed source explicitly reports none.";
    case "source_status_unknown":
    default:
      return "Not established from the consumed source metadata.";
  }
}

export function normalizeOutstandingEffectsStatus(
  status: string | null | undefined,
): OutstandingEffectsStatus {
  const value = trimOrNull(status);
  if (value === "source_reports_present" || value === "source_reports_none") {
    return value;
  }
  return "source_status_unknown";
}

/** True when `candidate` is a proper structural ancestor of `descendant` by locator path. */
export function isLocatorAncestor(
  candidate: string | null | undefined,
  descendant: string | null | undefined,
): boolean {
  const parent = trimOrNull(candidate);
  const child = trimOrNull(descendant);
  if (!parent || !child || parent === child) {
    return false;
  }
  return child.startsWith(`${parent}:`);
}

const TOP_LEVEL_PROVISION_KIND =
  /^(article|regulation|rule|section|annex|schedule):[^:]+$/i;
const CONTAINER_KIND = /^(part|chapter|title|division|document)(:|$)/i;

/**
 * Defensive check for legacy bundles with invalid sibling-article parentage.
 * Does not replace ingestion fixes; only rejects clearly non-ancestral edges.
 */
export function isPlausibleStructuralParentEdge(
  parent: SourceFragmentRow | null | undefined,
  child: SourceFragmentRow | null | undefined,
): boolean {
  if (!parent || !child) {
    return false;
  }
  const parentId = fragmentRowId(parent);
  const childId = fragmentRowId(child);
  if (!parentId || !childId || parentId === childId) {
    return false;
  }
  const parentSource = trimOrNull(parent.source_record_id);
  const childSource = trimOrNull(child.source_record_id);
  if (parentSource && childSource && parentSource !== childSource) {
    return false;
  }
  const parentSnap = trimOrNull(parent.source_snapshot_id);
  const childSnap = trimOrNull(child.source_snapshot_id);
  if (parentSnap && childSnap && parentSnap !== childSnap) {
    return false;
  }
  const parentLocator = trimOrNull(parent.locator);
  const childLocator = trimOrNull(child.locator);
  if (!parentLocator || !childLocator) {
    return false;
  }
  if (isLocatorAncestor(parentLocator, childLocator)) {
    return true;
  }
  // Genuine exported containers may parent top-level provisions without a
  // locator-prefix relationship (part:4 → article:49a).
  if (CONTAINER_KIND.test(parentLocator) && TOP_LEVEL_PROVISION_KIND.test(childLocator)) {
    return true;
  }
  if (CONTAINER_KIND.test(parentLocator) && CONTAINER_KIND.test(childLocator)) {
    return true;
  }
  // Sibling top-level provisions are never ancestors of each other.
  if (
    TOP_LEVEL_PROVISION_KIND.test(parentLocator) &&
    TOP_LEVEL_PROVISION_KIND.test(childLocator)
  ) {
    return false;
  }
  return false;
}

function ancestorFragmentIds(
  fragmentId: string | null,
  fragmentById: Map<string, SourceFragmentRow>,
): string[] {
  const ancestors: string[] = [];
  const seen = new Set<string>();
  let current = fragmentId;
  while (current && !seen.has(current)) {
    seen.add(current);
    const row =
      fragmentById.get(current) ??
      [...fragmentById.values()].find((item) => fragmentRowId(item) === current);
    if (!row) {
      break;
    }
    const parentId = trimOrNull(row.parent_fragment_id);
    if (!parentId) {
      break;
    }
    const parentRow =
      fragmentById.get(parentId) ??
      [...fragmentById.values()].find((item) => fragmentRowId(item) === parentId);
    // Skip invalid legacy edges (e.g. article:49a → article:1) without hiding
    // valid non-prefix container parents.
    if (!isPlausibleStructuralParentEdge(parentRow, row)) {
      break;
    }
    ancestors.push(parentId);
    current = parentId;
  }
  return ancestors;
}

function linksForEffect(
  effectId: string,
  links: SourceLegalEffectLinkRow[],
): SourceLegalEffectLinkRow[] {
  return links.filter((link) => trimOrNull(link.effect_id) === effectId);
}

function compareEffects(a: SourceLegalEffectRow, b: SourceLegalEffectRow): number {
  const labelA = trimOrNull(a.annotation_label) ?? "";
  const labelB = trimOrNull(b.annotation_label) ?? "";
  if (labelA !== labelB) {
    return labelA.localeCompare(labelB, undefined, { numeric: true });
  }
  const annA = trimOrNull(a.annotation_id) ?? "";
  const annB = trimOrNull(b.annotation_id) ?? "";
  if (annA !== annB) {
    return annA.localeCompare(annB);
  }
  return a.id.localeCompare(b.id);
}

function compareRelevant(a: RelevantSourceLegalEffect, b: RelevantSourceLegalEffect): number {
  // Deterministic label/id order; relevance kind is shown on each card.
  return compareEffects(a.effect, b.effect);
}

export type PropositionEffectMatchInput = {
  proposition: PropositionRow;
  artifact: SourceLegalEffectsArtifactRow;
  fragmentById: Map<string, SourceFragmentRow>;
};

/**
 * Match source-reported effects to a proposition using snapshot-scoped
 * fragment and locator links only. Never matches by text or citation alone.
 */
export function findRelevantEffectsForProposition(
  input: PropositionEffectMatchInput,
): RelevantSourceLegalEffect[] {
  const { proposition, artifact, fragmentById } = input;
  const sourceRecordId = trimOrNull(proposition.source_record_id);
  const snapshotId = trimOrNull(proposition.source_snapshot_id);
  const fragmentId = trimOrNull(proposition.source_fragment_id);
  const fragment =
    (fragmentId ? fragmentById.get(fragmentId) : null) ??
    (fragmentId
      ? [...fragmentById.values()].find((row) => fragmentRowId(row) === fragmentId)
      : null) ??
    null;
  const locator =
    trimOrNull(proposition.fragment_locator) ?? trimOrNull(fragment?.locator) ?? null;

  if (!sourceRecordId || !snapshotId) {
    return [];
  }

  const ancestorIds = new Set(ancestorFragmentIds(fragmentId, fragmentById));
  const scopedEffects = artifact.effects.filter(
    (effect) =>
      trimOrNull(effect.source_record_id) === sourceRecordId &&
      trimOrNull(effect.source_snapshot_id) === snapshotId,
  );
  const scopedLinks = artifact.effect_links.filter(
    (link) =>
      trimOrNull(link.source_record_id) === sourceRecordId &&
      trimOrNull(link.source_snapshot_id) === snapshotId,
  );

  const relevant: RelevantSourceLegalEffect[] = [];

  for (const effect of scopedEffects) {
    const effectLinks = linksForEffect(effect.id, scopedLinks);
    let best: RelevantSourceLegalEffect | null = null;

    const consider = (candidate: RelevantSourceLegalEffect) => {
      if (!best) {
        best = candidate;
        return;
      }
      if (candidate.relevance === "direct" && best.relevance !== "direct") {
        best = candidate;
      }
    };

    for (const link of effectLinks) {
      const linkFragmentId = trimOrNull(link.source_fragment_id);
      const linkLocator = trimOrNull(link.affected_locator);

      if (fragmentId && linkFragmentId && linkFragmentId === fragmentId) {
        consider({
          effect,
          relevance: "direct",
          matchedLink: link,
          matchedLocator: linkLocator ?? locator,
          matchedFragmentId: linkFragmentId,
          ancestorLocator: null,
          ancestorFragmentId: null,
        });
        continue;
      }

      if (locator && linkLocator && linkLocator === locator) {
        consider({
          effect,
          relevance: "direct",
          matchedLink: link,
          matchedLocator: linkLocator,
          matchedFragmentId: linkFragmentId,
          ancestorLocator: null,
          ancestorFragmentId: null,
        });
        continue;
      }

      if (fragmentId && linkFragmentId && ancestorIds.has(linkFragmentId)) {
        consider({
          effect,
          relevance: "structural",
          matchedLink: link,
          matchedLocator: locator,
          matchedFragmentId: fragmentId,
          ancestorLocator: linkLocator,
          ancestorFragmentId: linkFragmentId,
        });
        continue;
      }

      if (locator && linkLocator && isLocatorAncestor(linkLocator, locator)) {
        consider({
          effect,
          relevance: "structural",
          matchedLink: link,
          matchedLocator: locator,
          matchedFragmentId: fragmentId,
          ancestorLocator: linkLocator,
          ancestorFragmentId: linkFragmentId,
        });
      }
    }

    // Fallback: effect-level fragment / locator fields when links are sparse.
    if (!best) {
      const effectFragmentId = trimOrNull(effect.affected_source_fragment_id);
      const effectLocator = trimOrNull(effect.affected_locator);
      if (fragmentId && effectFragmentId && effectFragmentId === fragmentId) {
        best = {
          effect,
          relevance: "direct",
          matchedLink: null,
          matchedLocator: effectLocator ?? locator,
          matchedFragmentId: effectFragmentId,
          ancestorLocator: null,
          ancestorFragmentId: null,
        };
      } else if (locator && effectLocator && effectLocator === locator) {
        best = {
          effect,
          relevance: "direct",
          matchedLink: null,
          matchedLocator: effectLocator,
          matchedFragmentId: effectFragmentId,
          ancestorLocator: null,
          ancestorFragmentId: null,
        };
      } else if (fragmentId && effectFragmentId && ancestorIds.has(effectFragmentId)) {
        best = {
          effect,
          relevance: "structural",
          matchedLink: null,
          matchedLocator: locator,
          matchedFragmentId: fragmentId,
          ancestorLocator: effectLocator,
          ancestorFragmentId: effectFragmentId,
        };
      } else if (locator && effectLocator && isLocatorAncestor(effectLocator, locator)) {
        best = {
          effect,
          relevance: "structural",
          matchedLink: null,
          matchedLocator: locator,
          matchedFragmentId: fragmentId,
          ancestorLocator: effectLocator,
          ancestorFragmentId: effectFragmentId,
        };
      }
    }

    if (best) {
      relevant.push(best);
    }
  }

  relevant.sort(compareRelevant);
  return relevant;
}

export function buildSourceLegalEffectsView(input: {
  sourceRecordId: string;
  sourceSnapshotId: string | null;
  propositions: PropositionRow[];
  artifact: SourceLegalEffectsArtifactRow;
  fragmentById: Map<string, SourceFragmentRow>;
}): SourceLegalEffectsView {
  const sourceRecordId = trimOrNull(input.sourceRecordId) ?? "";
  const sourceSnapshotId = trimOrNull(input.sourceSnapshotId);
  const snapshotEffects = input.artifact.effects.filter((effect) => {
    if (trimOrNull(effect.source_record_id) !== sourceRecordId) {
      return false;
    }
    if (!sourceSnapshotId) {
      return false;
    }
    return trimOrNull(effect.source_snapshot_id) === sourceSnapshotId;
  });

  const byEffectId = new Map<string, RelevantSourceLegalEffect>();
  for (const proposition of input.propositions) {
    const matches = findRelevantEffectsForProposition({
      proposition,
      artifact: input.artifact,
      fragmentById: input.fragmentById,
    });
    for (const match of matches) {
      const existing = byEffectId.get(match.effect.id);
      if (!existing || (match.relevance === "direct" && existing.relevance !== "direct")) {
        byEffectId.set(match.effect.id, match);
      }
    }
  }

  const relevant = [...byEffectId.values()].sort(compareRelevant);
  const relevantIds = new Set(relevant.map((item) => item.effect.id));
  const other = snapshotEffects
    .filter((effect) => !relevantIds.has(effect.id))
    .sort(compareEffects);

  const relevantLabels = relevant
    .map((item) => trimOrNull(item.effect.annotation_label))
    .filter((label): label is string => Boolean(label));

  const snapshotDiagnostics = input.artifact.diagnostics.filter((diag) => {
    const effectId = trimOrNull(diag.effect_id);
    if (!effectId) {
      return true;
    }
    return snapshotEffects.some((effect) => effect.id === effectId);
  });

  return {
    sourceRecordId,
    sourceSnapshotId,
    totalEffectCount: snapshotEffects.length,
    relevant,
    other,
    outstandingEffectsStatus: normalizeOutstandingEffectsStatus(
      input.artifact.outstanding_effects_status,
    ),
    diagnostics: snapshotDiagnostics,
    hasEffects: snapshotEffects.length > 0,
    relevantLabels,
  };
}

export function affectingInstrumentDisplay(effect: SourceLegalEffectRow): {
  primary: string | null;
  citation: string | null;
  title: string | null;
  uri: string | null;
  provision: string | null;
} {
  const title = trimOrNull(effect.affecting_instrument_title);
  const citation = trimOrNull(effect.affecting_instrument_citation);
  const uri = trimOrNull(effect.affecting_instrument_uri);
  const provision = trimOrNull(effect.affecting_instrument_provision);
  const parts = [title, citation].filter(Boolean);
  return {
    primary: parts.length > 0 ? parts.join(" / ") : citation ?? title ?? uri,
    citation,
    title,
    uri,
    provision,
  };
}

export function isHttpAffectingInstrumentUri(uri: string | null | undefined): boolean {
  const text = trimOrNull(uri);
  if (!text) {
    return false;
  }
  try {
    const parsed = new URL(text);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function structuralLinkExplanation(match: RelevantSourceLegalEffect): string {
  if (match.relevance === "direct") {
    const locatorLabel =
      humanCanonicalLocator(match.matchedLocator) ??
      humanCanonicalLocator(match.effect.affected_locator) ??
      "this provision";
    return `Directly linked to ${locatorLabel}`;
  }
  const ancestorLabel =
    humanCanonicalLocator(match.ancestorLocator) ??
    (match.ancestorFragmentId ? match.ancestorFragmentId : "an ancestor provision");
  return (
    `Linked through source structure: The consumed CLML associates this annotation with ` +
    `${ancestorLabel}, which contains the reviewed paragraph.`
  );
}

export function usefulEffectDiagnostics(
  diagnostics: SourceLegalEffectsDiagnosticRow[],
): SourceLegalEffectsDiagnosticRow[] {
  const usefulCodes = new Set([
    "source_effect_reference_unresolved",
    "source_effect_affected_fragment_unresolved",
  ]);
  return diagnostics.filter((diag) => {
    const code = trimOrNull(diag.code);
    return Boolean(code && usefulCodes.has(code));
  });
}

export function effectHasAffectingInstrumentIds(effects: SourceLegalEffectRow[]): boolean {
  return effects.some(
    (effect) =>
      Boolean(trimOrNull(effect.affecting_instrument_uri)) ||
      Boolean(trimOrNull(effect.affecting_instrument_citation)) ||
      Boolean(trimOrNull(effect.affecting_instrument_title)),
  );
}

export function effectHasFragmentLinks(
  effects: SourceLegalEffectRow[],
  links: SourceLegalEffectLinkRow[],
): boolean {
  const effectIds = new Set(effects.map((effect) => effect.id));
  return links.some(
    (link) =>
      effectIds.has(link.effect_id) &&
      (Boolean(trimOrNull(link.source_fragment_id)) ||
        trimOrNull(link.linkage_status) === "linked"),
  );
}
