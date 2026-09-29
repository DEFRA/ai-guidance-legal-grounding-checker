import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";

export type ContextMaterialRole =
  | "confirm"
  | "constrain"
  | "exception"
  | "definition"
  | "alter_effect"
  | "noise";

export type IncorporationRecommendation =
  | "keep_external"
  | "inline_selectively"
  | "emit_multiple"
  | "defer_reviewer";

export type ContextEntryAssessment = {
  locator: string;
  kind: string;
  resolutionStatus: string;
  propositionIds: string[];
  propositionText: string;
  legalEffectType: string;
  propositionTier: string;
  role: ContextMaterialRole;
  textInStatement: boolean;
  textInCore: boolean;
  locatorReferencedInStatement: boolean;
};

const MATERIAL_ROLES = new Set<ContextMaterialRole>([
  "constrain",
  "exception",
  "definition",
  "alter_effect",
]);

const SUBSTANTIVE_EFFECTS = new Set([
  "obligation",
  "prohibition",
  "permission",
  "requirement",
  "application_scope",
]);

const CONDITION_MARKERS =
  /\b(unless|subject to|where|if|except|notwithstanding|provided that|in the case of)\b/i;

const EXCEPTION_MARKERS =
  /\b(unless|except|derogat|notwithstanding|does not apply|shall not apply)\b/i;

function normalizeText(text: string): string {
  return text
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .trim();
}

function textContainedIn(needle: string, haystack: string, minLength = 12): boolean {
  const normalizedNeedle = normalizeText(needle);
  const normalizedHaystack = normalizeText(haystack);
  if (!normalizedNeedle || normalizedNeedle.length < minLength) {
    return false;
  }
  return normalizedHaystack.includes(normalizedNeedle);
}

function normalizeLocator(locator: string): string {
  return normalizeText(locator)
    .replace(/^regulation\s+/, "regulation ")
    .replace(/^reg\s+/, "regulation ")
    .replace(/^schedule\s+/, "schedule ")
    .replace(/^article\s+/, "article ")
    .replace(/^paragraph\s+/, "paragraph ");
}

export function locatorReferencedInText(locator: string, text: string): boolean {
  const normalizedLocator = normalizeLocator(locator);
  if (!normalizedLocator) {
    return false;
  }
  const normalizedText = normalizeText(text);
  if (normalizedText.includes(normalizedLocator)) {
    return true;
  }

  const regulationMatch = normalizedLocator.match(
    /^(?:regulation|reg)\s+(\d+[a-z]?)(?:\((\d+[a-z]?)\))?$/,
  );
  if (regulationMatch) {
    const [, num, sub] = regulationMatch;
    const patterns = [`regulation ${num}`, `reg ${num}`, `regulation ${num}(${sub ?? ""})`].filter(
      (pattern) => pattern.trim(),
    );
    return patterns.some((pattern) => normalizedText.includes(pattern.replace(/\(\)$/, "")));
  }

  const scheduleMatch = normalizedLocator.match(/^schedule\s+(\d+[a-z]?)$/);
  if (scheduleMatch) {
    return normalizedText.includes(`schedule ${scheduleMatch[1]}`);
  }

  return false;
}

export function classifyContextEntry(input: {
  entry: NonNullable<LawStatementRow["required_context"]>[number];
  contextProp?: PropositionRow;
  coreProp?: PropositionRow;
  statementText: string;
  coreText: string;
}): ContextEntryAssessment {
  const locator = String(input.entry.locator ?? "").trim();
  const kind = String(input.entry.kind ?? "").trim();
  const resolutionStatus = String(input.entry.resolution_status ?? "").trim();
  const propositionIds = (input.entry.proposition_ids ?? [])
    .map((id) => String(id).trim())
    .filter(Boolean);
  const propositionText = String(input.contextProp?.proposition_text ?? "").trim();
  const legalEffectType = String(input.contextProp?.legal_effect_type ?? "").trim();
  const propositionTier = String(input.contextProp?.proposition_tier ?? "").trim();
  const textInStatement = textContainedIn(propositionText, input.statementText);
  const textInCore = textContainedIn(propositionText, input.coreText);
  const locatorReferencedInStatement = locatorReferencedInText(locator, input.statementText);

  let role: ContextMaterialRole = "noise";

  if (!propositionIds.length) {
    if (locatorReferencedInStatement && resolutionStatus !== "resolved") {
      role = "confirm";
    } else if (resolutionStatus === "external_reference") {
      role = "noise";
    } else {
      role = kind === "supporting_definition" ? "definition" : "noise";
    }
  } else if (legalEffectType === "definition" || propositionTier === "definitional_rule") {
    role = "definition";
  } else if (kind === "supporting_definition") {
    role = "definition";
  } else if (kind === "applicable_exception" || legalEffectType === "derogation" || EXCEPTION_MARKERS.test(propositionText)) {
    role = "exception";
  } else if (kind === "exception_target") {
    role = "alter_effect";
  } else if (kind === "trigger_condition") {
    role = "constrain";
  } else if (textInStatement || textInCore) {
    role = "confirm";
  } else {
    const coreEffect = String(input.coreProp?.legal_effect_type ?? "").trim();
    if (
      legalEffectType &&
      coreEffect &&
      legalEffectType !== coreEffect &&
      SUBSTANTIVE_EFFECTS.has(legalEffectType) &&
      SUBSTANTIVE_EFFECTS.has(coreEffect)
    ) {
      role = "alter_effect";
    } else if (
      kind === "incorporated_factors" ||
      kind === "host_rule" ||
      kind === "incorporated_rule"
    ) {
      role = "constrain";
    } else if (CONDITION_MARKERS.test(propositionText) && !CONDITION_MARKERS.test(input.coreText)) {
      role = "constrain";
    } else if (legalEffectType === "cross_reference" && locatorReferencedInStatement) {
      role = "confirm";
    } else if (resolutionStatus === "resolved") {
      role = "constrain";
    } else {
      role = "noise";
    }
  }

  return {
    locator,
    kind,
    resolutionStatus,
    propositionIds,
    propositionText,
    legalEffectType,
    propositionTier,
    role,
    textInStatement,
    textInCore,
    locatorReferencedInStatement,
  };
}

export function deriveIncorporationRecommendation(input: {
  entries: ContextEntryAssessment[];
  incorporationGap: boolean;
  unresolvedContextCount: number;
  resolvedMaterialCount: number;
}): IncorporationRecommendation {
  if (input.unresolvedContextCount > 0 && input.resolvedMaterialCount === 0) {
    return "defer_reviewer";
  }

  const materialEntries = input.entries.filter((entry) => MATERIAL_ROLES.has(entry.role));
  const unresolvedMaterial = materialEntries.filter((entry) => entry.propositionIds.length === 0);
  if (unresolvedMaterial.length > 0 && input.resolvedMaterialCount === 0) {
    return "defer_reviewer";
  }

  const substantiveMaterial = materialEntries.filter(
    (entry) =>
      entry.propositionIds.length > 0 && !entry.textInStatement && entry.role !== "definition",
  );
  if (substantiveMaterial.length >= 2) {
    return "emit_multiple";
  }

  if (input.incorporationGap && input.resolvedMaterialCount > 0) {
    return "inline_selectively";
  }

  const onlyConfirmOrNoise = materialEntries.length === 0;
  if (onlyConfirmOrNoise) {
    return "keep_external";
  }

  return input.unresolvedContextCount > 0 ? "defer_reviewer" : "keep_external";
}
