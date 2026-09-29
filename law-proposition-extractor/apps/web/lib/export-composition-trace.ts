import {
  assessCompositionTrace,
  buildCompositionTrace,
  type CompositionTraceFragment,
} from "@/lib/analyze-composition-traces";
import {
  classifyContextEntry,
  deriveIncorporationRecommendation,
  type ContextMaterialRole,
  type ContextEntryAssessment,
} from "@/lib/export-context-incorporation";
import {
  EXPORT_FIELD_UNAVAILABLE,
  type CompositionBuildContext,
  type SourceFragmentRow,
} from "@/lib/law-statements-composition";
import {
  buildStatementCompositionSegments,
  type StatementCompositionSegment,
} from "@/lib/statement-composition-highlight";
import type { LawStatementRow, PropositionRow, SourceRow } from "@/lib/law-statements-index";

export type ExportCompositionTraceRole =
  | "core_proposition"
  | "supporting_proposition"
  | "required_context"
  | "definition"
  | "exception"
  | "constraint"
  | "connector"
  | "unknown";

export type ExportSupportStatus =
  | "supported"
  | "partial"
  | "unresolved"
  | "inferred_unknown";

export type ExportIncorporationFlags = {
  included_in_text: boolean;
  external_context: boolean;
  should_inline: boolean;
  should_split: boolean;
  reviewer_required: boolean;
};

export type ExportCompositionTraceSpan = {
  order: number;
  text: string;
  start: number;
  end: number;
  role: ExportCompositionTraceRole;
  proposition_ids: string[];
  context_locators: string[];
  source_fragment_ids: string[];
  source_locators: string[];
  support_status: ExportSupportStatus;
  incorporation: ExportIncorporationFlags;
};

export type ContextMaterialRoleExport =
  | "confirms_statement"
  | "constrains_statement"
  | "exception_to_statement"
  | "defines_term"
  | "alters_effect"
  | "noise_or_unresolved";

export type ContextIncorporationEntry = {
  locator: string;
  kind: string;
  resolution_status: string;
  proposition_ids: string[];
  material_role: ContextMaterialRoleExport;
  incorporation: ExportIncorporationFlags;
};

export type EnrichedLawStatementRow = LawStatementRow & {
  composition_trace?: ExportCompositionTraceSpan[];
  context_incorporation?: ContextIncorporationEntry[];
};

const ROLE_MAP: Record<CompositionTraceFragment["role"], ExportCompositionTraceRole> = {
  core_proposition: "core_proposition",
  supporting_proposition: "supporting_proposition",
  required_context: "required_context",
  definition: "definition",
  exception: "exception",
  connector_inference: "connector",
  unknown: "unknown",
};

const MATERIAL_ROLE_EXPORT: Record<ContextMaterialRole, ContextMaterialRoleExport> = {
  confirm: "confirms_statement",
  constrain: "constrains_statement",
  exception: "exception_to_statement",
  definition: "defines_term",
  alter_effect: "alters_effect",
  noise: "noise_or_unresolved",
};

function mapSupportStatus(
  fragment: CompositionTraceFragment,
  segment: StatementCompositionSegment | undefined,
): ExportSupportStatus {
  if (fragment.role === "unknown" || segment?.unknown) {
    return "inferred_unknown";
  }
  if (fragment.support_status === "unresolved") {
    return "unresolved";
  }
  if (fragment.support_status === "partial" || fragment.support_status === "unsupported") {
    return "partial";
  }
  return "supported";
}

function sourceMetadataForPropositions(
  propositionIds: readonly string[],
  context: CompositionBuildContext,
): { fragmentIds: string[]; locators: string[] } {
  const fragmentIds = new Set<string>();
  const locators = new Set<string>();
  for (const propositionId of propositionIds) {
    const proposition = context.propositionById.get(propositionId);
    const fragmentId = String(proposition?.source_fragment_id ?? "").trim();
    if (fragmentId) {
      fragmentIds.add(fragmentId);
    }
    const locator = String(proposition?.fragment_locator ?? "").trim();
    if (locator) {
      locators.add(locator);
    }
  }
  return {
    fragmentIds: Array.from(fragmentIds),
    locators: Array.from(locators),
  };
}

function incorporationForContextEntry(
  entry: ContextEntryAssessment,
  recommendation: ReturnType<typeof deriveIncorporationRecommendation>,
): ExportIncorporationFlags {
  const included = entry.textInStatement || entry.textInCore;
  const externalContext =
    recommendation === "keep_external" ||
    entry.role === "confirm" ||
    entry.role === "noise";
  return {
    included_in_text: included,
    external_context: externalContext,
    should_inline: recommendation === "inline_selectively" && MATERIAL_ROLES.has(entry.role),
    should_split: recommendation === "emit_multiple",
    reviewer_required: recommendation === "defer_reviewer",
  };
}

const MATERIAL_ROLES = new Set<ContextMaterialRole>([
  "constrain",
  "exception",
  "definition",
  "alter_effect",
]);

function incorporationForSpan(input: {
  fragment: CompositionTraceFragment;
  segment: StatementCompositionSegment | undefined;
  contextEntries: ContextEntryAssessment[];
  recommendation: ReturnType<typeof deriveIncorporationRecommendation>;
  statementText: string;
}): ExportIncorporationFlags {
  const { fragment, segment, contextEntries, recommendation, statementText } = input;
  const relatedEntries = contextEntries.filter((entry) =>
    entry.propositionIds.some((id) => fragment.proposition_ids.includes(id)),
  );
  const relatedLocators = new Set(fragment.context_locators);
  const locatorEntries = contextEntries.filter((entry) => relatedLocators.has(entry.locator));
  const entries = relatedEntries.length > 0 ? relatedEntries : locatorEntries;

  const included =
    entries.some((entry) => entry.textInStatement || entry.textInCore) ||
    normalizeText(fragment.text) === normalizeText(statementText.slice(fragment.start, fragment.end));

  const materialEntries = entries.filter((entry) => MATERIAL_ROLES.has(entry.role));
  const unresolvedEntries = entries.filter(
    (entry) => entry.propositionIds.length === 0 && entry.resolutionStatus !== "external_reference",
  );

  const externalContext =
    entries.length > 0 &&
    (recommendation === "keep_external" ||
      entries.every((entry) => entry.role === "confirm" || entry.role === "noise"));

  const shouldInline =
    recommendation === "inline_selectively" &&
    materialEntries.length === 1 &&
    !included &&
    (fragment.role === "required_context" ||
      fragment.role === "definition" ||
      fragment.role === "exception" ||
      ROLE_MAP[fragment.role] === "constraint");

  const shouldSplit =
    recommendation === "emit_multiple" ||
    materialEntries.filter((entry) => entry.role === "alter_effect").length > 0 ||
    materialEntries.length >= 2;

  const reviewerRequired =
    recommendation === "defer_reviewer" ||
    unresolvedEntries.length > 0 ||
    entries.some((entry) => entry.resolutionStatus === "ambiguous");

  if (fragment.role === "unknown" || segment?.unknown) {
    return {
      included_in_text: false,
      external_context: false,
      should_inline: false,
      should_split: false,
      reviewer_required: reviewerRequired,
    };
  }

  return {
    included_in_text: included,
    external_context: externalContext,
    should_inline: shouldInline,
    should_split: shouldSplit,
    reviewer_required: reviewerRequired,
  };
}

function normalizeText(text: string): string {
  return text
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .trim();
}

function mapTraceRole(fragment: CompositionTraceFragment): ExportCompositionTraceRole {
  const mapped = ROLE_MAP[fragment.role] ?? "unknown";
  if (mapped === "required_context" && fragment.role !== "connector_inference") {
    return mapped;
  }
  if (fragment.role === "supporting_proposition") {
    return "supporting_proposition";
  }
  return mapped;
}

function refineRoleWithContext(
  role: ExportCompositionTraceRole,
  fragment: CompositionTraceFragment,
  contextEntries: ContextEntryAssessment[],
): ExportCompositionTraceRole {
  if (role === "required_context") {
    const related = contextEntries.filter((entry) =>
      entry.propositionIds.some((id) => fragment.proposition_ids.includes(id)),
    );
    if (related.some((entry) => entry.role === "constrain")) {
      return "constraint";
    }
  }
  return role;
}

export function buildContextIncorporationEntries(
  statement: LawStatementRow,
  context: CompositionBuildContext,
): ContextIncorporationEntry[] {
  const corePropId = String(statement.source_proposition_ids?.[0] ?? "").trim();
  const coreProp = context.propositionById.get(corePropId);
  const coreText = String(coreProp?.proposition_text ?? "").trim();
  const statementText = String(statement.statement_text ?? "").trim();

  const contextEntries: ContextEntryAssessment[] = (statement.required_context ?? []).map(
    (entry) =>
      classifyContextEntry({
        entry,
        contextProp: context.propositionById.get(String(entry.proposition_ids?.[0] ?? "").trim()),
        coreProp,
        statementText,
        coreText,
      }),
  );

  const recommendation = deriveIncorporationRecommendation({
    entries: contextEntries,
    incorporationGap: contextEntries.some(
      (entry) => MATERIAL_ROLES.has(entry.role) && !entry.textInStatement && !entry.textInCore,
    ),
    unresolvedContextCount: contextEntries.filter(
      (entry) => entry.propositionIds.length === 0 && entry.resolutionStatus !== "external_reference",
    ).length,
    resolvedMaterialCount: contextEntries.filter(
      (entry) => entry.propositionIds.length > 0 && MATERIAL_ROLES.has(entry.role),
    ).length,
  });

  return (statement.required_context ?? []).map((entry, index) => {
    const assessed = contextEntries[index]!;
    return {
      locator: String(entry.locator ?? "").trim(),
      kind: String(entry.kind ?? "").trim(),
      resolution_status: String(entry.resolution_status ?? "").trim(),
      proposition_ids: (entry.proposition_ids ?? []).map((id) => String(id).trim()).filter(Boolean),
      material_role: MATERIAL_ROLE_EXPORT[assessed.role],
      incorporation: incorporationForContextEntry(assessed, recommendation),
    };
  });
}

export function buildExportCompositionTrace(
  statement: LawStatementRow,
  context: CompositionBuildContext,
): ExportCompositionTraceSpan[] {
  const legacyTrace = buildCompositionTrace(statement, context);
  const segments = buildStatementCompositionSegments({ statement, context });
  const contextEntries = (statement.required_context ?? []).map((entry) =>
    classifyContextEntry({
      entry,
      contextProp: context.propositionById.get(String(entry.proposition_ids?.[0] ?? "").trim()),
      coreProp: context.propositionById.get(String(statement.source_proposition_ids?.[0] ?? "").trim()),
      statementText: statement.statement_text,
      coreText: String(
        context.propositionById.get(String(statement.source_proposition_ids?.[0] ?? "").trim())
          ?.proposition_text ?? "",
      ).trim(),
    }),
  );
  const recommendation = deriveIncorporationRecommendation({
    entries: contextEntries,
    incorporationGap: contextEntries.some(
      (entry) => MATERIAL_ROLES.has(entry.role) && !entry.textInStatement && !entry.textInCore,
    ),
    unresolvedContextCount: contextEntries.filter(
      (entry) => entry.propositionIds.length === 0 && entry.resolutionStatus !== "external_reference",
    ).length,
    resolvedMaterialCount: contextEntries.filter(
      (entry) => entry.propositionIds.length > 0 && MATERIAL_ROLES.has(entry.role),
    ).length,
  });

  return legacyTrace.map((fragment, index) => {
    const segment = segments[index];
    const sourceMeta = sourceMetadataForPropositions(fragment.proposition_ids, context);
    const role = refineRoleWithContext(mapTraceRole(fragment), fragment, contextEntries);
    const sourceLocator =
      fragment.source_locator !== EXPORT_FIELD_UNAVAILABLE ? fragment.source_locator : "";
    return {
      order: index,
      text: fragment.text,
      start: fragment.start,
      end: fragment.end,
      role,
      proposition_ids: fragment.proposition_ids,
      context_locators: fragment.context_locators,
      source_fragment_ids: sourceMeta.fragmentIds,
      source_locators: sourceLocator
        ? [sourceLocator, ...sourceMeta.locators.filter((loc) => loc !== sourceLocator)]
        : sourceMeta.locators,
      support_status: mapSupportStatus(fragment, segment),
      incorporation: incorporationForSpan({
        fragment,
        segment,
        contextEntries,
        recommendation,
        statementText: statement.statement_text,
      }),
    };
  });
}

export function enrichStatementWithCompositionTrace(
  statement: LawStatementRow,
  context: CompositionBuildContext,
): EnrichedLawStatementRow {
  const composition_trace = buildExportCompositionTrace(statement, context);
  const context_incorporation = buildContextIncorporationEntries(statement, context);
  return {
    ...statement,
    composition_trace,
    context_incorporation,
  };
}

export type CompositionTraceExportInput = {
  propositions: PropositionRow[];
  source_fragments: SourceFragmentRow[];
  source_records?: SourceRow[];
  effective_law_statements: { statements: LawStatementRow[] };
  proposition_completeness_assessments?: Array<{
    proposition_id?: string;
    status?: string;
  }>;
};

export function buildCompositionContext(
  input: CompositionTraceExportInput,
): CompositionBuildContext {
  const fragmentById = new Map(
    input.source_fragments
      .map((row) => [String(row.id ?? row.fragment_id ?? "").trim(), row] as const)
      .filter(([id]) => id),
  );
  const completenessById = new Map(
    (input.proposition_completeness_assessments ?? [])
      .map((row) => [String(row.proposition_id ?? ""), String(row.status ?? "")] as const)
      .filter(([id]) => id),
  );
  return {
    propositionById: new Map(input.propositions.map((row) => [row.id, row])),
    sourceById: new Map((input.source_records ?? []).map((row) => [row.id, row])),
    fragmentById,
    sourceCompletenessByPropositionId: completenessById,
  };
}

export function enrichEffectiveLawStatements(
  input: CompositionTraceExportInput,
): { statements: EnrichedLawStatementRow[] } & Record<string, unknown> {
  const context = buildCompositionContext(input);
  const statements = (input.effective_law_statements.statements ?? []).map((statement) =>
    enrichStatementWithCompositionTrace(statement, context),
  );
  return {
    ...input.effective_law_statements,
    statements,
  };
}

export type ExportCompositionTraceAnalysis = {
  exportDir: string;
  totalStatements: number;
  statementsWithCompositionTrace: number;
  opaqueStatementCount: number;
  traceReviewableBeforeExport: number;
  traceReviewableAfterExport: number;
  traceBlockedAfterExport: number;
  shouldInlineCount: number;
  shouldSplitCount: number;
  reviewerRequiredCount: number;
  externalContextCount: number;
  samples: Array<{
    statementId: string;
    statementText: string;
    traceReviewable: boolean;
    spanCount: number;
    incorporationSummary: string;
  }>;
};

export function analyzeExportCompositionTraceFromInput(
  exportDir: string,
  input: CompositionTraceExportInput,
): ExportCompositionTraceAnalysis {
  const context = buildCompositionContext(input);
  const statements = input.effective_law_statements.statements ?? [];
  let opaqueCount = 0;
  let reviewableBefore = 0;
  let reviewableAfter = 0;
  let shouldInline = 0;
  let shouldSplit = 0;
  let reviewerRequired = 0;
  let externalContext = 0;
  const samples: ExportCompositionTraceAnalysis["samples"] = [];

  for (const statement of statements) {
    const before = assessCompositionTrace(statement, context);
    const opaque = before.opacityTriggers.length > 0;
    if (!opaque) {
      continue;
    }
    opaqueCount += 1;
    if (before.traceReviewable) {
      reviewableBefore += 1;
    }

    const enriched = enrichStatementWithCompositionTrace(statement, context);
    const after = assessCompositionTrace(enriched, context);
    if (after.traceReviewable) {
      reviewableAfter += 1;
    }

    const incorporation = enriched.context_incorporation ?? [];
    const hasInline = incorporation.some((entry) => entry.incorporation.should_inline);
    const hasSplit =
      incorporation.some((entry) => entry.incorporation.should_split) ||
      (enriched.composition_trace ?? []).some((span) => span.incorporation.should_split);
    const hasReviewer = incorporation.some((entry) => entry.incorporation.reviewer_required);
    const hasExternal = incorporation.some((entry) => entry.incorporation.external_context);
    if (hasInline) {
      shouldInline += 1;
    }
    if (hasSplit) {
      shouldSplit += 1;
    }
    if (hasReviewer) {
      reviewerRequired += 1;
    }
    if (hasExternal) {
      externalContext += 1;
    }

    if (samples.length < 12) {
      samples.push({
        statementId: statement.id,
        statementText: statement.statement_text,
        traceReviewable: after.traceReviewable,
        spanCount: enriched.composition_trace?.length ?? 0,
        incorporationSummary: [
          hasInline ? "should_inline" : null,
          hasSplit ? "should_split" : null,
          hasReviewer ? "reviewer_required" : null,
        ]
          .filter(Boolean)
          .join(", ") || "none",
      });
    }
  }

  const enrichedStatements = statements.map((statement) =>
    enrichStatementWithCompositionTrace(statement, context),
  );

  return {
    exportDir,
    totalStatements: statements.length,
    statementsWithCompositionTrace: enrichedStatements.filter(
      (row) => (row.composition_trace?.length ?? 0) > 0,
    ).length,
    opaqueStatementCount: opaqueCount,
    traceReviewableBeforeExport: reviewableBefore,
    traceReviewableAfterExport: reviewableAfter,
    traceBlockedAfterExport: opaqueCount - reviewableAfter,
    shouldInlineCount: shouldInline,
    shouldSplitCount: shouldSplit,
    reviewerRequiredCount: reviewerRequired,
    externalContextCount: externalContext,
    samples,
  };
}

export function buildExportCompositionTraceReport(analysis: ExportCompositionTraceAnalysis): string {
  const lines: string[] = [];
  const opaque = analysis.opaqueStatementCount;
  const before = analysis.traceReviewableBeforeExport;
  const after = analysis.traceReviewableAfterExport;
  const blocked = analysis.traceBlockedAfterExport;
  const beforePct = opaque > 0 ? ((before / opaque) * 100).toFixed(1) : "0.0";
  const afterPct = opaque > 0 ? ((after / opaque) * 100).toFixed(1) : "0.0";

  lines.push("# Export composition trace report");
  lines.push("");
  lines.push(`**Date:** ${new Date().toISOString().slice(0, 10)}`);
  lines.push("**Corpus:** Slurry GB principal-5 (regenerated export)");
  lines.push(`**Export:** \`${analysis.exportDir}\``);
  lines.push("");
  lines.push("## Executive summary");
  lines.push("");
  lines.push(
    `- **${analysis.statementsWithCompositionTrace}** / ${analysis.totalStatements} statements carry export \`composition_trace\`.`,
  );
  lines.push(
    `- Among **${opaque}** composition-opaque statements: trace-reviewable **${before} → ${after}** (${beforePct}% → ${afterPct}%) after export trace packaging.`,
  );
  lines.push(`- **${blocked}** opaque statements remain trace-blocked.`);
  lines.push(`- **${analysis.shouldInlineCount}** statements flagged \`should_inline\`.`);
  lines.push(`- **${analysis.shouldSplitCount}** statements flagged \`should_split\`.`);
  lines.push(`- **${analysis.reviewerRequiredCount}** statements flagged \`reviewer_required\`.`);
  lines.push("");
  lines.push("## Population");
  lines.push("");
  lines.push("| Metric | Count |");
  lines.push("| --- | ---: |");
  lines.push(`| Statements with composition_trace | ${analysis.statementsWithCompositionTrace} |`);
  lines.push(`| Opaque statements | ${opaque} |`);
  lines.push(`| Trace-reviewable (derived, before export field) | ${before} |`);
  lines.push(`| Trace-reviewable (with export trace) | ${after} |`);
  lines.push(`| Trace-blocked | ${blocked} |`);
  lines.push(`| should_inline | ${analysis.shouldInlineCount} |`);
  lines.push(`| should_split | ${analysis.shouldSplitCount} |`);
  lines.push(`| reviewer_required | ${analysis.reviewerRequiredCount} |`);
  lines.push(`| external_context entries | ${analysis.externalContextCount} |`);
  lines.push("");
  lines.push("## Sample statements");
  lines.push("");
  for (const [index, sample] of analysis.samples.entries()) {
    lines.push(`### ${index + 1}. \`${sample.statementId}\``);
    lines.push("");
    lines.push(`- Trace-reviewable: ${sample.traceReviewable ? "yes" : "no"}`);
    lines.push(`- Spans: ${sample.spanCount}`);
    lines.push(`- Incorporation: ${sample.incorporationSummary}`);
    lines.push("");
    lines.push(`> ${sample.statementText.slice(0, 220).replace(/\s+/g, " ")}${sample.statementText.length > 220 ? "…" : ""}`);
    lines.push("");
  }
  lines.push("## Reproduction");
  lines.push("");
  lines.push("```bash");
  lines.push("uv run --package law-proposition-extractor-pipeline python scripts/generate_export_composition_trace_report.py");
  lines.push("```");
  lines.push("");
  return lines.join("\n");
}
