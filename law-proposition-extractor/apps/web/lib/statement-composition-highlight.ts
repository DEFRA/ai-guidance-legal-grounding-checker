import {
  EXPORT_FIELD_UNAVAILABLE,
  buildStatementFragments,
  buildStatementRecipe,
  recipeRowsForFragment,
  type CompositionBuildContext,
  type StatementRecipeRow,
} from "@/lib/law-statements-composition";
import {
  propositionRefsForStatement,
  type LawStatementPropRef,
  type LawStatementPropRole,
  type LawStatementRow,
} from "@/lib/law-statements-index";
import type { AssessmentContextView, LawFragmentView } from "@/lib/review-workbench-views";

export type CompositionFragmentOrigin =
  | "composition_source"
  | "assessment_context"
  | "inferred_unknown";

export type StatementCompositionSegment = {
  id: string;
  text: string;
  start: number;
  end: number;
  propositionIds: string[];
  contextLocators: string[];
  origin: CompositionFragmentOrigin;
  sourceLocator: string;
  propositionText: string;
  sourceExcerpt: string;
  recipeRowIds: string[];
  lawFragmentIds: string[];
  statementFragmentId: string | null;
  unknown: boolean;
};

const COMPOSITION_SOURCE_ROLES: ReadonlySet<LawStatementPropRole> = new Set([
  "source",
  "supporting",
  "connector",
  "via",
]);

const ASSESSMENT_CONTEXT_ROLES: ReadonlySet<LawStatementPropRole> = new Set([
  "required_context",
  "exception",
  "displaced_rule",
  "trigger",
]);

function normalizeForMatch(text: string): string {
  return text
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .trim();
}

function splitStatementIntoSentences(statementText: string): string[] {
  const trimmed = statementText.trim();
  if (!trimmed) {
    return [];
  }
  const parts = trimmed.split(/(?<=[.!?])\s+/).map((part) => part.trim()).filter(Boolean);
  return parts.length > 0 ? parts : [trimmed];
}

function findSpanInStatement(statementText: string, fragmentText: string, fromIndex = 0): {
  start: number;
  end: number;
  text: string;
} | null {
  const trimmed = fragmentText.trim();
  if (!trimmed) {
    return null;
  }

  const exact = statementText.indexOf(trimmed, fromIndex);
  if (exact >= 0) {
    return { start: exact, end: exact + trimmed.length, text: trimmed };
  }

  const normalizedStatement = normalizeForMatch(statementText);
  const normalizedFragment = normalizeForMatch(trimmed);
  if (normalizedFragment.length < 8) {
    return null;
  }
  const normalizedFrom = normalizeForMatch(statementText.slice(fromIndex));
  const relative = normalizedFrom.indexOf(normalizedFragment);
  if (relative < 0) {
    return null;
  }

  const prefixLength = normalizedFrom.slice(0, relative).length;
  let start = fromIndex;
  let consumed = 0;
  while (start < statementText.length && consumed < prefixLength) {
    if (/\s/.test(statementText[start]!)) {
      while (start < statementText.length && /\s/.test(statementText[start]!)) {
        start += 1;
      }
      consumed += 1;
      continue;
    }
    start += 1;
    consumed += 1;
  }

  let end = start;
  let matched = 0;
  while (end < statementText.length && matched < normalizedFragment.length) {
    if (/\s/.test(statementText[end]!)) {
      while (end < statementText.length && /\s/.test(statementText[end]!)) {
        end += 1;
      }
      matched += 1;
      continue;
    }
    end += 1;
    matched += 1;
  }

  return { start, end, text: statementText.slice(start, end) };
}

function originForRoles(roles: Iterable<LawStatementPropRole>): CompositionFragmentOrigin {
  const roleList = Array.from(roles);
  if (roleList.some((role) => COMPOSITION_SOURCE_ROLES.has(role))) {
    return "composition_source";
  }
  if (roleList.some((role) => ASSESSMENT_CONTEXT_ROLES.has(role))) {
    return "assessment_context";
  }
  return "inferred_unknown";
}

function refsByPropositionId(statement: LawStatementRow): Map<string, LawStatementPropRef[]> {
  const map = new Map<string, LawStatementPropRef[]>();
  for (const ref of propositionRefsForStatement(statement)) {
    const existing = map.get(ref.propositionId) ?? [];
    existing.push(ref);
    map.set(ref.propositionId, existing);
  }
  return map;
}

function summarizeRecipeRows(
  rows: StatementRecipeRow[],
  refsById: Map<string, LawStatementPropRef[]>,
): Pick<
  StatementCompositionSegment,
  | "propositionIds"
  | "contextLocators"
  | "origin"
  | "sourceLocator"
  | "propositionText"
  | "sourceExcerpt"
  | "recipeRowIds"
  | "unknown"
> {
  const propositionIds = Array.from(
    new Set(rows.flatMap((row) => row.supporting_proposition_ids)),
  );
  const contextLocators = Array.from(
    new Set(
      propositionIds.flatMap(
        (propositionId) =>
          refsById.get(propositionId)?.map((ref) => ref.contextLocator?.trim() ?? "") ?? [],
      ),
    ),
  ).filter(Boolean);

  const roles = propositionIds.flatMap((propositionId) =>
    (refsById.get(propositionId) ?? []).map((ref) => ref.role),
  );
  const origin = rows.length === 0 ? "inferred_unknown" : originForRoles(roles);

  const primaryRow = rows[0];
  return {
    propositionIds,
    contextLocators,
    origin,
    sourceLocator: primaryRow?.source_locator ?? EXPORT_FIELD_UNAVAILABLE,
    propositionText: primaryRow?.proposition_text ?? EXPORT_FIELD_UNAVAILABLE,
    sourceExcerpt: primaryRow?.source_excerpt ?? EXPORT_FIELD_UNAVAILABLE,
    recipeRowIds: rows.map((row) => row.rowId),
    unknown: rows.length === 0,
  };
}

function lawFragmentIdsForPropositions(
  propositionIds: readonly string[],
  lawFragments: readonly LawFragmentView[],
): string[] {
  const ids = new Set<string>();
  for (const fragment of lawFragments) {
    if (fragment.propositionIds.some((propositionId) => propositionIds.includes(propositionId))) {
      ids.add(fragment.id);
    }
  }
  return Array.from(ids);
}

type PositionedFragment = {
  statementFragmentId: string;
  text: string;
  start: number;
  end: number;
  recipeRows: StatementRecipeRow[];
};

function recipeRowsMatchingText(
  recipe: StatementRecipeRow[],
  text: string,
): StatementRecipeRow[] {
  const normalizedText = normalizeForMatch(text);
  if (!normalizedText) {
    return [];
  }
  const unavailable = normalizeForMatch(EXPORT_FIELD_UNAVAILABLE);

  const matchesCandidate = (candidate: string): boolean => {
    if (!candidate || candidate === unavailable) {
      return false;
    }
    if (normalizedText === candidate) {
      return true;
    }
    if (normalizedText.includes(candidate) && candidate.length >= 12) {
      return true;
    }
    if (candidate.includes(normalizedText) && normalizedText.length >= 12) {
      return candidate.length <= normalizedText.length * 1.35 + 12;
    }
    return false;
  };

  return recipe.filter((row) => {
    return (
      matchesCandidate(normalizeForMatch(row.statement_fragment)) ||
      matchesCandidate(normalizeForMatch(row.proposition_text))
    );
  });
}

function positionCandidateTexts(
  statementText: string,
  candidates: Array<{ id: string; text: string; recipeRows: StatementRecipeRow[] }>,
): PositionedFragment[] {
  const positioned: PositionedFragment[] = [];
  let searchFrom = 0;

  for (const candidate of candidates) {
    const span = findSpanInStatement(statementText, candidate.text, searchFrom);
    if (!span) {
      continue;
    }
    positioned.push({
      statementFragmentId: candidate.id,
      text: statementText.slice(span.start, span.end),
      start: span.start,
      end: span.end,
      recipeRows: candidate.recipeRows,
    });
    searchFrom = span.end;
  }

  return positioned.sort((left, right) => left.start - right.start);
}

function isMonolithicStatementCoverage(
  statementText: string,
  positioned: PositionedFragment[],
): boolean {
  return (
    positioned.length === 1 &&
    positioned[0]!.start === 0 &&
    positioned[0]!.end === statementText.length
  );
}

function buildPositionedFragments(
  statement: LawStatementRow,
  context: CompositionBuildContext,
  recipe: StatementRecipeRow[],
): PositionedFragment[] {
  const statementText = statement.statement_text;
  const fragments = buildStatementFragments(statement, context.propositionById);
  const sentences = splitStatementIntoSentences(statementText);
  const monolithicExport =
    fragments.length === 1 &&
    normalizeForMatch(fragments[0]!.text) === normalizeForMatch(statementText);

  if (monolithicExport && sentences.length > 1) {
    const sentencePositioned = positionCandidateTexts(
      statementText,
      sentences.map((text, index) => ({
        id: `sentence-${index}`,
        text,
        recipeRows: recipeRowsMatchingText(recipe, text),
      })),
    );
    if (sentencePositioned.length > 1) {
      return sentencePositioned;
    }
  }

  const fragmentCandidates = fragments.map((fragment) => ({
    id: fragment.id,
    text: fragment.text,
    recipeRows: recipeRowsForFragment(fragment, recipe),
  }));

  let positioned = positionCandidateTexts(statementText, fragmentCandidates);

  if (positioned.length === 0 || isMonolithicStatementCoverage(statementText, positioned)) {
    const seenRowIds = new Set<string>();
    const recipeCandidates = recipe
      .filter(
        (row) =>
          row.statement_fragment !== EXPORT_FIELD_UNAVAILABLE ||
          row.proposition_text !== EXPORT_FIELD_UNAVAILABLE,
      )
      .flatMap((row) => {
        if (seenRowIds.has(row.rowId)) {
          return [];
        }
        seenRowIds.add(row.rowId);
        const text =
          row.statement_fragment !== EXPORT_FIELD_UNAVAILABLE
            ? row.statement_fragment
            : row.proposition_text;
        return [{ id: `recipe-${row.rowId}`, text, recipeRows: [row] }];
      });

    const recipePositioned = positionCandidateTexts(statementText, recipeCandidates);
    if (recipePositioned.length > positioned.length) {
      positioned = recipePositioned;
    }
  }

  return positioned;
}

function appendUnknownGaps(
  statementText: string,
  positioned: PositionedFragment[],
): PositionedFragment[] {
  const filled: PositionedFragment[] = [];
  let cursor = 0;

  for (const [index, fragment] of positioned.entries()) {
    if (fragment.start > cursor) {
      const gapText = statementText.slice(cursor, fragment.start);
      if (gapText.trim().length > 0) {
        filled.push({
          statementFragmentId: `unknown-gap-${index}`,
          text: gapText,
          start: cursor,
          end: fragment.start,
          recipeRows: [],
        });
        cursor = fragment.start;
      } else if (filled.length > 0) {
        const previous = filled[filled.length - 1]!;
        filled[filled.length - 1] = {
          ...previous,
          end: fragment.start,
          text: statementText.slice(previous.start, fragment.start),
        };
        cursor = fragment.start;
      } else {
        cursor = fragment.start;
      }
    }
    filled.push(fragment);
    cursor = fragment.end;
  }

  if (cursor < statementText.length) {
    const tail = statementText.slice(cursor);
    if (tail.trim()) {
      filled.push({
        statementFragmentId: "unknown-tail",
        text: tail,
        start: cursor,
        end: statementText.length,
        recipeRows: [],
      });
    }
  }

  return filled;
}

export function buildStatementCompositionSegments(input: {
  statement: LawStatementRow;
  context: CompositionBuildContext;
  lawFragments?: readonly LawFragmentView[];
}): StatementCompositionSegment[] {
  const { statement, context } = input;
  const lawFragments = input.lawFragments ?? [];
  const recipe = buildStatementRecipe(statement, context);
  const refsById = refsByPropositionId(statement);
  const positioned = appendUnknownGaps(
    statement.statement_text,
    buildPositionedFragments(statement, context, recipe),
  );

  if (positioned.length === 0 && statement.statement_text.trim()) {
    const summary = summarizeRecipeRows(recipe, refsById);
    return [
      {
        id: "whole-statement",
        text: statement.statement_text,
        start: 0,
        end: statement.statement_text.length,
        ...summary,
        lawFragmentIds: lawFragmentIdsForPropositions(summary.propositionIds, lawFragments),
        statementFragmentId: "whole-statement",
        unknown: summary.unknown,
      },
    ];
  }

  return positioned.map((fragment, index) => {
    const summary = summarizeRecipeRows(fragment.recipeRows, refsById);
    return {
      id: `composition-segment-${index}`,
      text: fragment.text,
      start: fragment.start,
      end: fragment.end,
      ...summary,
      lawFragmentIds: lawFragmentIdsForPropositions(summary.propositionIds, lawFragments),
      statementFragmentId: fragment.statementFragmentId,
      unknown: summary.unknown || fragment.recipeRows.length === 0,
      origin: fragment.recipeRows.length === 0 ? "inferred_unknown" : summary.origin,
    };
  });
}

export function segmentHighlightsLawFragment(
  segment: StatementCompositionSegment | null | undefined,
  lawFragment: LawFragmentView,
): boolean {
  if (!segment) {
    return false;
  }
  if (segment.lawFragmentIds.includes(lawFragment.id)) {
    return true;
  }
  return lawFragment.propositionIds.some((propositionId) =>
    segment.propositionIds.includes(propositionId),
  );
}

export function segmentHighlightsProposition(
  segment: StatementCompositionSegment | null | undefined,
  propositionId: string,
): boolean {
  if (!segment) {
    return false;
  }
  return segment.propositionIds.includes(propositionId);
}

export function segmentHighlightsContext(
  segment: StatementCompositionSegment | null | undefined,
  context: AssessmentContextView,
): boolean {
  if (!segment) {
    return false;
  }
  if (segment.contextLocators.includes(context.locator)) {
    return true;
  }
  return context.children?.some((child) => segment.contextLocators.includes(child.locator)) ?? false;
}

export const COMPOSITION_ORIGIN_LABEL: Record<CompositionFragmentOrigin, string> = {
  composition_source: "Composition source",
  assessment_context: "Assessment context",
  inferred_unknown: "Inferred / unknown",
};

export const COMPOSITION_SEGMENT_SURFACE_CLASS: Record<CompositionFragmentOrigin, string> = {
  composition_source:
    "border-sky-500/40 bg-sky-500/15 text-foreground hover:bg-sky-500/25",
  assessment_context:
    "border-amber-500/40 bg-amber-500/15 text-foreground hover:bg-amber-500/25",
  inferred_unknown:
    "border-dashed border-zinc-500/50 bg-zinc-500/10 text-foreground hover:bg-zinc-500/20",
};

export const COMPOSITION_SEGMENT_SELECTED_CLASS =
  "ring-2 ring-priguidance-discovery/70 ring-offset-1 ring-offset-background";

export const SEGMENT_DETAIL_MAX_WIDTH_PX = 480;
export const SEGMENT_DETAIL_MAX_HEIGHT_PX = 360;
export const SEGMENT_DETAIL_TRUNCATE_LENGTH = 180;
export const NARROW_VIEWPORT_MEDIA_QUERY = "(max-width: 640px)";

export function computeSegmentPopoverPosition(input: {
  anchorRect: Pick<DOMRect, "top" | "bottom" | "left" | "right">;
  popoverSize: { width: number; height: number };
  viewport: { width: number; height: number };
  gap?: number;
  padding?: number;
}): { top: number; left: number } {
  const {
    anchorRect,
    popoverSize,
    viewport,
    gap = 8,
    padding = 8,
  } = input;
  const popoverWidth = Math.min(popoverSize.width, SEGMENT_DETAIL_MAX_WIDTH_PX);
  const popoverHeight = Math.min(popoverSize.height, SEGMENT_DETAIL_MAX_HEIGHT_PX);

  let left = anchorRect.right + gap;
  if (left + popoverWidth + padding > viewport.width) {
    left = anchorRect.left - gap - popoverWidth;
  }
  left = Math.max(padding, Math.min(left, viewport.width - popoverWidth - padding));

  let top = anchorRect.top;
  if (top + popoverHeight + padding > viewport.height) {
    top = viewport.height - popoverHeight - padding;
  }
  top = Math.max(padding, Math.min(top, viewport.height - popoverHeight - padding));

  return { top, left };
}
