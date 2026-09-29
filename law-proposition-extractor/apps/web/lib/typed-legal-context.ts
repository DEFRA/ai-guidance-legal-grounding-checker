import { EXPORT_FIELD_UNAVAILABLE } from "@/lib/law-statements-composition";
import {
  contextRoleForKind,
  isResolvedTypedContext,
  isTypedContextKind,
  typedContextPropositionIds,
  type LawStatementPropRole,
  type LawStatementRow,
  type PropositionRow,
  type RequiredContextEntry,
  type TypedContextKind,
} from "@/lib/law-statements-index";

export type TypedLegalContextUiRole = "exception" | "displaced_rule" | "trigger";

export type TypedLegalContextItemView = {
  id: string;
  kind: TypedContextKind;
  uiRole: TypedLegalContextUiRole;
  propositionId: string;
  propositionText: string;
  sourceLocator: string;
  effectLabel: string | null;
  conciseExplanation: string;
  inheritedViaGroup: boolean;
  groupInheritanceLabel: string | null;
  targetCanonicalLocator: string | null;
  referencedLocator: string | null;
  referenceText: string | null;
  relationshipType: string | null;
  relationshipDirection: string | null;
  resolutionBasis: string | null;
  resolutionBasisLabel: string | null;
  inferenceBasis: string | null;
  inferenceBasisLabel: string | null;
  whyLinkedSummary: string;
  whyLinkedDetails: string[];
  missingTarget: boolean;
  relationshipId: string | null;
  legalRuleGroupId: string | null;
};

export type TypedLegalContextSections = {
  applicableExceptions: TypedLegalContextItemView[];
  exceptionTargets: TypedLegalContextItemView[];
  triggerConditions: TypedLegalContextItemView[];
};

const KIND_TO_UI_ROLE: Record<TypedContextKind, TypedLegalContextUiRole> = {
  applicable_exception: "exception",
  exception_target: "displaced_rule",
  trigger_condition: "trigger",
};

const RESOLUTION_BASIS_LABEL: Record<string, string> = {
  explicit: "Explicit reference",
  structural_relative: "Structural relative reference",
  instrument_wide: "Instrument-wide reference",
  unresolved: "Unresolved",
};

const INFERENCE_BASIS_LABEL: Record<string, string> = {
  explicit_exception_cue: "Explicit exception wording",
  explicit_trigger_cue: "Explicit triggering wording",
};

const RELATIONSHIP_TYPE_LABEL: Record<string, string> = {
  exception_to: "exception to",
  triggered_by: "triggered by",
};

export function formatCanonicalLocatorLabel(locator: string | null | undefined): string {
  const raw = String(locator ?? "").trim();
  if (!raw) {
    return "";
  }
  if (!raw.includes(":")) {
    return raw;
  }
  const parts = raw.split(":").filter(Boolean);
  const labels: string[] = [];
  for (let index = 0; index + 1 < parts.length; index += 2) {
    const kind = parts[index]!;
    const value = parts[index + 1]!;
    const kindLabel =
      index === 0
        ? kind.charAt(0).toUpperCase() + kind.slice(1).toLowerCase()
        : kind.toLowerCase();
    labels.push(`${kindLabel} ${value}`);
  }
  return labels.join(", ");
}

export function resolutionBasisLabel(basis: string | null | undefined): string | null {
  const trimmed = String(basis ?? "").trim();
  if (!trimmed) {
    return null;
  }
  return RESOLUTION_BASIS_LABEL[trimmed] ?? trimmed.replaceAll("_", " ");
}

export function inferenceBasisLabel(basis: string | null | undefined): string | null {
  const trimmed = String(basis ?? "").trim();
  if (!trimmed) {
    return null;
  }
  return INFERENCE_BASIS_LABEL[trimmed] ?? trimmed.replaceAll("_", " ");
}

export function groupInheritanceLabel(entry: RequiredContextEntry): string | null {
  if (!entry.inherited_via_group) {
    return null;
  }
  const canonical = formatCanonicalLocatorLabel(entry.target_canonical_locator);
  const reference = String(entry.reference_text ?? "").trim();
  if (canonical) {
    return `Applies through rule group: ${canonical}`;
  }
  if (reference) {
    return `Applies through ${reference} rule group`;
  }
  return "Inherited through rule group";
}

function conciseExplanationForEntry(
  kind: TypedContextKind,
  entry: RequiredContextEntry,
  sectionSize: number,
): string {
  const reference =
    String(entry.reference_text ?? "").trim() ||
    formatCanonicalLocatorLabel(entry.referenced_locator) ||
    formatCanonicalLocatorLabel(entry.target_canonical_locator) ||
    String(entry.locator ?? "").trim();
  const viaGroup = Boolean(entry.inherited_via_group);

  if (kind === "applicable_exception") {
    if (viaGroup && reference) {
      return `Applies through rule group targeting ${reference}.`;
    }
    return "Direct applicable exception from an explicit relationship.";
  }

  if (kind === "exception_target") {
    if (viaGroup && reference) {
      const plural =
        sectionSize > 1
          ? `That rule group contains these ${sectionSize} propositions.`
          : "That rule group contains this proposition.";
      return `The source disapplies ${reference}. ${plural}`;
    }
    return "This exception explicitly displaces the referenced rule.";
  }

  if (viaGroup && reference) {
    return `Inherited from the cases in ${reference}.`;
  }
  return "Direct trigger condition from an explicit relationship.";
}

function whyLinkedSummary(kind: TypedContextKind, entry: RequiredContextEntry): string {
  const viaGroup = Boolean(entry.inherited_via_group);
  if (kind === "applicable_exception") {
    return viaGroup
      ? 'This proposition is an applicable exception because an explicit "exception_to" relationship targets a rule group containing the current proposition.'
      : 'This proposition is an applicable exception because an explicit "exception_to" relationship targets the current proposition.';
  }
  if (kind === "exception_target") {
    return viaGroup
      ? "This exception explicitly disapplies the referenced rule group."
      : "This exception explicitly displaces the referenced rule.";
  }
  return viaGroup
    ? "The current obligation applies in the cases referred to in the target rule group."
    : "The current obligation applies in the referenced triggering case.";
}

function whyLinkedDetails(entry: RequiredContextEntry): string[] {
  const details: string[] = [];
  const reference =
    String(entry.reference_text ?? "").trim() ||
    formatCanonicalLocatorLabel(entry.referenced_locator) ||
    String(entry.referenced_locator ?? "").trim();
  if (reference) {
    details.push(`Reference: ${reference}`);
  }
  const resolvedTarget = formatCanonicalLocatorLabel(entry.target_canonical_locator);
  if (resolvedTarget) {
    details.push(`Resolved target: ${resolvedTarget}`);
  }
  const basis = resolutionBasisLabel(entry.resolution_basis);
  if (basis) {
    details.push(`Resolution: ${basis}`);
  }
  const inference = inferenceBasisLabel(entry.inference_basis);
  if (inference) {
    details.push(`Inference: ${inference}`);
  }
  if (entry.inherited_via_group === false) {
    details.push("Link: direct");
  } else if (entry.inherited_via_group === true) {
    details.push("Link: inherited through rule group");
  }
  const relationshipType = String(entry.relationship_type ?? "").trim();
  if (relationshipType) {
    details.push(
      `Relationship: ${RELATIONSHIP_TYPE_LABEL[relationshipType] ?? relationshipType.replaceAll("_", " ")}`,
    );
  }
  return details;
}

function effectLabelForProposition(proposition: PropositionRow | undefined): string | null {
  const effect = proposition?.legal_effect_type?.trim();
  if (!effect) {
    return null;
  }
  return effect.replaceAll("_", " ");
}

function stableItemId(kind: string, propositionId: string, relationshipId: string | null, index: number): string {
  return `${kind}:${propositionId}:${relationshipId ?? "none"}:${index}`;
}

function buildItemView(input: {
  entry: RequiredContextEntry;
  kind: TypedContextKind;
  propositionId: string;
  propositionById: Map<string, PropositionRow>;
  sectionSize: number;
  index: number;
}): TypedLegalContextItemView {
  const { entry, kind, propositionId, propositionById, sectionSize, index } = input;
  const proposition = propositionById.get(propositionId);
  const relationshipId = String(entry.relationship_id ?? "").trim() || null;
  const missingTarget = !propositionId;

  return {
    id: stableItemId(kind, propositionId || "missing", relationshipId, index),
    kind,
    uiRole: KIND_TO_UI_ROLE[kind],
    propositionId,
    propositionText:
      proposition?.proposition_text?.trim() ||
      proposition?.label?.trim() ||
      (missingTarget ? "Target proposition missing" : EXPORT_FIELD_UNAVAILABLE),
    sourceLocator:
      proposition?.fragment_locator?.trim() ||
      String(entry.locator ?? "").trim() ||
      EXPORT_FIELD_UNAVAILABLE,
    effectLabel: effectLabelForProposition(proposition),
    conciseExplanation: conciseExplanationForEntry(kind, entry, sectionSize),
    inheritedViaGroup: Boolean(entry.inherited_via_group),
    groupInheritanceLabel: groupInheritanceLabel(entry),
    targetCanonicalLocator: String(entry.target_canonical_locator ?? "").trim() || null,
    referencedLocator: String(entry.referenced_locator ?? "").trim() || null,
    referenceText: String(entry.reference_text ?? "").trim() || null,
    relationshipType: String(entry.relationship_type ?? "").trim() || null,
    relationshipDirection: String(entry.relationship_direction ?? "").trim() || null,
    resolutionBasis: String(entry.resolution_basis ?? "").trim() || null,
    resolutionBasisLabel: resolutionBasisLabel(entry.resolution_basis),
    inferenceBasis: String(entry.inference_basis ?? "").trim() || null,
    inferenceBasisLabel: inferenceBasisLabel(entry.inference_basis),
    whyLinkedSummary: whyLinkedSummary(kind, entry),
    whyLinkedDetails: whyLinkedDetails(entry),
    missingTarget,
    relationshipId,
    legalRuleGroupId: String(entry.legal_rule_group_id ?? "").trim() || null,
  };
}

function collectKindItems(
  statement: LawStatementRow,
  kind: TypedContextKind,
  propositionById: Map<string, PropositionRow>,
): TypedLegalContextItemView[] {
  const matching = (statement.required_context ?? []).filter(
    (entry) => String(entry.kind ?? "").trim() === kind,
  );
  const provisionalCount = matching.reduce(
    (count, entry) => count + Math.max(1, (entry.proposition_ids ?? []).filter((id) => id.trim()).length),
    0,
  );
  const items: TypedLegalContextItemView[] = [];
  const seenPropositionIds = new Set<string>();

  for (const [entryIndex, entry] of matching.entries()) {
    const propositionIds = (entry.proposition_ids ?? []).map((id) => String(id).trim()).filter(Boolean);
    if (propositionIds.length === 0) {
      items.push(
        buildItemView({
          entry,
          kind,
          propositionId: "",
          propositionById,
          sectionSize: provisionalCount || 1,
          index: entryIndex,
        }),
      );
      continue;
    }
    for (const [propIndex, propositionId] of propositionIds.entries()) {
      if (seenPropositionIds.has(propositionId)) {
        continue;
      }
      seenPropositionIds.add(propositionId);
      items.push(
        buildItemView({
          entry,
          kind,
          propositionId,
          propositionById,
          sectionSize: provisionalCount,
          index: entryIndex * 100 + propIndex,
        }),
      );
    }
  }

  items.sort((left, right) => {
    const leftOrder = propositionById.get(left.propositionId)?.source_order;
    const rightOrder = propositionById.get(right.propositionId)?.source_order;
    const leftHasOrder = typeof leftOrder === "number" && Number.isFinite(leftOrder);
    const rightHasOrder = typeof rightOrder === "number" && Number.isFinite(rightOrder);
    if (leftHasOrder && rightHasOrder && leftOrder !== rightOrder) {
      return leftOrder! - rightOrder!;
    }
    if (leftHasOrder !== rightHasOrder) {
      return leftHasOrder ? -1 : 1;
    }
    const locatorDelta = left.sourceLocator.localeCompare(right.sourceLocator);
    if (locatorDelta !== 0) {
      return locatorDelta;
    }
    return left.propositionId.localeCompare(right.propositionId);
  });

  return items;
}

export function buildTypedLegalContextSections(
  statement: LawStatementRow,
  propositionById: Map<string, PropositionRow>,
): TypedLegalContextSections {
  return {
    applicableExceptions: collectKindItems(statement, "applicable_exception", propositionById),
    exceptionTargets: collectKindItems(statement, "exception_target", propositionById),
    triggerConditions: collectKindItems(statement, "trigger_condition", propositionById),
  };
}

export function hasTypedLegalContext(sections: TypedLegalContextSections): boolean {
  return (
    sections.applicableExceptions.length > 0 ||
    sections.exceptionTargets.length > 0 ||
    sections.triggerConditions.length > 0
  );
}

export function partitionRequiredContext(statement: LawStatementRow): {
  typed: RequiredContextEntry[];
  generic: RequiredContextEntry[];
} {
  const typedIds = typedContextPropositionIds(statement);
  const typed: RequiredContextEntry[] = [];
  const generic: RequiredContextEntry[] = [];

  for (const entry of statement.required_context ?? []) {
    const kind = String(entry.kind ?? "").trim();
    if (isTypedContextKind(kind)) {
      typed.push(entry);
      continue;
    }
    const propIds = (entry.proposition_ids ?? []).map((id) => String(id).trim()).filter(Boolean);
    // Drop generic entries wholly covered by typed context for the same propositions.
    if (propIds.length > 0 && propIds.every((id) => typedIds.has(id))) {
      continue;
    }
    generic.push(entry);
  }

  return { typed, generic };
}

export function statementWithGenericContextOnly(statement: LawStatementRow): LawStatementRow {
  const { generic } = partitionRequiredContext(statement);
  return {
    ...statement,
    required_context: generic,
  };
}

export function uiRoleForContextKind(kind: string | undefined | null): LawStatementPropRole {
  return contextRoleForKind(kind);
}

export function typedContextMissingTargetWarning(entry: RequiredContextEntry): boolean {
  if (!isTypedContextKind(entry.kind)) {
    return false;
  }
  const hasRelationship = Boolean(String(entry.relationship_id ?? "").trim());
  const hasTarget = (entry.proposition_ids ?? []).some((id) => String(id).trim());
  return hasRelationship && !hasTarget;
}

export function shouldTreatContextAsAmbiguous(entry: RequiredContextEntry): boolean {
  if (isResolvedTypedContext(entry)) {
    return false;
  }
  return String(entry.resolution_status ?? "").trim() === "ambiguous";
}

export function sectionHeadingForTypedRole(
  role: TypedLegalContextUiRole,
  count: number,
): { title: string; description: string } {
  if (role === "exception") {
    return {
      title: count === 1 ? "Applicable exception" : "Applicable exceptions",
      description: "Exceptions that apply to this rule.",
    };
  }
  if (role === "displaced_rule") {
    return {
      title: count === 1 ? "Rule displaced by this exception" : "Rules displaced by this exception",
      description:
        count > 1
          ? "Included because the source disapplies a rule group containing these propositions."
          : "The rule this exception displaces.",
    };
  }
  return {
    title: "Triggered in these cases",
    description: "Cases that trigger this consequential obligation.",
  };
}
