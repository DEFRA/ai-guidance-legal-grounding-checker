import { assessCompositionTrace } from "@/lib/analyze-composition-traces";
import {
  buildCompositionContext,
  enrichStatementWithCompositionTrace,
  type CompositionTraceExportInput,
  type EnrichedLawStatementRow,
} from "@/lib/export-composition-trace";
import type { CompositionBuildContext } from "@/lib/law-statements-composition";
import {
  assessStatementQuality,
  propositionRefsForStatement,
  uniqueInstrumentKeysForStatement,
  type LawStatementRow,
  type StatementQualityAssessment,
} from "@/lib/law-statements-index";

function primaryInstrumentKey(
  statement: LawStatementRow,
  instrumentKeyByPropositionId: Map<string, string>,
): string {
  const keys = uniqueInstrumentKeysForStatement(statement, instrumentKeyByPropositionId);
  return keys[0] ?? "__unknown_instrument__";
}

export type IncorporationRecommendationCounts = {
  reviewer_required: number;
  should_split: number;
  should_inline: number;
  external_context: number;
};

export type TraceBlockedHardCaseProfile = {
  statementId: string;
  statementText: string;
  traceBlockReason: string;
  traceBlockReasons: string[];
  incorporationCounts: IncorporationRecommendationCounts;
  unresolvedLocatorCount: number;
  materialContextCount: number;
  propositionCount: number;
  sourceInstrument: string;
  contextDependent: boolean;
  apparentOverreach: boolean;
  missingPropositions: boolean;
  priorityScore: number;
};

export type TraceBlockedHardCaseAnalysis = {
  exportDir: string;
  totalStatements: number;
  hardCaseCount: number;
  traceBlockReasonCounts: Record<string, number>;
  incorporationRecommendationCounts: IncorporationRecommendationCounts;
  topSourceInstruments: Array<{ instrument: string; count: number }>;
  topRepeatedLocators: Array<{ locator: string; count: number }>;
  samples: TraceBlockedHardCaseProfile[];
  assessments: TraceBlockedHardCaseProfile[];
};

const MATERIAL_CONTEXT_ROLES = new Set([
  "constrains_statement",
  "exception_to_statement",
  "defines_term",
  "alters_effect",
]);

const TRACE_BLOCK_REASON_PRIORITY = [
  "monolithic_unknown",
  "monolithic_composition",
  "unsurfaced_context_dependence",
  "unsurfaced_required_context",
  "high_unknown_coverage",
  "missing_proposition_mapping",
  "incomplete_provenance",
  "empty_trace",
] as const;

const TRACE_BLOCK_REASON_LABEL: Record<string, string> = {
  monolithic_unknown: "Monolithic unknown",
  monolithic_composition: "Monolithic composition",
  unsurfaced_context_dependence: "Unsurfaced context dependence",
  unsurfaced_required_context: "Unsurfaced required context",
  high_unknown_coverage: "High unknown coverage",
  missing_proposition_mapping: "Missing proposition mapping",
  incomplete_provenance: "Incomplete provenance",
  empty_trace: "Empty trace",
};

export function ensureEnrichedStatement(
  statement: LawStatementRow,
  context: CompositionBuildContext,
): EnrichedLawStatementRow {
  if (Array.isArray(statement.composition_trace) && statement.composition_trace.length > 0) {
    return statement as EnrichedLawStatementRow;
  }
  return enrichStatementWithCompositionTrace(statement, context);
}

function countIncorporationFlags(
  statement: EnrichedLawStatementRow,
): IncorporationRecommendationCounts {
  const counts: IncorporationRecommendationCounts = {
    reviewer_required: 0,
    should_split: 0,
    should_inline: 0,
    external_context: 0,
  };
  const bump = (flags: {
    reviewer_required?: boolean;
    should_split?: boolean;
    should_inline?: boolean;
    external_context?: boolean;
  }): void => {
    if (flags.reviewer_required) {
      counts.reviewer_required += 1;
    }
    if (flags.should_split) {
      counts.should_split += 1;
    }
    if (flags.should_inline) {
      counts.should_inline += 1;
    }
    if (flags.external_context) {
      counts.external_context += 1;
    }
  };
  for (const span of statement.composition_trace ?? []) {
    bump(span.incorporation);
  }
  for (const entry of statement.context_incorporation ?? []) {
    bump(entry.incorporation);
  }
  return counts;
}

function unresolvedLocatorCount(statement: LawStatementRow): number {
  return (statement.required_context ?? []).filter((entry) => {
    const propositionIds = entry.proposition_ids ?? [];
    const resolutionStatus = String(entry.resolution_status ?? "").trim();
    return propositionIds.length === 0 && resolutionStatus !== "external_reference";
  }).length;
}

function materialContextCount(statement: EnrichedLawStatementRow): number {
  return (statement.context_incorporation ?? []).filter((entry) =>
    MATERIAL_CONTEXT_ROLES.has(entry.material_role),
  ).length;
}

export function hasApparentOverreach(
  statement: LawStatementRow,
  quality: StatementQualityAssessment,
): boolean {
  if (quality.flags.includes("high_composition")) {
    return true;
  }
  if ((statement.source_proposition_ids ?? []).length > 1) {
    return true;
  }
  for (const warning of statement.warnings ?? []) {
    const normalized = warning.toLowerCase();
    if (
      normalized.includes("overreach") ||
      normalized.includes("incorporat") ||
      normalized.includes("merged")
    ) {
      return true;
    }
  }
  return false;
}

export function hasMissingPropositions(
  statement: LawStatementRow,
  quality: StatementQualityAssessment,
  traceBlockReasons: string[],
): boolean {
  if (traceBlockReasons.includes("missing_proposition_mapping")) {
    return true;
  }
  const standalone = String(statement.standalone_status ?? "");
  if (
    standalone === "fragmentary" ||
    standalone === "relationship_only" ||
    quality.flags.includes("weak_source_completeness")
  ) {
    return true;
  }
  return false;
}

export function primaryTraceBlockReason(reasons: string[]): string {
  if (reasons.length === 0) {
    return "unknown";
  }
  for (const reason of TRACE_BLOCK_REASON_PRIORITY) {
    if (reasons.includes(reason)) {
      return reason;
    }
  }
  return reasons[0] ?? "unknown";
}

export function hardCasePriorityScore(profile: {
  incorporationCounts: IncorporationRecommendationCounts;
  contextDependent: boolean;
  apparentOverreach: boolean;
  missingPropositions: boolean;
  reviewScore?: number;
}): number {
  let score = 0;
  if (profile.incorporationCounts.reviewer_required > 0) {
    score += 1_000_000;
  }
  if (profile.incorporationCounts.should_split > 0) {
    score += 100_000;
  }
  if (profile.incorporationCounts.should_inline > 0) {
    score += 10_000;
  }
  if (profile.contextDependent) {
    score += 1_000;
  }
  if (profile.apparentOverreach) {
    score += 100;
  }
  if (profile.missingPropositions) {
    score += 10;
  }
  score += profile.reviewScore ?? 0;
  return score;
}

export function assessTraceBlockedHardCase(input: {
  statement: LawStatementRow;
  context: CompositionBuildContext;
  instrumentKeyByPropositionId: Map<string, string>;
  quality?: StatementQualityAssessment;
}): TraceBlockedHardCaseProfile | null {
  const enriched = ensureEnrichedStatement(input.statement, input.context);
  if (!Array.isArray(enriched.composition_trace) || enriched.composition_trace.length === 0) {
    return null;
  }

  const trace = assessCompositionTrace(enriched, input.context);
  if (trace.traceReviewable) {
    return null;
  }

  const quality = input.quality ?? assessStatementQuality(input.statement);
  const traceBlockReasons = trace.residualOpacityReasons;
  const incorporationCounts = countIncorporationFlags(enriched);
  const contextDependent = input.statement.standalone_status === "context_dependent";
  const apparentOverreach = hasApparentOverreach(input.statement, quality);
  const missingPropositions = hasMissingPropositions(
    input.statement,
    quality,
    traceBlockReasons,
  );
  const priorityScore = hardCasePriorityScore({
    incorporationCounts,
    contextDependent,
    apparentOverreach,
    missingPropositions,
    reviewScore: quality.reviewScore,
  });

  return {
    statementId: input.statement.id,
    statementText: input.statement.statement_text,
    traceBlockReason: primaryTraceBlockReason(traceBlockReasons),
    traceBlockReasons,
    incorporationCounts,
    unresolvedLocatorCount: unresolvedLocatorCount(input.statement),
    materialContextCount: materialContextCount(enriched),
    propositionCount: new Set(propositionRefsForStatement(input.statement).map((ref) => ref.propositionId))
      .size,
    sourceInstrument: primaryInstrumentKey(input.statement, input.instrumentKeyByPropositionId),
    contextDependent,
    apparentOverreach,
    missingPropositions,
    priorityScore,
  };
}

export function isTraceBlockedHardCase(profile: TraceBlockedHardCaseProfile | null | undefined): boolean {
  return profile != null;
}

function incrementCount(map: Record<string, number>, key: string): void {
  map[key] = (map[key] ?? 0) + 1;
}

function topCounts(
  counts: Map<string, number>,
  limit: number,
): Array<{ instrument: string; count: number }> {
  return Array.from(counts.entries())
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, limit)
    .map(([instrument, count]) => ({ instrument, count }));
}

function topLocatorCounts(
  counts: Map<string, number>,
  limit: number,
): Array<{ locator: string; count: number }> {
  return Array.from(counts.entries())
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, limit)
    .map(([locator, count]) => ({ locator, count }));
}

export function pickRepresentativeHardCaseSamples(
  assessments: TraceBlockedHardCaseProfile[],
  sampleSize = 20,
): TraceBlockedHardCaseProfile[] {
  const buckets = new Map<string, TraceBlockedHardCaseProfile[]>();
  for (const row of assessments) {
    const bucketKey = [
      row.traceBlockReason,
      row.incorporationCounts.reviewer_required > 0 ? "reviewer" : "",
      row.incorporationCounts.should_split > 0 ? "split" : "",
      row.incorporationCounts.should_inline > 0 ? "inline" : "",
      row.contextDependent ? "ctx" : "",
    ]
      .filter(Boolean)
      .join("|");
    const bucket = buckets.get(bucketKey) ?? [];
    bucket.push(row);
    buckets.set(bucketKey, bucket);
  }

  const sortedBuckets = Array.from(buckets.entries()).sort(
    (left, right) => right[1].length - left[1].length || left[0].localeCompare(right[0]),
  );

  const picked: TraceBlockedHardCaseProfile[] = [];
  const seen = new Set<string>();

  for (const [, rows] of sortedBuckets) {
    const sorted = [...rows].sort(
      (left, right) => right.priorityScore - left.priorityScore || left.statementId.localeCompare(right.statementId),
    );
    for (const row of sorted) {
      if (picked.length >= sampleSize) {
        break;
      }
      if (seen.has(row.statementId)) {
        continue;
      }
      seen.add(row.statementId);
      picked.push(row);
    }
    if (picked.length >= sampleSize) {
      break;
    }
  }

  if (picked.length < sampleSize) {
    const remainder = [...assessments]
      .sort(
        (left, right) =>
          right.priorityScore - left.priorityScore || left.statementId.localeCompare(right.statementId),
      )
      .filter((row) => !seen.has(row.statementId));
    for (const row of remainder) {
      if (picked.length >= sampleSize) {
        break;
      }
      picked.push(row);
    }
  }

  return picked.slice(0, sampleSize);
}

export function analyzeTraceBlockedHardCasesFromInput(
  exportDir: string,
  input: CompositionTraceExportInput,
  instrumentKeyByPropositionId: Map<string, string>,
): TraceBlockedHardCaseAnalysis {
  const context = buildCompositionContext(input);
  const statements = input.effective_law_statements.statements ?? [];

  const assessments: TraceBlockedHardCaseProfile[] = [];
  const traceBlockReasonCounts: Record<string, number> = {};
  const incorporationRecommendationCounts: IncorporationRecommendationCounts = {
    reviewer_required: 0,
    should_split: 0,
    should_inline: 0,
    external_context: 0,
  };
  const instrumentCounts = new Map<string, number>();
  const locatorCounts = new Map<string, number>();

  for (const statement of statements) {
    const profile = assessTraceBlockedHardCase({
      statement,
      context,
      instrumentKeyByPropositionId,
    });
    if (!profile) {
      continue;
    }

    assessments.push(profile);
    incrementCount(traceBlockReasonCounts, profile.traceBlockReason);
    if (profile.incorporationCounts.reviewer_required > 0) {
      incorporationRecommendationCounts.reviewer_required += 1;
    }
    if (profile.incorporationCounts.should_split > 0) {
      incorporationRecommendationCounts.should_split += 1;
    }
    if (profile.incorporationCounts.should_inline > 0) {
      incorporationRecommendationCounts.should_inline += 1;
    }
    if (profile.incorporationCounts.external_context > 0) {
      incorporationRecommendationCounts.external_context += 1;
    }
    instrumentCounts.set(
      profile.sourceInstrument,
      (instrumentCounts.get(profile.sourceInstrument) ?? 0) + 1,
    );

    const enriched = ensureEnrichedStatement(statement, context);
    for (const entry of enriched.required_context ?? []) {
      const locator = String(entry.locator ?? "").trim();
      const propositionIds = entry.proposition_ids ?? [];
      const resolutionStatus = String(entry.resolution_status ?? "").trim();
      if (locator && propositionIds.length === 0 && resolutionStatus !== "external_reference") {
        locatorCounts.set(locator, (locatorCounts.get(locator) ?? 0) + 1);
      }
    }
  }

  assessments.sort(
    (left, right) =>
      right.priorityScore - left.priorityScore || left.statementId.localeCompare(right.statementId),
  );

  return {
    exportDir,
    totalStatements: statements.length,
    hardCaseCount: assessments.length,
    traceBlockReasonCounts,
    incorporationRecommendationCounts,
    topSourceInstruments: topCounts(instrumentCounts, 15),
    topRepeatedLocators: topLocatorCounts(locatorCounts, 15),
    samples: pickRepresentativeHardCaseSamples(assessments, 20),
    assessments,
  };
}

function formatReasonLabel(reason: string): string {
  return TRACE_BLOCK_REASON_LABEL[reason] ?? reason.replaceAll("_", " ");
}

export function buildTraceBlockedHardCasesReport(analysis: TraceBlockedHardCaseAnalysis): string {
  const lines: string[] = [];
  lines.push("# Trace-blocked hard cases report");
  lines.push("");
  lines.push(`**Date:** ${new Date().toISOString().slice(0, 10)}`);
  lines.push(`**Export:** \`${analysis.exportDir}\``);
  lines.push("");
  lines.push("## Executive summary");
  lines.push("");
  lines.push(
    `- **${analysis.hardCaseCount}** / ${analysis.totalStatements} statements have export \`composition_trace\` but remain trace-blocked by \`assessCompositionTrace\`.`,
  );
  lines.push(
    "- Review Workbench queue preset: **Trace-blocked hard cases** — prioritises reviewer_required → should_split → should_inline → context_dependent → apparent overreach → missing propositions.",
  );
  lines.push("");
  lines.push("## Count by trace_block_reason");
  lines.push("");
  lines.push("| Reason | Count |");
  lines.push("| --- | ---: |");
  for (const [reason, count] of Object.entries(analysis.traceBlockReasonCounts).sort(
    (left, right) => right[1] - left[1] || left[0].localeCompare(right[0]),
  )) {
    lines.push(`| ${formatReasonLabel(reason)} | ${count} |`);
  }
  lines.push("");
  lines.push("## Count by incorporation recommendation");
  lines.push("");
  lines.push("| Flag (statement has ≥1) | Count |");
  lines.push("| --- | ---: |");
  lines.push(
    `| reviewer_required | ${analysis.incorporationRecommendationCounts.reviewer_required} |`,
  );
  lines.push(`| should_split | ${analysis.incorporationRecommendationCounts.should_split} |`);
  lines.push(`| should_inline | ${analysis.incorporationRecommendationCounts.should_inline} |`);
  lines.push(
    `| external_context | ${analysis.incorporationRecommendationCounts.external_context} |`,
  );
  lines.push("");
  lines.push("## Top source instruments");
  lines.push("");
  lines.push("| Instrument | Hard cases |");
  lines.push("| --- | ---: |");
  for (const row of analysis.topSourceInstruments) {
    lines.push(`| ${row.instrument} | ${row.count} |`);
  }
  lines.push("");
  lines.push("## Top repeated unresolved locators");
  lines.push("");
  lines.push("| Locator | Statements |");
  lines.push("| --- | ---: |");
  for (const row of analysis.topRepeatedLocators) {
    lines.push(`| ${row.locator} | ${row.count} |`);
  }
  lines.push("");
  lines.push("## Sample hard cases (20 representative)");
  lines.push("");
  for (const [index, sample] of analysis.samples.entries()) {
    lines.push(`### ${index + 1}. \`${sample.statementId}\``);
    lines.push("");
    lines.push(`- trace_block_reason: ${formatReasonLabel(sample.traceBlockReason)}`);
    lines.push(
      `- incorporation: reviewer=${sample.incorporationCounts.reviewer_required}, split=${sample.incorporationCounts.should_split}, inline=${sample.incorporationCounts.should_inline}, external=${sample.incorporationCounts.external_context}`,
    );
    lines.push(`- unresolved locators: ${sample.unresolvedLocatorCount}`);
    lines.push(`- material context entries: ${sample.materialContextCount}`);
    lines.push(`- proposition count: ${sample.propositionCount}`);
    lines.push(`- source instrument: ${sample.sourceInstrument}`);
    lines.push(`- priority score: ${sample.priorityScore}`);
    lines.push("");
    lines.push(
      `> ${sample.statementText.slice(0, 220).replace(/\s+/g, " ")}${sample.statementText.length > 220 ? "…" : ""}`,
    );
    lines.push("");
  }
  lines.push("## Reproduction");
  lines.push("");
  lines.push("```bash");
  lines.push("uv run --package law-proposition-extractor-pipeline python scripts/generate_trace_blocked_hard_cases_report.py");
  lines.push("```");
  lines.push("");
  return lines.join("\n");
}
