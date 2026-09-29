import {
  normalizeCrossReferenceLocator,
  parseLocatorStructuralContext,
  primarySourceRecordIdForStatement,
  resolveContextRequirement,
} from "@/lib/context-locator-resolution";
import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import { EXPORT_FIELD_UNAVAILABLE } from "@/lib/law-statements-composition";
import { locatorReferencedInText } from "@/lib/export-context-incorporation";
import type {
  ContextIncorporationEntry,
  LawStatementRow,
  PropositionRow,
} from "@/lib/law-statements-index";
import {
  assessmentContextStatus,
  type AssessmentContextStatus,
  type AssessmentContextView,
} from "@/lib/review-workbench-views";

export type InlineReferenceAccent = "resolved" | "resolved_container" | "material" | "warning";

export type InlineLegalReference = {
  id: string;
  sourceId: string;
  locator: string;
  label: string;
  start: number;
  end: number;
  accent: InlineReferenceAccent;
  status: AssessmentContextStatus;
  materialRole: string;
  incorporationLabel: string;
  whyThisMatters: string | null;
  summary: string;
  propositionIds: string[];
  sourceFragmentIds: string[];
  sourceExcerpt: string | null;
  resolvedLocator: string | null;
  rawLocators: string[];
  resolutionMode?: "exact" | "container" | "partial";
};

export type LegalTextSource = {
  id: string;
  text: string;
  structuralContextLocator?: string | null;
};

export type WorkbenchLegalReferences = {
  referencesBySourceId: Map<string, InlineLegalReference[]>;
  partsBySourceId: Map<string, StatementTextPart[]>;
  allReferences: InlineLegalReference[];
};

export type StatementTextPart =
  | { kind: "text"; text: string; key: string }
  | { kind: "reference"; referenceId: string; text: string; key: string };

const MATERIAL_ROLES = new Set([
  "constrains_statement",
  "defines_term",
  "alters_effect",
  "exception_to_statement",
]);

const MATERIAL_ROLE_LABEL: Record<string, string> = {
  confirms_statement: "Confirms statement",
  constrains_statement: "Constrains statement",
  exception_to_statement: "Exception",
  defines_term: "Defines term",
  alters_effect: "Alters legal effect",
  noise_or_unresolved: "Unresolved noise",
};

const STATUS_LABEL: Record<AssessmentContextStatus, string> = {
  resolved: "Resolved",
  resolved_container: "Resolved container",
  partially_resolved: "Partially resolved",
  unresolved: "Unresolved",
  ambiguous: "Ambiguous",
  external: "External reference",
};

function normalizeText(text: string): string {
  return text
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .trim();
}

function isSafeSourceLocatorForInlineRef(locator: string): boolean {
  const trimmed = locator.trim();
  if (!trimmed || trimmed === EXPORT_FIELD_UNAVAILABLE) {
    return false;
  }
  if (!trimmed.includes(":")) {
    return true;
  }
  const normalized = normalizeCrossReferenceLocator(trimmed);
  return Boolean(normalized) && !normalized.includes(":");
}

function collectCandidateLocators(statement: LawStatementRow): string[] {
  const locators = new Set<string>();

  for (const entry of statement.required_context ?? []) {
    const locator = String(entry.locator ?? "").trim();
    if (locator) {
      locators.add(locator);
    }
  }

  for (const span of statement.composition_trace ?? []) {
    for (const locator of span.context_locators ?? []) {
      const trimmed = String(locator).trim();
      if (trimmed) {
        locators.add(trimmed);
      }
    }
    for (const locator of span.source_locators ?? []) {
      if (isSafeSourceLocatorForInlineRef(locator)) {
        locators.add(normalizeCrossReferenceLocator(locator));
      }
    }
  }

  return Array.from(locators);
}

function buildLocatorTextVariants(locator: string): string[] {
  const variants = new Set<string>();
  const trimmed = locator.trim();
  if (!trimmed) {
    return [];
  }
  variants.add(trimmed);
  variants.add(normalizeCrossReferenceLocator(trimmed));

  const titleCased = trimmed.replace(/\b([a-z])/g, (char) => char.toUpperCase());
  variants.add(titleCased);

  const regulationMatch = normalizeText(trimmed).match(
    /^(?:regulation|reg)\s+(\d+[a-z]?)(?:\(([^)]+)\))?$/,
  );
  if (regulationMatch) {
    const [, num, sub] = regulationMatch;
    variants.add(`regulation ${num}${sub ? `(${sub})` : ""}`);
    variants.add(`Regulation ${num}${sub ? `(${sub})` : ""}`);
  }

  const scheduleMatch = normalizeText(trimmed).match(/^schedule\s+(\d+[a-z]?)$/);
  if (scheduleMatch) {
    variants.add(`Schedule ${scheduleMatch[1]}`);
    variants.add(`schedule ${scheduleMatch[1]}`);
  }

  return Array.from(variants).filter(Boolean).sort((left, right) => right.length - left.length);
}

function findCaseInsensitiveSpan(
  text: string,
  needle: string,
): { start: number; end: number } | null {
  const normalizedText = normalizeText(text);
  const normalizedNeedle = normalizeText(needle);
  if (!normalizedNeedle) {
    return null;
  }
  const relative = normalizedText.indexOf(normalizedNeedle);
  if (relative < 0) {
    return null;
  }

  let normalizedIndex = 0;
  let start = 0;
  while (start < text.length && normalizedIndex < relative) {
    if (/\s/.test(text[start]!)) {
      while (start < text.length && /\s/.test(text[start]!)) {
        start += 1;
      }
      normalizedIndex += 1;
      continue;
    }
    start += 1;
    normalizedIndex += 1;
  }

  let end = start;
  let matched = 0;
  while (end < text.length && matched < normalizedNeedle.length) {
    if (/\s/.test(text[end]!)) {
      while (end < text.length && /\s/.test(text[end]!)) {
        end += 1;
      }
      matched += 1;
      continue;
    }
    end += 1;
    matched += 1;
  }

  return { start, end };
}

export function findLocatorTextSpan(
  statementText: string,
  locator: string,
  fromIndex = 0,
): { start: number; end: number; label: string } | null {
  const slice = statementText.slice(fromIndex);
  for (const variant of buildLocatorTextVariants(locator)) {
    const span = findCaseInsensitiveSpan(slice, variant);
    if (span) {
      const start = fromIndex + span.start;
      const end = fromIndex + span.end;
      return {
        start,
        end,
        label: statementText.slice(start, end),
      };
    }
  }
  return null;
}

function findAllLocatorTextSpans(
  statementText: string,
  locator: string,
): Array<{ start: number; end: number; label: string }> {
  const spans: Array<{ start: number; end: number; label: string }> = [];
  let fromIndex = 0;
  while (fromIndex < statementText.length) {
    const span = findLocatorTextSpan(statementText, locator, fromIndex);
    if (!span) {
      break;
    }
    spans.push(span);
    fromIndex = span.end;
  }
  return spans;
}

function fragmentIdsFromContext(context?: AssessmentContextView): string[] {
  if (!context) {
    return [];
  }
  const ids = new Set<string>();
  for (const fragment of context.fragments) {
    if (fragment.fragmentId) {
      ids.add(fragment.fragmentId);
    }
  }
  for (const child of context.children ?? []) {
    for (const fragment of child.fragments) {
      if (fragment.fragmentId) {
        ids.add(fragment.fragmentId);
      }
    }
  }
  return Array.from(ids);
}

function propositionIdsForFragments(
  fragmentIds: readonly string[],
  propositionById: Map<string, PropositionRow>,
): string[] {
  const fragmentIdSet = new Set(fragmentIds);
  const ids: string[] = [];
  for (const [propositionId, proposition] of propositionById) {
    const sourceFragmentId = String(proposition.source_fragment_id ?? "").trim();
    if (sourceFragmentId && fragmentIdSet.has(sourceFragmentId)) {
      ids.push(propositionId);
    }
  }
  return ids;
}

function collectPropositionIds(input: {
  locator: string;
  statement: LawStatementRow;
  context?: AssessmentContextView;
  incorporation?: ContextIncorporationEntry;
  propositionById: Map<string, PropositionRow>;
}): string[] {
  const ids = new Set<string>();

  for (const entry of input.statement.required_context ?? []) {
    if (String(entry.locator ?? "").trim() === input.locator) {
      for (const propositionId of entry.proposition_ids ?? []) {
        const trimmed = String(propositionId).trim();
        if (trimmed) {
          ids.add(trimmed);
        }
      }
    }
  }

  for (const propositionId of input.incorporation?.proposition_ids ?? []) {
    const trimmed = String(propositionId).trim();
    if (trimmed) {
      ids.add(trimmed);
    }
  }

  for (const propositionId of propositionIdsForFragments(
    fragmentIdsFromContext(input.context),
    input.propositionById,
  )) {
    ids.add(propositionId);
  }

  for (const span of input.statement.composition_trace ?? []) {
    if (!(span.context_locators ?? []).includes(input.locator)) {
      continue;
    }
    for (const propositionId of span.proposition_ids ?? []) {
      const trimmed = String(propositionId).trim();
      if (trimmed) {
        ids.add(trimmed);
      }
    }
  }

  return Array.from(ids);
}

function incorporationLabelForEntry(entry?: ContextIncorporationEntry): string {
  if (!entry) {
    return "Not assessed";
  }
  if (entry.incorporation.should_split) {
    return "Should split into multiple statements";
  }
  if (entry.incorporation.should_inline) {
    return "Should inline into statement text";
  }
  if (entry.incorporation.reviewer_required) {
    return "Reviewer attention required";
  }
  if (entry.incorporation.external_context) {
    return "Keep as external context";
  }
  return "No incorporation change suggested";
}

function accentForReference(input: {
  status: AssessmentContextStatus;
  incorporation?: ContextIncorporationEntry;
  materialRole: string;
}): InlineReferenceAccent {
  if (
    input.status === "external" ||
    input.status === "unresolved" ||
    input.status === "ambiguous"
  ) {
    return "warning";
  }
  if (
    input.incorporation?.incorporation.should_inline ||
    input.incorporation?.incorporation.should_split ||
    MATERIAL_ROLES.has(input.materialRole)
  ) {
    return "material";
  }
  if (input.status === "resolved_container") {
    return "resolved_container";
  }
  return "resolved";
}

export function buildReferenceSummary(reference: InlineLegalReference): string {
  if (reference.status === "resolved_container" || reference.resolutionMode === "container") {
    return `This expands to ${reference.propositionIds.length} propositions / ${reference.sourceFragmentIds.length} source fragments`;
  }
  if (reference.propositionIds.length === 1) {
    return "Shows the linked proposition for this reference.";
  }
  if (reference.propositionIds.length > 1) {
    return `Shows ${reference.propositionIds.length} linked propositions for this reference.`;
  }
  return "No linked propositions were found for this reference.";
}

export function propositionReadableText(
  propositionId: string,
  propositionById: Map<string, PropositionRow>,
): string {
  const proposition = propositionById.get(propositionId);
  return (
    proposition?.proposition_text?.trim() ??
    proposition?.label?.trim() ??
    proposition?.short_name?.trim() ??
    "Proposition text unavailable"
  );
}

function sourceExcerptFromContext(context?: AssessmentContextView): string | null {
  const excerpt = context?.fragments[0]?.excerpt?.trim();
  return excerpt || null;
}

export function whyThisMattersLabel(input: {
  materialRole: string;
  incorporation?: ContextIncorporationEntry;
  inheritedContextLabel?: string;
  contextReason?: string;
}): string | null {
  if (input.inheritedContextLabel?.trim()) {
    return input.inheritedContextLabel.trim();
  }
  if (MATERIAL_ROLES.has(input.materialRole)) {
    return materialRoleLabel(input.materialRole);
  }
  if (input.incorporation?.incorporation.reviewer_required) {
    return "Reviewer attention required for this reference";
  }
  if (input.incorporation?.incorporation.should_inline) {
    return "This context should be written into the statement text";
  }
  if (input.incorporation?.incorporation.should_split) {
    return "This reference may require splitting into multiple statements";
  }
  if (input.contextReason?.trim()) {
    return input.contextReason.trim();
  }
  return null;
}

type RelativeReferenceSpan = {
  start: number;
  end: number;
  label: string;
  locator: string;
};

const RELATIVE_REFERENCE_PATTERNS: Array<{
  pattern: RegExp;
  toLocator: (match: RegExpExecArray) => string;
}> = [
  {
    pattern: /\b(paragraphs?)\s+(\d+[a-z]?)(?:\s*\(([^)]+)\))?/gi,
    toLocator: (match) => {
      const sub = match[3] ? `(${match[3]})` : "";
      return `${match[1]!.toLowerCase()} ${match[2]!.toLowerCase()}${sub}`;
    },
  },
  {
    pattern: /\b(regulations?|regs?\.)\s+(\d+[a-z]?)(?:\s*\(([^)]+)\))?/gi,
    toLocator: (match) => {
      const sub = match[3] ? `(${match[3]})` : "";
      return `regulation ${match[2]!.toLowerCase()}${sub}`;
    },
  },
  {
    pattern: /\b(Schedule)\s+(\d+[a-z]?)\b/g,
    toLocator: (match) => `Schedule ${match[2]}`,
  },
  {
    pattern: /\b(Part)\s+(\d+[a-z]?)\b/g,
    toLocator: (match) => `Part ${match[2]}`,
  },
];

function spansOverlap(
  left: { start: number; end: number },
  right: { start: number; end: number },
): boolean {
  return left.start < right.end && left.end > right.start;
}

function detectRelativeReferenceSpans(
  text: string,
  occupiedSpans: Array<{ start: number; end: number }>,
): RelativeReferenceSpan[] {
  const spans: RelativeReferenceSpan[] = [];
  for (const { pattern, toLocator } of RELATIVE_REFERENCE_PATTERNS) {
    pattern.lastIndex = 0;
    let match: RegExpExecArray | null = pattern.exec(text);
    while (match) {
      const start = match.index;
      const end = start + match[0].length;
      const overlaps =
        occupiedSpans.some((span) => spansOverlap({ start, end }, span)) ||
        spans.some((span) => spansOverlap({ start, end }, span));
      if (!overlaps) {
        spans.push({
          start,
          end,
          label: match[0],
          locator: toLocator(match),
        });
      }
      match = pattern.exec(text);
    }
  }
  return spans;
}

function buildStructuralContext(
  structuralContextLocator: string | null | undefined,
  sourceRecordId: string | null,
) {
  if (!structuralContextLocator?.trim()) {
    return sourceRecordId ? { sourceRecordId, segments: [] } : null;
  }
  const parsed = parseLocatorStructuralContext(structuralContextLocator);
  return {
    sourceRecordId,
    segments: parsed?.segments ?? [],
  };
}

function resolveReferenceMetadata(input: {
  locator: string;
  statement: LawStatementRow;
  assessmentContext: AssessmentContextView[];
  propositionById: Map<string, PropositionRow>;
  sourceFragments: SourceFragmentRow[];
  fragmentById: Map<string, SourceFragmentRow>;
  structuralContextLocator?: string | null;
  sourceRecordId: string | null;
}) {
  const incorporationByLocator = new Map(
    (input.statement.context_incorporation ?? []).map((entry) => [entry.locator, entry]),
  );
  const contextByLocator = new Map(
    input.assessmentContext.map((context) => [context.locator, context]),
  );
  let context = contextByLocator.get(input.locator);
  let incorporation = incorporationByLocator.get(input.locator);
  let resolvedLocator = context?.resolvedLocator ?? null;

  if (!context) {
    const resolution = resolveContextRequirement(
      { locator: input.locator, resolution_status: "unresolved", proposition_ids: [] },
      {
        sourceRecordId: input.sourceRecordId,
        structuralContext: buildStructuralContext(
          input.structuralContextLocator,
          input.sourceRecordId,
        ),
        sourceFragments: input.sourceFragments,
        propositionById: input.propositionById,
        fragmentById: input.fragmentById,
      },
    );
    const status = assessmentContextStatus(resolution);
    context = {
      locator: input.locator,
      status,
      inheritedContextLabel: resolution.inheritedContextLabel,
      resolvedLocator: resolution.resolvedLocator,
      reason: resolution.reason,
      fragments: resolution.fragments,
      children: resolution.children,
    };
    resolvedLocator = resolution.resolvedLocator ?? null;
  }

  const status = context.status;
  const materialRole = incorporation?.material_role ?? "noise_or_unresolved";
  const propositionIds = collectPropositionIds({
    locator: input.locator,
    statement: input.statement,
    context,
    incorporation,
    propositionById: input.propositionById,
  });
  const sourceFragmentIds = fragmentIdsFromContext(context);
  const resolutionMode =
    status === "resolved_container"
      ? "container"
      : status === "partially_resolved"
        ? "partial"
        : status === "resolved"
          ? "exact"
          : undefined;

  return {
    locator: input.locator,
    accent: accentForReference({ status, incorporation, materialRole }),
    status,
    materialRole,
    incorporationLabel: incorporationLabelForEntry(incorporation),
    whyThisMatters: whyThisMattersLabel({
      materialRole,
      incorporation,
      inheritedContextLabel: context.inheritedContextLabel,
      contextReason: context.reason,
    }),
    propositionIds,
    sourceFragmentIds,
    sourceExcerpt: sourceExcerptFromContext(context),
    resolvedLocator,
    rawLocators: [
      input.locator,
      ...Array.from(
        new Set(
          (input.statement.composition_trace ?? []).flatMap((traceSpan) =>
            (traceSpan.source_locators ?? []).filter((sourceLocator) =>
              normalizeCrossReferenceLocator(sourceLocator) === input.locator ||
              sourceLocator === input.locator,
            ),
          ),
        ),
      ),
    ],
    resolutionMode,
  };
}

function collectKnownLocators(
  statement: LawStatementRow,
  assessmentContext: AssessmentContextView[],
): string[] {
  const locators = new Set(collectCandidateLocators(statement));
  for (const context of assessmentContext) {
    if (context.locator.trim()) {
      locators.add(context.locator);
    }
  }
  return Array.from(locators);
}

export function buildLegalTextReferences(input: {
  source: LegalTextSource;
  statement: LawStatementRow;
  assessmentContext: AssessmentContextView[];
  propositionById: Map<string, PropositionRow>;
  sourceFragments: SourceFragmentRow[];
  fragmentById: Map<string, SourceFragmentRow>;
  sourceRecordId: string | null;
  knownLocators?: string[];
}): InlineLegalReference[] {
  const text = input.source.text ?? "";
  if (!text.trim()) {
    return [];
  }

  const knownLocators = input.knownLocators ?? collectKnownLocators(input.statement, input.assessmentContext);
  const references: InlineLegalReference[] = [];
  const occupiedSpans: Array<{ start: number; end: number }> = [];

  for (const locator of knownLocators) {
    if (!locatorReferencedInText(locator, text)) {
      continue;
    }
    const metadata = resolveReferenceMetadata({
      locator,
      statement: input.statement,
      assessmentContext: input.assessmentContext,
      propositionById: input.propositionById,
      sourceFragments: input.sourceFragments,
      fragmentById: input.fragmentById,
      structuralContextLocator: input.source.structuralContextLocator,
      sourceRecordId: input.sourceRecordId,
    });

    for (const span of findAllLocatorTextSpans(text, locator)) {
      occupiedSpans.push({ start: span.start, end: span.end });
      const reference: InlineLegalReference = {
        ...metadata,
        sourceId: input.source.id,
        id: `${input.source.id}::${locator}::${span.start}`,
        label: span.label,
        start: span.start,
        end: span.end,
        summary: "",
      };
      reference.summary = buildReferenceSummary(reference);
      references.push(reference);
    }
  }

  for (const span of detectRelativeReferenceSpans(text, occupiedSpans)) {
    const alreadyCovered = references.some(
      (reference) => reference.start === span.start && reference.end === span.end,
    );
    if (alreadyCovered) {
      continue;
    }
    const metadata = resolveReferenceMetadata({
      locator: span.locator,
      statement: input.statement,
      assessmentContext: input.assessmentContext,
      propositionById: input.propositionById,
      sourceFragments: input.sourceFragments,
      fragmentById: input.fragmentById,
      structuralContextLocator: input.source.structuralContextLocator,
      sourceRecordId: input.sourceRecordId,
    });
    const reference: InlineLegalReference = {
      ...metadata,
      sourceId: input.source.id,
      id: `${input.source.id}::${span.locator}::${span.start}`,
      label: span.label,
      start: span.start,
      end: span.end,
      summary: "",
    };
    reference.summary = buildReferenceSummary(reference);
    references.push(reference);
  }

  return references.sort((left, right) => {
    if (left.start !== right.start) {
      return left.start - right.start;
    }
    return right.end - right.end - (left.end - left.start);
  });
}

export function buildWorkbenchLegalTextSources(input: {
  statement: LawStatementRow;
  classifiedPropositions: Array<{
    proposition: { propositionId: string; propositionText: string; sourceExcerpt: string };
  }>;
  propositionById: Map<string, PropositionRow>;
  assessmentContext: AssessmentContextView[];
  compositionLawFragments: Array<{ sourceLocator: string; sourceExcerpt: string }>;
}): LegalTextSource[] {
  const sources: LegalTextSource[] = [
    {
      id: "statement",
      text: input.statement.statement_text ?? "",
    },
  ];

  for (const entry of input.classifiedPropositions) {
    const propositionRow = input.propositionById.get(entry.proposition.propositionId);
    const structuralContextLocator = propositionRow?.fragment_locator?.trim() || null;
    if (entry.proposition.propositionText.trim()) {
      sources.push({
        id: `proposition:${entry.proposition.propositionId}`,
        text: entry.proposition.propositionText,
        structuralContextLocator,
      });
    }
    if (
      entry.proposition.sourceExcerpt.trim() &&
      entry.proposition.sourceExcerpt !== EXPORT_FIELD_UNAVAILABLE
    ) {
      sources.push({
        id: `proposition:${entry.proposition.propositionId}:excerpt`,
        text: entry.proposition.sourceExcerpt,
        structuralContextLocator,
      });
    }
  }

  for (const context of input.assessmentContext) {
    const summaryParts = [
      context.locator,
      context.inheritedContextLabel ?? "",
      context.fragments[0]?.excerpt ?? "",
    ].filter(Boolean);
    if (summaryParts.length > 0) {
      sources.push({
        id: `context:${context.locator}`,
        text: summaryParts.join(" — "),
      });
    }
  }

  for (const fragment of input.compositionLawFragments) {
    if (
      fragment.sourceExcerpt.trim() &&
      fragment.sourceExcerpt !== EXPORT_FIELD_UNAVAILABLE &&
      isSafeSourceLocatorForInlineRef(fragment.sourceLocator)
    ) {
      sources.push({
        id: `source:${fragment.sourceLocator}`,
        text: fragment.sourceExcerpt,
        structuralContextLocator: fragment.sourceLocator,
      });
    }
  }

  return sources;
}

export function buildWorkbenchLegalReferences(input: {
  statement: LawStatementRow;
  assessmentContext: AssessmentContextView[];
  propositionById: Map<string, PropositionRow>;
  sourceFragments: SourceFragmentRow[];
  fragmentById: Map<string, SourceFragmentRow>;
  classifiedPropositions: Array<{
    proposition: { propositionId: string; propositionText: string; sourceExcerpt: string };
  }>;
  compositionLawFragments: Array<{ sourceLocator: string; sourceExcerpt: string }>;
}): WorkbenchLegalReferences {
  const sourceRecordId = primarySourceRecordIdForStatement(input.statement, input.propositionById);
  const knownLocators = collectKnownLocators(input.statement, input.assessmentContext);
  const sources = buildWorkbenchLegalTextSources(input);
  const referencesBySourceId = new Map<string, InlineLegalReference[]>();
  const partsBySourceId = new Map<string, StatementTextPart[]>();
  const allReferences: InlineLegalReference[] = [];

  for (const source of sources) {
    const references = buildLegalTextReferences({
      source,
      statement: input.statement,
      assessmentContext: input.assessmentContext,
      propositionById: input.propositionById,
      sourceFragments: input.sourceFragments,
      fragmentById: input.fragmentById,
      sourceRecordId,
      knownLocators,
    });
    referencesBySourceId.set(source.id, references);
    partsBySourceId.set(source.id, buildStatementTextParts(source.text, references));
    allReferences.push(...references);
  }

  return { referencesBySourceId, partsBySourceId, allReferences };
}

export function buildInlineLegalReferences(input: {
  statement: LawStatementRow;
  assessmentContext: AssessmentContextView[];
  propositionById: Map<string, PropositionRow>;
  sourceFragments?: SourceFragmentRow[];
  fragmentById?: Map<string, SourceFragmentRow>;
}): InlineLegalReference[] {
  const sourceFragments = input.sourceFragments ?? [];
  const fragmentById = input.fragmentById ?? new Map<string, SourceFragmentRow>();
  const sourceRecordId = primarySourceRecordIdForStatement(input.statement, input.propositionById);
  return buildLegalTextReferences({
    source: { id: "statement", text: input.statement.statement_text ?? "" },
    statement: input.statement,
    assessmentContext: input.assessmentContext,
    propositionById: input.propositionById,
    sourceFragments,
    fragmentById,
    sourceRecordId,
  });
}

export function buildStatementTextParts(
  statementText: string,
  references: InlineLegalReference[],
): StatementTextPart[] {
  const chosen: InlineLegalReference[] = [];
  for (const reference of [...references].sort((left, right) => {
    const leftLength = left.end - left.start;
    const rightLength = right.end - right.start;
    if (leftLength !== rightLength) {
      return rightLength - leftLength;
    }
    return left.start - right.start;
  })) {
    const overlaps = chosen.some(
      (existing) => reference.start < existing.end && reference.end > existing.start,
    );
    if (!overlaps) {
      chosen.push(reference);
    }
  }

  const ordered = chosen.sort((left, right) => left.start - right.start);
  const parts: StatementTextPart[] = [];
  let cursor = 0;
  ordered.forEach((reference, index) => {
    if (reference.start > cursor) {
      parts.push({
        kind: "text",
        text: statementText.slice(cursor, reference.start),
        key: `text-${cursor}`,
      });
    }
    parts.push({
      kind: "reference",
      referenceId: reference.id,
      text: statementText.slice(reference.start, reference.end),
      key: `ref-${reference.id}-${index}`,
    });
    cursor = reference.end;
  });
  if (cursor < statementText.length) {
    parts.push({
      kind: "text",
      text: statementText.slice(cursor),
      key: `text-${cursor}`,
    });
  }
  return parts;
}

export function referenceById(
  references: InlineLegalReference[],
): Map<string, InlineLegalReference> {
  return new Map(references.map((reference) => [reference.id, reference]));
}

export function statusLabelForReference(status: AssessmentContextStatus): string {
  return STATUS_LABEL[status];
}

export function materialRoleLabel(materialRole: string): string {
  return MATERIAL_ROLE_LABEL[materialRole] ?? materialRole.replaceAll("_", " ");
}

export const INLINE_REFERENCE_ACCENT_CLASS: Record<InlineReferenceAccent, string> = {
  resolved:
    "border-b-2 border-sky-600 text-sky-900 underline decoration-sky-600/70 underline-offset-2 dark:text-sky-100",
  resolved_container:
    "inline-flex items-center gap-0.5 rounded-full border border-sky-600/50 bg-sky-50 px-1.5 py-0.5 text-sky-900 dark:bg-sky-950/30 dark:text-sky-100",
  material:
    "rounded-full border border-emerald-600/50 bg-emerald-50 px-1.5 py-0.5 text-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-100",
  warning:
    "rounded-full border border-amber-600/50 bg-amber-50 px-1.5 py-0.5 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100",
};

export const INLINE_REFERENCE_PREVIEW_LIMIT = 3;

export const ACCENT_ARIA_LABEL: Record<InlineReferenceAccent, string> = {
  resolved: "Resolved exact legal reference",
  resolved_container: "Resolved container legal reference",
  material: "Material or relied-on legal reference",
  warning: "Unresolved or external legal reference",
};

export function referenceAriaLabel(reference: InlineLegalReference): string {
  return `${reference.label} · ${statusLabelForReference(reference.status)} · ${ACCENT_ARIA_LABEL[reference.accent]} · ${reference.propositionIds.length} linked propositions · Click to add to Authorities in play`;
}

export function hoverPreviewText(reference: InlineLegalReference): string {
  return `${reference.label}\n${statusLabelForReference(reference.status)}\n${reference.propositionIds.length} linked proposition${reference.propositionIds.length === 1 ? "" : "s"}\nClick to add to Authorities in play`;
}
