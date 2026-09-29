import type {
  ExportCompositionTraceSpan,
  EnrichedLawStatementRow,
} from "@/lib/export-composition-trace";
import {
  COMPOSITION_SEGMENT_SURFACE_CLASS,
  type CompositionFragmentOrigin,
  type StatementCompositionSegment,
} from "@/lib/statement-composition-highlight";

const EXPORT_ROLE_ORIGIN: Record<
  ExportCompositionTraceSpan["role"],
  CompositionFragmentOrigin
> = {
  core_proposition: "composition_source",
  supporting_proposition: "composition_source",
  definition: "composition_source",
  exception: "composition_source",
  constraint: "assessment_context",
  required_context: "assessment_context",
  connector: "composition_source",
  unknown: "inferred_unknown",
};

export function statementHasExportCompositionTrace(
  statement: EnrichedLawStatementRow,
): boolean {
  return Array.isArray(statement.composition_trace) && statement.composition_trace.length > 0;
}

export function segmentsFromExportCompositionTrace(
  statement: EnrichedLawStatementRow,
): StatementCompositionSegment[] {
  const trace = statement.composition_trace ?? [];
  return trace.map((span, index) => ({
    id: `export-trace-${index}`,
    text: span.text,
    start: span.start,
    end: span.end,
    propositionIds: span.proposition_ids,
    contextLocators: span.context_locators,
    origin: EXPORT_ROLE_ORIGIN[span.role] ?? "inferred_unknown",
    sourceLocator: span.source_locators[0] ?? "not available from current export",
    propositionText: span.text,
    sourceExcerpt: span.text,
    recipeRowIds: [],
    lawFragmentIds: span.source_fragment_ids,
    statementFragmentId: `export-trace-${index}`,
    unknown: span.role === "unknown" || span.support_status === "inferred_unknown",
  }));
}

export function exportTraceSurfaceClass(span: ExportCompositionTraceSpan): string {
  const origin = EXPORT_ROLE_ORIGIN[span.role] ?? "inferred_unknown";
  return COMPOSITION_SEGMENT_SURFACE_CLASS[origin];
}

export const INCORPORATION_BADGE_LABEL = {
  should_inline: "Should inline",
  should_split: "Should split",
  reviewer_required: "Reviewer required",
  external_context: "External context",
} as const;
