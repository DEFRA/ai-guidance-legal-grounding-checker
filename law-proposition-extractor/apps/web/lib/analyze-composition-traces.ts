import {
  EXPORT_FIELD_UNAVAILABLE,
  buildStatementRecipe,
  type CompositionBuildContext,
  type SourceFragmentRow,
  type StatementRecipeRow,
} from "@/lib/law-statements-composition";
import {
  assessStatementQuality,
  propositionRefsForStatement,
  type LawStatementPropRef,
  type LawStatementRow,
  type PropositionRow,
  type SourceRow,
} from "@/lib/law-statements-index";
import { buildStatementCompositionSegments } from "@/lib/statement-composition-highlight";

export type ExportBundle = {
  propositions: PropositionRow[];
  source_fragments: SourceFragmentRow[];
  source_records: SourceRow[];
  effective_law_statements: { statements: LawStatementRow[] };
  proposition_completeness_assessments?: Array<{
    proposition_id?: string;
    status?: string;
  }>;
};

export type CompositionTraceRole =
  | "core_proposition"
  | "supporting_proposition"
  | "definition"
  | "exception"
  | "required_context"
  | "connector_inference"
  | "unknown";

export type CompositionTraceFragment = {
  order: number;
  text: string;
  start: number;
  end: number;
  role: CompositionTraceRole;
  proposition_ids: string[];
  context_locators: string[];
  source_locator: string;
  source_excerpt: string;
  support_status: string;
};

export type OpacityTrigger =
  | "high_composition"
  | "context_dependent"
  | "partially_resolved"
  | "many_required_context"
  | "connector_context";

export type CompositionTraceAssessment = {
  statementId: string;
  statementText: string;
  standaloneStatus: string;
  opacityTriggers: OpacityTrigger[];
  trace: CompositionTraceFragment[];
  fragmentCount: number;
  unknownCoverageRatio: number;
  propositionCoverageRatio: number;
  requiredContextSurfaced: boolean;
  provenanceComplete: boolean;
  traceReviewable: boolean;
  opacityResolvable: boolean;
  residualOpacityReasons: string[];
};

export type TriggerResolutionStats = {
  total: number;
  traceReviewable: number;
};

export type CompositionTraceAnalysis = {
  exportDir: string;
  totalStatements: number;
  opaqueStatementCount: number;
  traceReviewableCount: number;
  opacityResolvableCount: number;
  opacityResolvableExclusiveCount: number;
  triggerCounts: Record<OpacityTrigger, number>;
  triggerResolution: Record<OpacityTrigger, TriggerResolutionStats>;
  roleCounts: Record<CompositionTraceRole, number>;
  residualReasonCounts: Record<string, number>;
  samples: CompositionTraceAssessment[];
  assessments: CompositionTraceAssessment[];
};

const ROLE_LABEL: Record<CompositionTraceRole, string> = {
  core_proposition: "Core proposition",
  supporting_proposition: "Supporting proposition",
  definition: "Definition",
  exception: "Exception",
  required_context: "Required context",
  connector_inference: "Connector / inference",
  unknown: "Unknown",
};

const TRACE_ROLE_PRIORITY: Record<CompositionTraceRole, number> = {
  unknown: 0,
  connector_inference: 1,
  required_context: 2,
  exception: 3,
  definition: 4,
  supporting_proposition: 5,
  core_proposition: 6,
};

const UNKNOWN_COVERAGE_THRESHOLD = 0.15;
const PROPOSITION_COVERAGE_THRESHOLD = 0.9;

function fragmentRowId(fragment: SourceFragmentRow): string {
  return String(fragment.id ?? fragment.fragment_id ?? "").trim();
}

function detectOpacityTriggers(statement: LawStatementRow): OpacityTrigger[] {
  const triggers: OpacityTrigger[] = [];
  const quality = assessStatementQuality(statement);
  if (quality.flags.includes("high_composition")) {
    triggers.push("high_composition");
  }
  if (statement.standalone_status === "context_dependent") {
    triggers.push("context_dependent");
  }
  if (statement.standalone_status === "partially_resolved") {
    triggers.push("partially_resolved");
  }
  if ((statement.required_context ?? []).length >= 3) {
    triggers.push("many_required_context");
  }
  if ((statement.connector_context ?? []).length > 0) {
    triggers.push("connector_context");
  }
  return triggers;
}

function isOpaqueStatement(statement: LawStatementRow): boolean {
  return detectOpacityTriggers(statement).length > 0;
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

function roleForProposition(input: {
  statement: LawStatementRow;
  propositionId: string;
  refs: LawStatementPropRef[];
  proposition?: PropositionRow;
  segmentUnknown: boolean;
}): CompositionTraceRole {
  if (input.segmentUnknown) {
    return "unknown";
  }

  const { statement, propositionId, refs, proposition } = input;
  const roles = new Set<CompositionTraceRole>();

  for (const ref of refs) {
    if (
      ref.role === "required_context" ||
      ref.role === "exception" ||
      ref.role === "displaced_rule" ||
      ref.role === "trigger"
    ) {
      roles.add("required_context");
    } else if (ref.role === "connector" || ref.role === "via") {
      roles.add("connector_inference");
    } else if (ref.role === "supporting") {
      roles.add("supporting_proposition");
    } else {
      roles.add("core_proposition");
    }
  }

  const effectType = String(proposition?.legal_effect_type ?? "").trim();
  const tier = String(proposition?.proposition_tier ?? "").trim();
  if (
    effectType === "definition" ||
    tier === "definitional_rule" ||
    statement.presentation_role === "supporting_definition"
  ) {
    roles.add("definition");
  }
  if (effectType === "derogation") {
    roles.add("exception");
  }

  const warningText = (statement.warnings ?? []).join(" ").toLowerCase();
  if (warningText.includes("exception") && refs.some((ref) => ref.propositionId === propositionId)) {
    roles.add("exception");
  }

  if (roles.size === 0) {
    return "unknown";
  }

  return Array.from(roles).sort(
    (left, right) => TRACE_ROLE_PRIORITY[left] - TRACE_ROLE_PRIORITY[right],
  )[0]!;
}

function supportStatusForFragment(recipeRows: StatementRecipeRow[]): string {
  if (recipeRows.length === 0) {
    return "unsupported";
  }
  if (recipeRows.some((row) => row.support_status === "unresolved")) {
    return "unresolved";
  }
  if (recipeRows.some((row) => row.support_status === "unsupported")) {
    return "unsupported";
  }
  if (recipeRows.some((row) => row.support_status === "partial")) {
    return "partial";
  }
  return "supported";
}

export function buildCompositionTrace(
  statement: LawStatementRow,
  context: CompositionBuildContext,
): CompositionTraceFragment[] {
  const recipe = buildStatementRecipe(statement, context);
  const recipeByRowId = new Map(recipe.map((row) => [row.rowId, row]));
  const refsById = refsByPropositionId(statement);
  const segments = buildStatementCompositionSegments({ statement, context });

  return segments.map((segment, index) => {
    const recipeRows = segment.recipeRowIds
      .map((rowId) => recipeByRowId.get(rowId))
      .filter((row): row is StatementRecipeRow => Boolean(row));
    const segmentUnknown = segment.unknown || segment.propositionIds.length === 0;

    const roles = segment.propositionIds.map((propositionId) =>
      roleForProposition({
        statement,
        propositionId,
        refs: refsById.get(propositionId) ?? [],
        proposition: context.propositionById.get(propositionId),
        segmentUnknown,
      }),
    );
    const role =
      segmentUnknown && roles.length === 0
        ? "unknown"
        : roles.sort((left, right) => TRACE_ROLE_PRIORITY[left] - TRACE_ROLE_PRIORITY[right])[0] ??
          "unknown";

    return {
      order: index,
      text: segment.text,
      start: segment.start,
      end: segment.end,
      role,
      proposition_ids: segment.propositionIds,
      context_locators: segment.contextLocators,
      source_locator: segment.sourceLocator,
      source_excerpt: segment.sourceExcerpt,
      support_status: supportStatusForFragment(recipeRows),
    };
  });
}

function requiredContextPropositionIds(statement: LawStatementRow): string[] {
  const ids = new Set<string>();
  for (const ctx of statement.required_context ?? []) {
    for (const propositionId of ctx.proposition_ids ?? []) {
      if (propositionId.trim()) {
        ids.add(propositionId);
      }
    }
  }
  return Array.from(ids);
}

export function assessCompositionTrace(
  statement: LawStatementRow,
  context: CompositionBuildContext,
): CompositionTraceAssessment {
  const trace = buildCompositionTrace(statement, context);
  const opacityTriggers = detectOpacityTriggers(statement);
  const statementLength = Math.max(statement.statement_text.length, 1);

  const unknownChars = trace
    .filter((fragment) => fragment.role === "unknown")
    .reduce((sum, fragment) => sum + Math.max(0, fragment.end - fragment.start), 0);
  const unknownCoverageRatio = unknownChars / statementLength;

  const linkedPropositionIds = new Set(uniquePropositionIdsForTrace(statement));
  const tracedPropositionIds = new Set(trace.flatMap((fragment) => fragment.proposition_ids));
  const propositionCoverageRatio =
    linkedPropositionIds.size === 0
      ? 1
      : Array.from(linkedPropositionIds).filter((id) => tracedPropositionIds.has(id)).length /
        linkedPropositionIds.size;

  const requiredIds = requiredContextPropositionIds(statement);
  const requiredContextSurfaced =
    requiredIds.length === 0 ||
    requiredIds.every((propositionId) =>
      trace.some(
        (fragment) =>
          fragment.proposition_ids.includes(propositionId) &&
          fragment.role === "required_context",
      ),
    );

  const nonUnknownFragments = trace.filter((fragment) => fragment.role !== "unknown");
  const provenanceComplete =
    nonUnknownFragments.length === 0
      ? false
      : nonUnknownFragments.every(
          (fragment) =>
            fragment.proposition_ids.length > 0 &&
            fragment.source_excerpt !== EXPORT_FIELD_UNAVAILABLE,
        );

  const linkedPropCount = linkedPropositionIds.size;
  const needsStructuralDecomposition =
    opacityTriggers.includes("context_dependent") ||
    opacityTriggers.includes("partially_resolved") ||
    opacityTriggers.includes("high_composition") ||
    opacityTriggers.includes("many_required_context") ||
    linkedPropCount >= 2;

  const distinctNonUnknownFragments = nonUnknownFragments.length;
  const maxPropositionsPerFragment = Math.max(
    0,
    ...nonUnknownFragments.map((fragment) => fragment.proposition_ids.length),
  );
  const hasRequiredContextFragment = trace.some(
    (fragment) => fragment.role === "required_context",
  );
  const structurallyDecomposed =
    !needsStructuralDecomposition ||
    distinctNonUnknownFragments >= 2 ||
    (distinctNonUnknownFragments === 1 &&
      maxPropositionsPerFragment >= 2 &&
      hasRequiredContextFragment);

  const contextStandalone =
    statement.standalone_status === "context_dependent" ||
    statement.standalone_status === "partially_resolved";
  const needsContextSurfacing = contextStandalone && requiredIds.length > 0;
  const contextSurfacedInTrace =
    !needsContextSurfacing || hasRequiredContextFragment;

  const residualOpacityReasons: string[] = [];

  if (trace.length === 0 || (trace.length === 1 && trace[0]!.role === "unknown")) {
    residualOpacityReasons.push("monolithic_unknown");
  }
  if (!structurallyDecomposed) {
    residualOpacityReasons.push("monolithic_composition");
  }
  if (!contextSurfacedInTrace) {
    residualOpacityReasons.push("unsurfaced_context_dependence");
  }
  if (unknownCoverageRatio > UNKNOWN_COVERAGE_THRESHOLD) {
    residualOpacityReasons.push("high_unknown_coverage");
  }
  if (propositionCoverageRatio < PROPOSITION_COVERAGE_THRESHOLD) {
    residualOpacityReasons.push("missing_proposition_mapping");
  }
  if (!requiredContextSurfaced) {
    residualOpacityReasons.push("unsurfaced_required_context");
  }
  if (!provenanceComplete) {
    residualOpacityReasons.push("incomplete_provenance");
  }
  if (trace.length === 0) {
    residualOpacityReasons.push("empty_trace");
  }

  const traceReviewable = residualOpacityReasons.length === 0;
  const opacityResolvable = traceReviewable;

  return {
    statementId: statement.id,
    statementText: statement.statement_text,
    standaloneStatus: statement.standalone_status,
    opacityTriggers,
    trace,
    fragmentCount: trace.length,
    unknownCoverageRatio,
    propositionCoverageRatio,
    requiredContextSurfaced,
    provenanceComplete,
    traceReviewable,
    opacityResolvable,
    residualOpacityReasons,
  };
}

function uniquePropositionIdsForTrace(statement: LawStatementRow): string[] {
  const ids = new Set<string>();
  for (const ref of propositionRefsForStatement(statement)) {
    ids.add(ref.propositionId);
  }
  return Array.from(ids);
}

function pickSamples(assessments: CompositionTraceAssessment[]): CompositionTraceAssessment[] {
  const opaque = assessments.filter((row) => row.opacityTriggers.length > 0);
  const buckets: Record<string, CompositionTraceAssessment[]> = {
    context_dependent_reviewable: [],
    context_dependent_blocked: [],
    partially_resolved_reviewable: [],
    partially_resolved_blocked: [],
    high_composition_reviewable: [],
    high_composition_blocked: [],
    many_required_context: [],
    connector_context: [],
  };

  for (const row of opaque) {
    const keyBase = row.opacityTriggers[0] ?? "high_composition";
    const suffix = row.traceReviewable ? "reviewable" : "blocked";
    const bucketKey = `${keyBase}_${suffix}`;
    if (buckets[bucketKey]) {
      buckets[bucketKey].push(row);
    } else if (row.opacityTriggers.includes("many_required_context")) {
      buckets.many_required_context.push(row);
    } else if (row.opacityTriggers.includes("connector_context")) {
      buckets.connector_context.push(row);
    }
  }

  const picked: CompositionTraceAssessment[] = [];
  const take = (key: keyof typeof buckets, count: number): void => {
    for (const row of buckets[key].slice(0, count)) {
      if (!picked.some((existing) => existing.statementId === row.statementId)) {
        picked.push(row);
      }
    }
  };

  take("context_dependent_reviewable", 2);
  take("context_dependent_blocked", 2);
  take("partially_resolved_reviewable", 2);
  take("partially_resolved_blocked", 2);
  take("high_composition_reviewable", 2);
  take("high_composition_blocked", 2);
  take("many_required_context", 2);
  take("connector_context", 2);

  if (picked.length < 12) {
    for (const row of opaque) {
      if (picked.length >= 15) {
        break;
      }
      if (!picked.some((existing) => existing.statementId === row.statementId)) {
        picked.push(row);
      }
    }
  }

  return picked.slice(0, 15);
}

export function analyzeCompositionTracesFromBundle(
  exportDir: string,
  bundle: ExportBundle,
): CompositionTraceAnalysis {
  const propositionById = new Map(bundle.propositions.map((row) => [row.id, row]));
  const fragmentById = new Map(
    bundle.source_fragments.map((row) => [fragmentRowId(row), row]).filter(([id]) => id),
  );
  const completenessById = new Map(
    (bundle.proposition_completeness_assessments ?? [])
      .map((row) => [String(row.proposition_id ?? ""), String(row.status ?? "")])
      .filter(([id]) => id),
  );
  const context: CompositionBuildContext = {
    propositionById,
    sourceById: new Map(bundle.source_records.map((row) => [row.id, row])),
    fragmentById,
    sourceCompletenessByPropositionId: completenessById,
  };

  const assessments: CompositionTraceAssessment[] = [];
  const triggerCounts: Record<OpacityTrigger, number> = {
    high_composition: 0,
    context_dependent: 0,
    partially_resolved: 0,
    many_required_context: 0,
    connector_context: 0,
  };
  const roleCounts: Record<CompositionTraceRole, number> = {
    core_proposition: 0,
    supporting_proposition: 0,
    definition: 0,
    exception: 0,
    required_context: 0,
    connector_inference: 0,
    unknown: 0,
  };
  const residualReasonCounts = new Map<string, number>();

  for (const statement of bundle.effective_law_statements.statements ?? []) {
    if (!isOpaqueStatement(statement)) {
      continue;
    }
    const assessment = assessCompositionTrace(statement, context);
    assessments.push(assessment);
    for (const trigger of assessment.opacityTriggers) {
      triggerCounts[trigger] += 1;
    }
    for (const fragment of assessment.trace) {
      roleCounts[fragment.role] += 1;
    }
    for (const reason of assessment.residualOpacityReasons) {
      residualReasonCounts.set(reason, (residualReasonCounts.get(reason) ?? 0) + 1);
    }
  }

  const traceReviewableCount = assessments.filter((row) => row.traceReviewable).length;
  const opacityResolvableCount = assessments.filter((row) => row.opacityResolvable).length;

  const triggerResolution: Record<OpacityTrigger, TriggerResolutionStats> = {
    high_composition: { total: 0, traceReviewable: 0 },
    context_dependent: { total: 0, traceReviewable: 0 },
    partially_resolved: { total: 0, traceReviewable: 0 },
    many_required_context: { total: 0, traceReviewable: 0 },
    connector_context: { total: 0, traceReviewable: 0 },
  };
  for (const row of assessments) {
    for (const trigger of row.opacityTriggers) {
      triggerResolution[trigger].total += 1;
      if (row.traceReviewable) {
        triggerResolution[trigger].traceReviewable += 1;
      }
    }
  }

  return {
    exportDir,
    totalStatements: bundle.effective_law_statements.statements?.length ?? 0,
    opaqueStatementCount: assessments.length,
    traceReviewableCount,
    opacityResolvableCount,
    opacityResolvableExclusiveCount: traceReviewableCount,
    triggerCounts,
    triggerResolution,
    roleCounts,
    residualReasonCounts: Object.fromEntries(
      Array.from(residualReasonCounts.entries()).sort((left, right) => right[1] - left[1]),
    ),
    samples: pickSamples(assessments),
    assessments,
  };
}

function truncate(text: string, max = 180): string {
  const trimmed = text.replace(/\s+/g, " ").trim();
  if (trimmed.length <= max) {
    return trimmed;
  }
  return `${trimmed.slice(0, max - 1)}…`;
}

function escapeCell(value: string): string {
  return value.replace(/\|/g, "\\|").replace(/\n/g, " ");
}

function formatTraceMarkdown(trace: CompositionTraceFragment[]): string {
  if (trace.length === 0) {
    return "_Empty trace_";
  }
  return trace
    .map((fragment) => {
      const props = fragment.proposition_ids.join(", ") || "—";
      const locators = fragment.context_locators.join(", ") || "—";
      return `${fragment.order + 1}. **${ROLE_LABEL[fragment.role]}** \`${fragment.start}–${fragment.end}\` — ${truncate(fragment.text, 120)} _(props: ${props}; locators: ${locators}; excerpt: ${fragment.source_excerpt === EXPORT_FIELD_UNAVAILABLE ? "missing" : "present"})_`;
    })
    .join("\n");
}

export function buildCompositionTraceReport(analysis: CompositionTraceAnalysis): string {
  const opaque = analysis.opaqueStatementCount;
  const reviewable = analysis.traceReviewableCount;
  const reviewablePct = opaque > 0 ? ((reviewable / opaque) * 100).toFixed(1) : "0.0";
  const blocked = opaque - reviewable;
  const blockedPct = opaque > 0 ? ((blocked / opaque) * 100).toFixed(1) : "0.0";

  const lines: string[] = [];
  lines.push("# Composition trace report");
  lines.push("");
  lines.push(`**Date:** ${new Date().toISOString().slice(0, 10)}`);
  lines.push("**Corpus:** Slurry GB principal-5 (regenerated export)");
  lines.push(`**Export:** \`${analysis.exportDir}\``);
  lines.push("");
  lines.push(
    "Prototypes first-class **composition traces** for statements currently flagged **composition opacity**, using deterministic reconstruction from statement recipes and proposition links (no LLM).",
  );
  lines.push("");
  lines.push("## Executive summary");
  lines.push("");
  lines.push(
    `- **${opaque}** / ${analysis.totalStatements} statements carry composition opacity triggers (same class as Prompt 82 reviewability blockers).`,
  );
  lines.push(
    `- **${reviewable}** (${reviewablePct}%) become **trace-reviewable** when decomposed into ordered composition traces with role labels and provenance.`,
  );
  lines.push(
    `- **${blocked}** (${blockedPct}%) remain opaque: traces exist but fail reviewability gates (unknown coverage, missing context surfacing, or incomplete provenance).`,
  );
  lines.push(
    `- **Verdict:** Explicit composition traces eliminate composition opacity for **${reviewablePct}%** of opaque statements; the remainder need better text-span alignment or context fragments, not just export packaging.`,
  );
  lines.push("");
  lines.push("## 1. Methodology");
  lines.push("");
  lines.push("### Opacity population");
  lines.push("");
  lines.push("A statement is **composition-opaque** when any of:");
  lines.push("");
  lines.push("- `high_composition` — 3+ unique linked propositions");
  lines.push("- `standalone_status` is `context_dependent` or `partially_resolved`");
  lines.push("- 3+ `required_context` entries");
  lines.push("- non-empty `connector_context`");
  lines.push("");
  lines.push("### Trace construction (deterministic)");
  lines.push("");
  lines.push("1. `buildStatementRecipe()` — one row per proposition ref (source, supporting, required context, connector/via)");
  lines.push("2. `buildStatementCompositionSegments()` — ordered text spans aligned to statement text");
  lines.push("3. Role classification per fragment from ref role + `legal_effect_type` / `proposition_tier` / `presentation_role`");
  lines.push("");
  lines.push("### Trace-reviewability gates");
  lines.push("");
  lines.push("A trace **resolves opacity** when all hold:");
  lines.push("");
  lines.push("- Not a single `unknown` span covering the statement");
  lines.push(
    "- **Structural decomposition** for multi-proposition / context-dependent statements: ≥2 non-unknown fragments, or one fragment with ≥2 proposition IDs and a `required_context` role",
  );
  lines.push(
    "- **Context surfacing** for `context_dependent` / `partially_resolved` with linked context: at least one `required_context` trace fragment",
  );
  lines.push(`- Unknown text coverage ≤ ${(UNKNOWN_COVERAGE_THRESHOLD * 100).toFixed(0)}%`);
  lines.push(`- ≥ ${(PROPOSITION_COVERAGE_THRESHOLD * 100).toFixed(0)}% of linked propositions appear in trace fragments`);
  lines.push("- Every `required_context` proposition appears in a `required_context` trace fragment");
  lines.push("- Every non-unknown fragment has proposition linkage and source excerpt");
  lines.push("");
  lines.push("## 2. Population breakdown");
  lines.push("");
  lines.push("| Opacity trigger | Statements |");
  lines.push("| --- | ---: |");
  for (const [trigger, count] of Object.entries(analysis.triggerCounts) as Array<
    [OpacityTrigger, number]
  >) {
    lines.push(`| ${trigger.replaceAll("_", " ")} | ${count} |`);
  }
  lines.push("");
  lines.push("_Triggers are non-exclusive._");
  lines.push("");
  lines.push("### Resolution rate by trigger");
  lines.push("");
  lines.push("| Opacity trigger | Opaque statements | Trace-reviewable | Rate |");
  lines.push("| --- | ---: | ---: | ---: |");
  for (const trigger of Object.keys(analysis.triggerResolution) as OpacityTrigger[]) {
    const stats = analysis.triggerResolution[trigger];
    const rate = stats.total > 0 ? `${((stats.traceReviewable / stats.total) * 100).toFixed(1)}%` : "—";
    lines.push(
      `| ${trigger.replaceAll("_", " ")} | ${stats.total} | ${stats.traceReviewable} | ${rate} |`,
    );
  }
  lines.push("");
  lines.push("### Trace outcome");
  lines.push("");
  lines.push("| Outcome | Count | Share of opaque |");
  lines.push("| --- | ---: | ---: |");
  lines.push(`| Trace-reviewable (opacity resolvable) | ${reviewable} | ${reviewablePct}% |`);
  lines.push(`| Trace present but blocked | ${blocked} | ${blockedPct}% |`);
  lines.push("");
  lines.push("### Residual opacity reasons (blocked statements)");
  lines.push("");
  lines.push("| Reason | Statements |");
  lines.push("| --- | ---: |");
  for (const [reason, count] of Object.entries(analysis.residualReasonCounts)) {
    lines.push(`| ${reason.replaceAll("_", " ")} | ${count} |`);
  }
  lines.push("");
  lines.push("### Fragment role distribution (across all trace fragments)");
  lines.push("");
  lines.push("| Role | Fragments |");
  lines.push("| --- | ---: |");
  for (const [role, count] of Object.entries(analysis.roleCounts) as Array<
    [CompositionTraceRole, number]
  >) {
    lines.push(`| ${ROLE_LABEL[role]} | ${count} |`);
  }
  lines.push("");
  lines.push("## 3. Sampled statements");
  lines.push("");
  lines.push(
    `${analysis.samples.length} opaque statements sampled across triggers and trace outcomes. Ordered composition traces shown below.`,
  );
  lines.push("");

  analysis.samples.forEach((sample, index) => {
    lines.push(`### Sample ${index + 1}: \`${sample.statementId}\``);
    lines.push("");
    lines.push(`- **Standalone:** \`${sample.standaloneStatus}\``);
    lines.push(`- **Triggers:** ${sample.opacityTriggers.join(", ")}`);
    lines.push(
      `- **Trace-reviewable:** ${sample.traceReviewable ? "yes" : "no"}${sample.residualOpacityReasons.length ? ` (${sample.residualOpacityReasons.join(", ")})` : ""}`,
    );
    lines.push(`- **Fragments:** ${sample.fragmentCount}; unknown coverage: ${(sample.unknownCoverageRatio * 100).toFixed(1)}%`);
    lines.push("");
    lines.push(`> ${truncate(sample.statementText, 300)}`);
    lines.push("");
    lines.push("**Composition trace:**");
    lines.push("");
    lines.push(formatTraceMarkdown(sample.trace));
    lines.push("");
  });

  lines.push("## 4. Findings");
  lines.push("");
  const topReason = Object.entries(analysis.residualReasonCounts)[0];
  lines.push(
    `1. **Traces are buildable today** from existing export fields — no LLM required. Current export has no \`statement_recipe\` or \`composition_trace\`; workbench derives recipes from proposition links.`,
  );
  lines.push(
    `2. **${reviewablePct}% resolvable** — explicit traces clear composition opacity only where structural decomposition and context surfacing already succeed; monolithic single-fragment traces do not count.`,
  );
  lines.push(
    `3. **Dominant residual blocker:** ${topReason ? `\`${topReason[0]}\` (${topReason[1]} statements)` : "none"} — most opaque statements collapse to one source-proposition span; context and supporting propositions are linked in metadata but not text-positioned.`,
  );
  lines.push(
    "4. **High-composition statements** with multiple proposition refs in one aligned span can pass when `required_context` role is assigned — but `context_dependent` statements without `required_context` fragments remain monolithic.",
  );
  lines.push(
    "5. **Exporting traces is necessary but not sufficient** — pipeline must also emit `statement_fragments` with text-aligned spans per proposition, or opacity persists despite trace metadata.",
  );
  lines.push("");
  lines.push("## 5. Proposed export extension");
  lines.push("");
  lines.push("### Schema");
  lines.push("");
  lines.push("Add optional `composition_trace` to each `effective_law_statements` entry:");
  lines.push("");
  lines.push("```json");
  lines.push(
    JSON.stringify(
      {
        composition_trace: [
          {
            order: 0,
            text: "fragment text as it appears in statement_text",
            start: 0,
            end: 42,
            role: "core_proposition",
            proposition_ids: ["prop-abc"],
            context_locators: [],
            source_locator: "SI 2010/2211, reg 4(1)",
            source_excerpt: "verbatim excerpt from source fragment",
            support_status: "supported",
          },
        ],
      },
      null,
      2,
    ),
  );
  lines.push("```");
  lines.push("");
  lines.push("**`role` enum:** `core_proposition` | `supporting_proposition` | `definition` | `exception` | `required_context` | `connector_inference` | `unknown`");
  lines.push("");
  lines.push("**Invariants:**");
  lines.push("");
  lines.push("- Fragments are ordered; `start`/`end` are half-open offsets into `statement_text`");
  lines.push("- `text` must equal `statement_text.slice(start, end)`");
  lines.push("- `proposition_ids` must be subset of statement's linked propositions");
  lines.push("- `required_context` fragments must include `context_locators` from `required_context`");
  lines.push("");
  lines.push("### Migration strategy");
  lines.push("");
  lines.push("1. **Phase 0 (now):** Workbench computes traces client-side via `buildCompositionTrace()` — no export change.");
  lines.push("2. **Phase 1:** Pipeline emits `composition_trace` on export using the same deterministic functions (shared TS module or Python port).");
  lines.push("3. **Phase 2:** Backfill existing runs on read; `statement_recipe` remains the per-proposition row view, `composition_trace` is the ordered text-span view.");
  lines.push("4. **Phase 3:** Use trace quality gates in `run_quality_summary` — count `trace_reviewable` vs `composition_opaque` per run.");
  lines.push("");
  lines.push("### Workbench rendering implications");
  lines.push("");
  lines.push("- **Statement review panel:** Render `composition_trace` as the primary highlighted text (replacing derived `buildStatementCompositionSegments` when export field present).");
  lines.push("- **Role colours:** Map roles to existing segment surface classes — core/supporting → composition source; required_context → assessment context; unknown → dashed inferred.");
  lines.push("- **Inspector stack:** Click fragment → scroll proposition stack filtered to `proposition_ids`; show `source_excerpt` inline.");
  lines.push("- **Queue filters:** Add \"trace-blocked\" preset for statements where `composition_trace` exists but fails reviewability gates.");
  lines.push("- **No regression:** When `composition_trace` absent, keep current derived path (`buildStatementRecipe` + `buildStatementCompositionSegments`).");
  lines.push("");
  lines.push("## Methodology notes");
  lines.push("");
  lines.push("- Export analysed: `runs/slurry-gb-principal-5-current-export`");
  lines.push("- Functions: `buildStatementRecipe`, `buildStatementCompositionSegments`, `propositionRefsForStatement`");
  lines.push("- Re-run: `uv run --package law-proposition-extractor-pipeline python scripts/generate_composition_trace_report.py`");
  lines.push("");
  return lines.join("\n");
}
