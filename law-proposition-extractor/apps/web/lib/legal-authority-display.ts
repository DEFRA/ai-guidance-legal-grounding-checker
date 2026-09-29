import type { PropositionRow } from "@/lib/law-statements-index";
import {
  materialRoleLabel,
  propositionReadableText,
  type InlineLegalReference,
} from "@/lib/statement-inline-references";

const AUTHORITY_SUMMARY_MAX_LENGTH = 120;

function normalizeWhitespace(text: string): string {
  return text.trim().replace(/\s+/g, " ");
}

function truncateToOneLine(text: string, maxLength = AUTHORITY_SUMMARY_MAX_LENGTH): string {
  const cleaned = normalizeWhitespace(text);
  if (!cleaned) {
    return "";
  }
  const firstSentence = cleaned.match(/^[^.!?]+[.!?]?/)?.[0]?.trim() ?? cleaned;
  if (firstSentence.length <= maxLength) {
    return firstSentence.endsWith(".") ? firstSentence : `${firstSentence}.`;
  }
  return `${cleaned.slice(0, maxLength - 1).trim()}…`;
}

function firstReadablePropositionText(
  reference: InlineLegalReference,
  propositionById: Map<string, PropositionRow>,
): string | null {
  for (const propositionId of reference.propositionIds) {
    const text = propositionReadableText(propositionId, propositionById);
    if (text && text !== "Proposition text unavailable") {
      return text;
    }
  }
  return null;
}

function materialRoleSummary(reference: InlineLegalReference): string {
  const role = materialRoleLabel(reference.materialRole);
  switch (reference.materialRole) {
    case "constrains_statement":
      return "Sets conditions that constrain this statement.";
    case "confirms_statement":
      return "Confirms the legal basis for this statement.";
    case "exception_to_statement":
      return "Describes an exception to the main requirement.";
    case "defines_term":
      return "Defines a term used in this statement.";
    case "alters_effect":
      return "Alters how the main requirement applies.";
    default:
      return role.endsWith(".") ? role : `${role}.`;
  }
}

function containerSummary(
  reference: InlineLegalReference,
  propositionById: Map<string, PropositionRow>,
): string {
  const firstProposition = firstReadablePropositionText(reference, propositionById);
  if (firstProposition) {
    return truncateToOneLine(firstProposition);
  }
  if (reference.sourceExcerpt?.trim()) {
    return truncateToOneLine(reference.sourceExcerpt);
  }
  const count = reference.propositionIds.length;
  if (count > 1) {
    return `Groups ${count} supporting rules for this reference.`;
  }
  return "Groups the supporting rules for this reference.";
}

export function authorityHeadlineSummary(
  reference: InlineLegalReference,
  propositionById: Map<string, PropositionRow>,
): string {
  const firstProposition = firstReadablePropositionText(reference, propositionById);
  if (firstProposition) {
    return truncateToOneLine(firstProposition);
  }
  if (reference.sourceExcerpt?.trim()) {
    return truncateToOneLine(reference.sourceExcerpt);
  }
  if (reference.whyThisMatters?.trim()) {
    return truncateToOneLine(reference.whyThisMatters);
  }
  if (reference.status === "resolved_container" || reference.resolutionMode === "container") {
    return containerSummary(reference, propositionById);
  }
  return materialRoleSummary(reference);
}

export function authorityWhyItMatters(reference: InlineLegalReference): string | null {
  if (reference.whyThisMatters?.trim()) {
    return reference.whyThisMatters.trim();
  }
  if (reference.materialRole === "noise_or_unresolved") {
    return null;
  }
  return materialRoleSummary(reference);
}

export function supportingPropositionCountLabel(count: number): string {
  if (count === 0) {
    return "No supporting propositions";
  }
  return `${count} supporting proposition${count === 1 ? "" : "s"}`;
}

export const AUTHORITIES_IN_PLAY_LABEL = "Authorities in play";

export const AUTHORITIES_EMPTY_STATE =
  "Select a highlighted legal reference to add the authorities you are reviewing.";
