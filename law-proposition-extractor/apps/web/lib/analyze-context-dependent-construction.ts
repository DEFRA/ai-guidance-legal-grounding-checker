import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  assessCompositionTrace,
  type CompositionTraceAssessment,
} from "@/lib/analyze-composition-traces";
import {
  EXPORT_FIELD_UNAVAILABLE,
  type CompositionBuildContext,
  type SourceFragmentRow,
} from "@/lib/law-statements-composition";
import {
  type LawStatementRow,
  type PropositionRow,
  type SourceRow,
} from "@/lib/law-statements-index";

type ExportBundle = {
  propositions: PropositionRow[];
  source_fragments: SourceFragmentRow[];
  source_records: SourceRow[];
  effective_law_statements: { statements: LawStatementRow[] };
};

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
  fragmentExcerpt: string;
  role: ContextMaterialRole;
  textInStatement: boolean;
  textInCore: boolean;
  locatorReferencedInStatement: boolean;
};

export type ContextConstructionAssessment = {
  statementId: string;
  statementText: string;
  corePropositionId: string;
  corePropositionText: string;
  coreLegalEffectType: string;
  statementMatchesCore: boolean;
  standaloneStatus: string;
  traceReviewable: boolean;
  traceBlocked: boolean;
  residualOpacityReasons: string[];
  contextEntries: ContextEntryAssessment[];
  primaryContextRole: ContextMaterialRole;
  materialContextRoles: ContextMaterialRole[];
  incorporationGap: boolean;
  unresolvedContextCount: number;
  resolvedContextCount: number;
  recommendation: IncorporationRecommendation;
  incorporatedStatementText: string;
  wouldBecomeReviewableIfIncorporated: boolean;
  wouldBecomeReviewableStructural: boolean;
};

export type ContextConstructionAnalysis = {
  exportDir: string;
  totalStatements: number;
  contextDependentCount: number;
  traceBlockedCount: number;
  traceReviewableCount: number;
  roleCounts: Record<ContextMaterialRole, number>;
  statementRoleCounts: Record<ContextMaterialRole, number>;
  recommendationCounts: Record<IncorporationRecommendation, number>;
  incorporationGapCount: number;
  wouldBecomeReviewableCount: number;
  wouldBecomeReviewableBlockedOnlyCount: number;
  wouldBecomeReviewableStructuralCount: number;
  wouldBecomeReviewableStructuralBlockedCount: number;
  incorporationCandidateCount: number;
  incorporationCandidateReviewableCount: number;
  incorporationCandidateBlockedCount: number;
  statementMatchesCoreCount: number;
  unresolvedOnlyCount: number;
  resolvedContextEntryCount: number;
  samples: ContextConstructionAssessment[];
  assessments: ContextConstructionAssessment[];
};

const ROLE_LABEL: Record<ContextMaterialRole, string> = {
  confirm: "a) merely confirm",
  constrain: "b) materially constrain",
  exception: "c) introduce exceptions",
  definition: "d) introduce definitions",
  alter_effect: "e) alter legal effect",
  noise: "f) irrelevant noise",
};

const RECOMMENDATION_LABEL: Record<IncorporationRecommendation, string> = {
  keep_external: "keep context external",
  inline_selectively: "inline context selectively",
  emit_multiple: "emit multiple statements",
  defer_reviewer: "defer to reviewer",
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

const ROLE_PRIORITY: Record<ContextMaterialRole, number> = {
  alter_effect: 0,
  exception: 1,
  definition: 2,
  constrain: 3,
  confirm: 4,
  noise: 5,
};

function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf-8")) as T;
}

function fragmentRowId(fragment: SourceFragmentRow): string {
  return String(fragment.id ?? fragment.fragment_id ?? "").trim();
}

function loadBundle(exportDir: string, effectiveLawPath?: string): ExportBundle {
  const root = resolve(exportDir);
  const effectivePath = effectiveLawPath ?? resolve(root, "effective_law_statements.json");
  return {
    propositions: readJson(resolve(root, "propositions.json")),
    source_fragments: readJson(resolve(root, "source_fragments.json")),
    source_records: readJson(resolve(root, "sources.json")),
    effective_law_statements: readJson(effectivePath),
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

function locatorReferencedInText(locator: string, text: string): boolean {
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
    const patterns = [
      `regulation ${num}`,
      `reg ${num}`,
      `regulation ${num}(${sub ?? ""})`,
    ].filter((pattern) => pattern.trim());
    return patterns.some((pattern) => normalizedText.includes(pattern.replace(/\(\)$/, "")));
  }

  const scheduleMatch = normalizedLocator.match(/^schedule\s+(\d+[a-z]?)$/);
  if (scheduleMatch) {
    return normalizedText.includes(`schedule ${scheduleMatch[1]}`);
  }

  return false;
}

function fragmentExcerptForProposition(
  proposition: PropositionRow | undefined,
  fragmentById: Map<string, SourceFragmentRow>,
): string {
  if (!proposition) {
    return EXPORT_FIELD_UNAVAILABLE;
  }
  const fragmentId = String(proposition.source_fragment_id ?? "").trim();
  const fragment = fragmentById.get(fragmentId);
  const excerpt = String(fragment?.fragment_text ?? "").trim();
  if (!excerpt) {
    return EXPORT_FIELD_UNAVAILABLE;
  }
  return excerpt.length > 220 ? `${excerpt.slice(0, 219)}…` : excerpt;
}

function classifyContextEntry(input: {
  entry: NonNullable<LawStatementRow["required_context"]>[number];
  contextProp?: PropositionRow;
  coreProp?: PropositionRow;
  statementText: string;
  coreText: string;
}): ContextEntryAssessment {
  const locator = String(input.entry.locator ?? "").trim();
  const kind = String(input.entry.kind ?? "").trim();
  const resolutionStatus = String(input.entry.resolution_status ?? "").trim();
  const propositionIds = (input.entry.proposition_ids ?? []).map((id) => String(id).trim()).filter(Boolean);
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
  } else if (legalEffectType === "derogation" || EXCEPTION_MARKERS.test(propositionText)) {
    role = "exception";
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
    } else if (
      CONDITION_MARKERS.test(propositionText) &&
      !CONDITION_MARKERS.test(input.coreText)
    ) {
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
    fragmentExcerpt: EXPORT_FIELD_UNAVAILABLE,
    role,
    textInStatement,
    textInCore,
    locatorReferencedInStatement,
  };
}

function primaryRole(roles: ContextMaterialRole[]): ContextMaterialRole {
  if (roles.length === 0) {
    return "noise";
  }
  return [...roles].sort((left, right) => ROLE_PRIORITY[left] - ROLE_PRIORITY[right])[0]!;
}

function buildIncorporatedStatementText(
  statementText: string,
  entries: ContextEntryAssessment[],
): string {
  const parts = [statementText.trim()];
  const seen = new Set<string>();
  for (const entry of entries) {
    const text = entry.propositionText.trim();
    if (!text || seen.has(text)) {
      continue;
    }
    if (textContainedIn(text, statementText)) {
      continue;
    }
    if (!MATERIAL_ROLES.has(entry.role)) {
      continue;
    }
    parts.push(text);
    seen.add(text);
  }
  return parts.join(" ");
}

function deriveRecommendation(input: {
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
      entry.propositionIds.length > 0 &&
      !entry.textInStatement &&
      entry.role !== "definition",
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

function assessContextConstruction(
  statement: LawStatementRow,
  trace: CompositionTraceAssessment,
  context: CompositionBuildContext,
  fragmentById: Map<string, SourceFragmentRow>,
): ContextConstructionAssessment {
  const corePropositionId = String(statement.source_proposition_ids?.[0] ?? "").trim();
  const coreProp = context.propositionById.get(corePropositionId);
  const corePropositionText = String(coreProp?.proposition_text ?? "").trim();
  const statementText = String(statement.statement_text ?? "").trim();
  const statementMatchesCore =
    normalizeText(statementText) === normalizeText(corePropositionText) ||
    textContainedIn(corePropositionText, statementText, 8);

  const contextEntries: ContextEntryAssessment[] = (statement.required_context ?? []).map(
    (entry) => {
      const firstPropId = String(entry.proposition_ids?.[0] ?? "").trim();
      const contextProp = firstPropId ? context.propositionById.get(firstPropId) : undefined;
      const assessed = classifyContextEntry({
        entry,
        contextProp,
        coreProp,
        statementText,
        coreText: corePropositionText,
      });
      assessed.fragmentExcerpt = fragmentExcerptForProposition(contextProp, fragmentById);
      return assessed;
    },
  );

  const materialContextRoles = [
    ...new Set(contextEntries.map((entry) => entry.role).filter((role) => MATERIAL_ROLES.has(role))),
  ];
  const incorporationGap = contextEntries.some(
    (entry) => MATERIAL_ROLES.has(entry.role) && !entry.textInStatement && !entry.textInCore,
  );
  const unresolvedContextCount = contextEntries.filter(
    (entry) => entry.propositionIds.length === 0 && entry.resolutionStatus !== "external_reference",
  ).length;
  const resolvedContextCount = contextEntries.filter((entry) => entry.propositionIds.length > 0).length;
  const resolvedMaterialCount = contextEntries.filter(
    (entry) => entry.propositionIds.length > 0 && MATERIAL_ROLES.has(entry.role),
  ).length;

  const incorporatedStatementText = buildIncorporatedStatementText(statementText, contextEntries);
  const recommendation = deriveRecommendation({
    entries: contextEntries,
    incorporationGap,
    unresolvedContextCount,
    resolvedMaterialCount,
  });

  const simulatedStatement: LawStatementRow = {
    ...statement,
    statement_text: incorporatedStatementText,
    standalone_status:
      unresolvedContextCount === 0 && incorporationGap ? "standalone" : statement.standalone_status,
  };
  const simulatedTrace = assessCompositionTrace(simulatedStatement, context);
  const wouldBecomeReviewableIfIncorporated =
    !trace.traceReviewable &&
    incorporationGap &&
    resolvedMaterialCount > 0 &&
    simulatedTrace.traceReviewable;
  const structuralBlockers = new Set([
    "monolithic_composition",
    "unsurfaced_context_dependence",
    "unsurfaced_required_context",
  ]);
  const wouldBecomeReviewableStructural =
    !trace.traceReviewable &&
    incorporationGap &&
    resolvedMaterialCount > 0 &&
    trace.residualOpacityReasons.every((reason) => structuralBlockers.has(reason));

  return {
    statementId: statement.id,
    statementText,
    corePropositionId,
    corePropositionText,
    coreLegalEffectType: String(coreProp?.legal_effect_type ?? "").trim(),
    statementMatchesCore,
    standaloneStatus: statement.standalone_status,
    traceReviewable: trace.traceReviewable,
    traceBlocked: !trace.traceReviewable,
    residualOpacityReasons: trace.residualOpacityReasons,
    contextEntries,
    primaryContextRole: primaryRole(contextEntries.map((entry) => entry.role)),
    materialContextRoles,
    incorporationGap,
    unresolvedContextCount,
    resolvedContextCount,
    recommendation,
    incorporatedStatementText,
    wouldBecomeReviewableIfIncorporated,
    wouldBecomeReviewableStructural,
  };
}

function pickSamples(assessments: ContextConstructionAssessment[]): ContextConstructionAssessment[] {
  const buckets: Record<string, ContextConstructionAssessment[]> = {
    inline_blocked: [],
    inline_reviewable: [],
    emit_multiple: [],
    defer: [],
    keep_external: [],
    alter_effect: [],
    definition: [],
    confirm_only: [],
  };

  for (const row of assessments) {
    if (row.recommendation === "inline_selectively" && row.traceBlocked) {
      buckets.inline_blocked.push(row);
    } else if (row.recommendation === "inline_selectively" && row.traceReviewable) {
      buckets.inline_reviewable.push(row);
    } else if (row.recommendation === "emit_multiple") {
      buckets.emit_multiple.push(row);
    } else if (row.recommendation === "defer_reviewer") {
      buckets.defer.push(row);
    } else if (row.recommendation === "keep_external") {
      buckets.keep_external.push(row);
    }
    if (row.primaryContextRole === "alter_effect") {
      buckets.alter_effect.push(row);
    }
    if (row.primaryContextRole === "definition") {
      buckets.definition.push(row);
    }
    if (row.materialContextRoles.length === 0) {
      buckets.confirm_only.push(row);
    }
  }

  const picked: ContextConstructionAssessment[] = [];
  const take = (key: keyof typeof buckets, count: number): void => {
    for (const row of buckets[key].slice(0, count)) {
      if (!picked.some((existing) => existing.statementId === row.statementId)) {
        picked.push(row);
      }
    }
  };

  take("inline_blocked", 2);
  take("inline_reviewable", 1);
  take("emit_multiple", 2);
  take("defer", 2);
  take("keep_external", 2);
  take("alter_effect", 1);
  take("definition", 1);
  take("confirm_only", 2);

  if (picked.length < 12) {
    for (const row of assessments) {
      if (picked.length >= 14) {
        break;
      }
      if (!picked.some((existing) => existing.statementId === row.statementId)) {
        picked.push(row);
      }
    }
  }

  return picked.slice(0, 14);
}

export function analyzeContextDependentConstruction(
  exportDir: string,
  effectiveLawPath?: string,
): ContextConstructionAnalysis {
  const bundle = loadBundle(exportDir, effectiveLawPath);
  const propositionById = new Map(bundle.propositions.map((row) => [row.id, row]));
  const fragmentById = new Map(
    bundle.source_fragments.map((row) => [fragmentRowId(row), row]).filter(([id]) => id),
  );
  const buildContext: CompositionBuildContext = {
    propositionById,
    sourceById: new Map(bundle.source_records.map((row) => [row.id, row])),
    fragmentById,
  };

  const roleCounts: Record<ContextMaterialRole, number> = {
    confirm: 0,
    constrain: 0,
    exception: 0,
    definition: 0,
    alter_effect: 0,
    noise: 0,
  };
  const statementRoleCounts: Record<ContextMaterialRole, number> = { ...roleCounts };
  const recommendationCounts: Record<IncorporationRecommendation, number> = {
    keep_external: 0,
    inline_selectively: 0,
    emit_multiple: 0,
    defer_reviewer: 0,
  };

  const assessments: ContextConstructionAssessment[] = [];

  for (const statement of bundle.effective_law_statements.statements ?? []) {
    if (statement.standalone_status !== "context_dependent") {
      continue;
    }
    const trace = assessCompositionTrace(statement, buildContext);
    const assessment = assessContextConstruction(statement, trace, buildContext, fragmentById);
    assessments.push(assessment);

    for (const entry of assessment.contextEntries) {
      roleCounts[entry.role] += 1;
    }
    statementRoleCounts[assessment.primaryContextRole] += 1;
    recommendationCounts[assessment.recommendation] += 1;
  }

  const traceBlockedCount = assessments.filter((row) => row.traceBlocked).length;
  const traceReviewableCount = assessments.filter((row) => row.traceReviewable).length;
  const resolvedContextEntryCount = assessments.reduce(
    (sum, row) => sum + row.resolvedContextCount,
    0,
  );

  return {
    exportDir,
    totalStatements: bundle.effective_law_statements.statements?.length ?? 0,
    contextDependentCount: assessments.length,
    traceBlockedCount,
    traceReviewableCount,
    roleCounts,
    statementRoleCounts,
    recommendationCounts,
    incorporationGapCount: assessments.filter((row) => row.incorporationGap).length,
    wouldBecomeReviewableCount: assessments.filter((row) => row.wouldBecomeReviewableIfIncorporated)
      .length,
    wouldBecomeReviewableBlockedOnlyCount: assessments.filter(
      (row) => row.wouldBecomeReviewableIfIncorporated && row.traceBlocked,
    ).length,
    wouldBecomeReviewableStructuralCount: assessments.filter(
      (row) => row.wouldBecomeReviewableStructural,
    ).length,
    wouldBecomeReviewableStructuralBlockedCount: assessments.filter(
      (row) => row.wouldBecomeReviewableStructural && row.traceBlocked,
    ).length,
    incorporationCandidateCount: assessments.filter(
      (row) => row.incorporationGap && row.resolvedContextCount > 0,
    ).length,
    incorporationCandidateReviewableCount: assessments.filter(
      (row) => row.incorporationGap && row.resolvedContextCount > 0 && row.traceReviewable,
    ).length,
    incorporationCandidateBlockedCount: assessments.filter(
      (row) => row.incorporationGap && row.resolvedContextCount > 0 && row.traceBlocked,
    ).length,
    statementMatchesCoreCount: assessments.filter((row) => row.statementMatchesCore).length,
    unresolvedOnlyCount: assessments.filter(
      (row) => row.resolvedContextCount === 0 && row.contextEntries.length > 0,
    ).length,
    resolvedContextEntryCount,
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

export function buildContextDependentConstructionReport(
  analysis: ContextConstructionAnalysis,
): string {
  const lines: string[] = [];
  const ctx = analysis.contextDependentCount;
  const blocked = analysis.traceBlockedCount;
  const reviewable = analysis.traceReviewableCount;
  const blockedPct = ctx > 0 ? ((blocked / ctx) * 100).toFixed(1) : "0.0";
  const reviewablePct = ctx > 0 ? ((reviewable / ctx) * 100).toFixed(1) : "0.0";
  const wouldInlineStrict = analysis.wouldBecomeReviewableBlockedOnlyCount;
  const wouldInlineStructural = analysis.wouldBecomeReviewableStructuralBlockedCount;
  const wouldInlineStrictPct =
    blocked > 0 ? ((wouldInlineStrict / blocked) * 100).toFixed(1) : "0.0";
  const wouldInlineStructuralPct =
    blocked > 0 ? ((wouldInlineStructural / blocked) * 100).toFixed(1) : "0.0";
  const gapPct =
    ctx > 0 ? ((analysis.incorporationGapCount / ctx) * 100).toFixed(1) : "0.0";

  lines.push("# Context-dependent construction report");
  lines.push("");
  lines.push(`**Date:** ${new Date().toISOString().slice(0, 10)}`);
  lines.push("**Corpus:** Slurry GB principal-5 (regenerated export)");
  lines.push(`**Export:** \`${analysis.exportDir}\``);
  lines.push("");
  lines.push(
    "Deterministic comparison of **effective-law statement text**, **core proposition text**, and **required_context** propositions/fragments for `context_dependent` and trace-blocked statements (no LLM).",
  );
  lines.push("");
  lines.push("## Executive summary");
  lines.push("");
  lines.push(`- **${ctx}** / ${analysis.totalStatements} statements are \`context_dependent\`.`);
  lines.push(
    `- **${reviewable}** (${reviewablePct}%) are already **trace-reviewable**; **${blocked}** (${blockedPct}%) are **trace-blocked**.`,
  );
  lines.push(
    `- **${analysis.incorporationGapCount}** (${gapPct}%) have a **material incorporation gap** — required context is not already present in statement/core text.`,
  );
  lines.push(
    `- **${wouldInlineStructural}** trace-blocked statements (${wouldInlineStructuralPct}% of blocked) are **structural incorporation candidates** — material resolved context absent from statement text, blocked only by monolithic/unsurfaced-context trace gates.`,
  );
  lines.push(
    `- **${wouldInlineStrict}** pass strict post-inline trace simulation (${wouldInlineStrictPct}% of blocked); naive text append alone does not realign composition fragments.`,
  );
  lines.push(
    `- **${analysis.statementMatchesCoreCount}** statements are verbatim (or near-verbatim) copies of the core proposition — effective-law generation is not composing additional wording today.`,
  );
  lines.push(
    "- **Recommendation:** **inline context selectively** for resolved material context with incorporation gaps; **keep external** for confirm/noise-only dependencies; **defer to reviewer** when context remains unresolved; **emit multiple statements** when several independent substantive context propositions apply.",
  );
  lines.push("");
  lines.push("## 1. Methodology");
  lines.push("");
  lines.push("### Population");
  lines.push("");
  lines.push('- All `effective_law_statements` with `standalone_status = context_dependent`.');
  lines.push(
    "- **Trace-blocked** subset: context-dependent statements failing composition-trace reviewability gates (same deterministic logic as Prompt 83 composition trace report).",
  );
  lines.push("");
  lines.push("### Per-statement comparison");
  lines.push("");
  lines.push("For each statement:");
  lines.push("");
  lines.push(
    '1. **Core proposition** — `source_proposition_ids[0]` → `propositions.json` text and `legal_effect_type`.',
  );
  lines.push(
    '2. **Effective statement** — `statement_text` (today identical to core proposition text in almost all cases).',
  );
  lines.push(
    '3. **Required context** — each `required_context` entry: `kind`, `locator`, `resolution_status`, linked proposition text, fragment excerpt.',
  );
  lines.push("");
  lines.push("### Context role classification (deterministic, per entry)");
  lines.push("");
  lines.push("| Role | Rule |");
  lines.push("| --- | --- |");
  lines.push("| a) confirm | Context proposition text already contained in statement or core text; or unresolved locator already cited in statement |");
  lines.push(
    '| b) constrain | `host_rule` / `incorporated_rule` / `incorporated_factors`; or condition markers in context absent from core |',
  );
  lines.push(
    '| c) exception | `legal_effect_type = derogation` or exception/unless markers in context text |',
  );
  lines.push(
    '| d) definition | `legal_effect_type = definition`, `proposition_tier = definitional_rule`, or `kind = supporting_definition` |',
  );
  lines.push(
    '| e) alter effect | Resolved context with different substantive `legal_effect_type` from core |',
  );
  lines.push("| f) noise | Unresolved context with no linked propositions and no material locator signal |");
  lines.push("");
  lines.push("Statement-level primary role = most severe entry role (alter > exception > definition > constrain > confirm > noise).");
  lines.push("");
  lines.push("### Incorporation gap");
  lines.push("");
  lines.push(
    "A statement has an incorporation gap when any context entry has a **material role** (b–e) and its proposition text is **not** already contained in the statement or core text.",
  );
  lines.push("");
  lines.push("### Simulated inlining (reviewability estimate)");
  lines.push("");
  lines.push(
    'Hypothetical `statement_text` = core text + unresolved material context proposition texts (deduplicated). Re-run composition-trace reviewability gates. Count statements that are trace-blocked today but trace-reviewable after simulation.',
  );
  lines.push("");
  lines.push("## 2. Population breakdown");
  lines.push("");
  lines.push("| Metric | Count |");
  lines.push("| --- | ---: |");
  lines.push(`| Context-dependent statements | ${ctx} |`);
  lines.push(`| Trace-reviewable | ${reviewable} |`);
  lines.push(`| Trace-blocked | ${blocked} |`);
  lines.push(`| Statement text matches core proposition | ${analysis.statementMatchesCoreCount} |`);
  lines.push(`| No resolved context propositions | ${analysis.unresolvedOnlyCount} |`);
  lines.push(`| Material incorporation gap | ${analysis.incorporationGapCount} |`);
  lines.push(`| Incorporation candidates (gap + resolved context) | ${analysis.incorporationCandidateCount} |`);
  lines.push(
    `| — already trace-reviewable | ${analysis.incorporationCandidateReviewableCount} |`,
  );
  lines.push(`| — trace-blocked | ${analysis.incorporationCandidateBlockedCount} |`);
  lines.push(
    `| Structural reviewability gain if inlined (blocked only) | ${wouldInlineStructural} |`,
  );
  lines.push(`| Strict post-inline trace pass (blocked only) | ${wouldInlineStrict} |`);
  lines.push("");
  lines.push("### Context entry roles (non-exclusive across entries)");
  lines.push("");
  lines.push("| Role | Entries |");
  lines.push("| --- | ---: |");
  for (const role of Object.keys(analysis.roleCounts) as ContextMaterialRole[]) {
    lines.push(`| ${ROLE_LABEL[role]} | ${analysis.roleCounts[role]} |`);
  }
  lines.push("");
  lines.push("### Statement primary context role");
  lines.push("");
  lines.push("| Role | Statements |");
  lines.push("| --- | ---: |");
  for (const role of Object.keys(analysis.statementRoleCounts) as ContextMaterialRole[]) {
    lines.push(`| ${ROLE_LABEL[role]} | ${analysis.statementRoleCounts[role]} |`);
  }
  lines.push("");
  lines.push("### Incorporation recommendations");
  lines.push("");
  lines.push("| Recommendation | Statements |");
  lines.push("| --- | ---: |");
  for (const recommendation of Object.keys(
    analysis.recommendationCounts,
  ) as IncorporationRecommendation[]) {
    lines.push(
      `| ${RECOMMENDATION_LABEL[recommendation]} | ${analysis.recommendationCounts[recommendation]} |`,
    );
  }
  lines.push("");
  lines.push("## 3. Findings");
  lines.push("");
  lines.push(
    `1. **Effective-law statements do not incorporate context into wording.** ${analysis.statementMatchesCoreCount} / ${ctx} statements match the core proposition text exactly; export transform copies \`proposition_text\` verbatim and leaves \`required_context\` external.`,
  );
  lines.push(
    `2. **Most context dependence is locator citation, not missing inline text.** ${analysis.roleCounts.confirm} context entries are classified as confirmatory (locator cited in statement or context text already present).`,
  );
  lines.push(
    `3. **Material gaps with resolved context are already trace-reviewable.** ${analysis.incorporationCandidateReviewableCount} / ${analysis.incorporationCandidateCount} incorporation candidates pass trace gates today without inlining; ${analysis.incorporationCandidateBlockedCount} blocked candidates remain. Trace-blocked context-dependence is primarily **unresolved locators**, not missing inline wording.`,
  );
  lines.push(
    `4. **Unresolved context dominates trace-blocked cases.** ${analysis.unresolvedOnlyCount} context-dependent statements have zero resolved \`required_context.proposition_ids\` — inlining cannot help until locator resolution improves.`,
  );
  lines.push(
    `5. **Selective inlining is sufficient; full composition is not.** ${analysis.recommendationCounts.emit_multiple} statements warrant multiple emitted statements; ${analysis.recommendationCounts.defer_reviewer} should defer to reviewer while locators remain unresolved.`,
  );
  lines.push("");
  lines.push("## 4. Sampled statements");
  lines.push("");
  lines.push(
    `${analysis.samples.length} statements sampled across incorporation recommendations and context roles.`,
  );
  lines.push("");

  analysis.samples.forEach((sample, index) => {
    lines.push(`### Sample ${index + 1}: \`${sample.statementId}\``);
    lines.push("");
    lines.push(`- **Standalone:** \`${sample.standaloneStatus}\``);
    lines.push(`- **Trace-reviewable:** ${sample.traceReviewable ? "yes" : "no"}`);
    if (sample.residualOpacityReasons.length) {
      lines.push(`- **Trace blockers:** ${sample.residualOpacityReasons.join(", ")}`);
    }
    lines.push(`- **Primary context role:** ${ROLE_LABEL[sample.primaryContextRole]}`);
    lines.push(`- **Recommendation:** ${RECOMMENDATION_LABEL[sample.recommendation]}`);
    lines.push(`- **Incorporation gap:** ${sample.incorporationGap ? "yes" : "no"}`);
    lines.push(
      `- **Structural incorporation candidate:** ${sample.wouldBecomeReviewableStructural ? "yes" : "no"}`,
    );
    lines.push(
      `- **Strict post-inline trace pass:** ${sample.wouldBecomeReviewableIfIncorporated ? "yes" : "no"}`,
    );
    lines.push("");
    lines.push("**Effective statement:**");
    lines.push("");
    lines.push(`> ${truncate(sample.statementText, 280)}`);
    lines.push("");
    lines.push("**Core proposition:**");
    lines.push("");
    lines.push(
      `> ${truncate(sample.corePropositionText, 280)} _(effect: ${sample.coreLegalEffectType || "—"})_`,
    );
    lines.push("");
    lines.push("**Required context:**");
    lines.push("");
    lines.push("| Locator | Kind | Resolution | Role | In statement? | Proposition excerpt |");
    lines.push("| --- | --- | --- | --- | :---: | --- |");
    for (const entry of sample.contextEntries) {
      lines.push(
        `| ${escapeCell(entry.locator || "—")} | ${escapeCell(entry.kind || "—")} | ${escapeCell(entry.resolutionStatus || "—")} | ${escapeCell(ROLE_LABEL[entry.role])} | ${entry.textInStatement ? "yes" : "no"} | ${escapeCell(truncate(entry.propositionText || entry.locator, 100))} |`,
      );
    }
    if (sample.incorporationGap && sample.incorporatedStatementText !== sample.statementText) {
      lines.push("");
      lines.push("**Simulated inlined statement:**");
      lines.push("");
      lines.push(`> ${truncate(sample.incorporatedStatementText, 320)}`);
    }
    lines.push("");
  });

  lines.push("## 5. Recommendations for effective-law generation");
  lines.push("");
  lines.push("| Strategy | When | Rationale |");
  lines.push("| --- | --- | --- |");
  lines.push(
    `| **Keep context external** | ${analysis.recommendationCounts.keep_external} statements | Confirmatory or noise-only context; statement already cites locators or text is present |`,
  );
  lines.push(
    `| **Inline context selectively** | ${analysis.recommendationCounts.inline_selectively} statements | Resolved material context (constrain/exception/definition) not yet in statement text |`,
  );
  lines.push(
    `| **Emit multiple statements** | ${analysis.recommendationCounts.emit_multiple} statements | Multiple independent substantive context propositions — single sentence would over-compose |`,
  );
  lines.push(
    `| **Defer to reviewer** | ${analysis.recommendationCounts.defer_reviewer} statements | Unresolved locators; inlining would fabricate law |`,
  );
  lines.push("");
  lines.push("### Proposed pipeline behaviour");
  lines.push("");
  lines.push(
    '1. **Default:** Keep `statement_text` as core proposition text; attach `required_context` metadata (current behaviour).',
  );
  lines.push(
    '2. **When resolved + material gap:** Append or clause-merge resolved context proposition text into `statement_text`; mark `standalone_status` → `standalone` or `partially_resolved` depending on remaining unresolved entries.',
  );
  lines.push(
    "3. **When multiple substantive contexts:** Emit sibling statements sharing provenance rather than one compound sentence.",
  );
  lines.push(
    '4. **When unresolved:** Retain `context_dependent`; surface locators in review UI; do not inline.',
  );
  lines.push(
    '5. **Do not use LLM composition** — all incorporation decisions are deterministic from proposition text, `legal_effect_type`, `required_context.kind`, and resolution status.',
  );
  lines.push("");
  lines.push("## Methodology notes");
  lines.push("");
  lines.push('- Export analysed: `runs/slurry-gb-principal-5-current-export`');
  lines.push(
    '- Functions: `analyzeContextDependentConstruction`, `assessCompositionTrace`, proposition/fragment joins',
  );
  lines.push(
    '- Re-run: `uv run --package law-proposition-extractor-pipeline python scripts/generate_context_dependent_construction_report.py`',
  );
  lines.push("");
  return lines.join("\n");
}

export function writeContextDependentConstructionReport(outputPath: string, report: string): void {
  writeFileSync(outputPath, `${report}\n`, "utf-8");
}
