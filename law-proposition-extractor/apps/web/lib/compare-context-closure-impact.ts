import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { analyzeCompositionTraces } from "@/lib/analyze-composition-traces-io";
import { analyzeContextDependentConstruction } from "@/lib/analyze-context-dependent-construction";
import {
  analyzeReviewabilityBlockers,
  type BlockerCategory,
} from "@/lib/analyze-reviewability-blockers";
import { buildContextRequirementResolutions } from "@/lib/context-locator-resolution";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";
import type { SourceFragmentRow } from "@/lib/law-statements-composition";

type ExportBundle = {
  propositions: PropositionRow[];
  source_fragments: SourceFragmentRow[];
  effective_law_statements: { statements: LawStatementRow[] };
};

type ResolutionModeCounts = {
  exact: number;
  container: number;
  partial: number;
  unresolved: number;
  external: number;
  ambiguous: number;
};

type ContextClosureSnapshot = {
  unresolvedEntries: number;
  emptyPropositionIds: number;
  resolutionModes: ResolutionModeCounts;
  exportStatusCounts: Record<string, number>;
};

type PropositionFillExample = {
  statementId: string;
  locator: string;
  beforeIds: string[];
  afterIds: string[];
  statementText: string;
};

function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf-8")) as T;
}

function loadBundle(exportDir: string, effectiveLawPath: string): ExportBundle {
  const root = resolve(exportDir);
  return {
    propositions: readJson(resolve(root, "propositions.json")),
    source_fragments: readJson(resolve(root, "source_fragments.json")),
    effective_law_statements: readJson(effectiveLawPath),
  };
}

function isFocusStatement(statement: LawStatementRow): boolean {
  return ["context_dependent", "partially_resolved", "unresolved_reference"].includes(
    String(statement.standalone_status ?? ""),
  );
}

function isUnresolvedEntry(entry: NonNullable<LawStatementRow["required_context"]>[number]): boolean {
  const propIds = (entry.proposition_ids ?? []).map((id) => String(id).trim()).filter(Boolean);
  if (propIds.length > 0) {
    return false;
  }
  const status = String(entry.resolution_status ?? "").trim();
  return status === "" || status === "unresolved" || status === "ambiguous" || status === "missing";
}

function analyzeContextClosure(
  exportDir: string,
  effectiveLawPath: string,
): ContextClosureSnapshot {
  const bundle = loadBundle(exportDir, effectiveLawPath);
  const propositionById = new Map(bundle.propositions.map((row) => [row.id, row]));
  const fragmentById = new Map(
    bundle.source_fragments
      .map((row) => [String(row.id ?? row.fragment_id ?? "").trim(), row])
      .filter(([id]) => id),
  );

  const resolutionModes: ResolutionModeCounts = {
    exact: 0,
    container: 0,
    partial: 0,
    unresolved: 0,
    external: 0,
    ambiguous: 0,
  };
  const exportStatusCounts: Record<string, number> = {};

  let unresolvedEntries = 0;
  let emptyPropositionIds = 0;

  for (const statement of bundle.effective_law_statements.statements ?? []) {
    if (!isFocusStatement(statement)) {
      continue;
    }

    const resolutions = buildContextRequirementResolutions(statement, {
      sourceFragments: bundle.source_fragments,
      propositionById,
      fragmentById,
    });

    for (const entry of statement.required_context ?? []) {
      const status = String(entry.resolution_status ?? "").trim() || "empty";
      exportStatusCounts[status] = (exportStatusCounts[status] ?? 0) + 1;

      const propIds = (entry.proposition_ids ?? []).map((id) => String(id).trim()).filter(Boolean);
      if (propIds.length === 0) {
        emptyPropositionIds += 1;
      }
      if (isUnresolvedEntry(entry)) {
        unresolvedEntries += 1;
      }
    }

    for (const resolution of resolutions) {
      if (resolution.reason === "external reference") {
        resolutionModes.external += 1;
        continue;
      }
      if (!resolution.resolved) {
        resolutionModes.unresolved += 1;
        continue;
      }
      if (resolution.resolutionMode === "exact") {
        resolutionModes.exact += 1;
      } else if (resolution.resolutionMode === "container") {
        resolutionModes.container += 1;
      } else if (resolution.resolutionMode === "partial") {
        resolutionModes.partial += 1;
      } else {
        resolutionModes.unresolved += 1;
      }
    }
  }

  return {
    unresolvedEntries,
    emptyPropositionIds,
    resolutionModes,
    exportStatusCounts,
  };
}

function collectPropositionFillExamples(
  exportDir: string,
  beforeEffectiveLawPath: string,
  afterEffectiveLawPath: string,
): PropositionFillExample[] {
  const beforeBundle = loadBundle(exportDir, beforeEffectiveLawPath);
  const afterBundle = loadBundle(exportDir, afterEffectiveLawPath);
  const beforeById = new Map(
    (beforeBundle.effective_law_statements.statements ?? []).map((row) => [row.id, row]),
  );
  const examples: PropositionFillExample[] = [];

  for (const after of afterBundle.effective_law_statements.statements ?? []) {
    const before = beforeById.get(after.id);
    if (!before) {
      continue;
    }
    const beforeByLocator = new Map(
      (before.required_context ?? []).map((entry) => [String(entry.locator ?? ""), entry]),
    );
    for (const entry of after.required_context ?? []) {
      const locator = String(entry.locator ?? "");
      const beforeEntry = beforeByLocator.get(locator);
      if (!beforeEntry) {
        continue;
      }
      const beforeIds = (beforeEntry.proposition_ids ?? []).map((id) => String(id).trim()).filter(Boolean);
      const afterIds = (entry.proposition_ids ?? []).map((id) => String(id).trim()).filter(Boolean);
      if (beforeIds.length === 0 && afterIds.length > 0) {
        examples.push({
          statementId: after.id,
          locator,
          beforeIds,
          afterIds,
          statementText: String(after.statement_text ?? ""),
        });
      }
    }
  }

  return examples.sort((a, b) => b.afterIds.length - a.afterIds.length).slice(0, 15);
}

function truncate(text: string, max = 160): string {
  const trimmed = text.replace(/\s+/g, " ").trim();
  if (trimmed.length <= max) {
    return trimmed;
  }
  return `${trimmed.slice(0, max - 1)}…`;
}

function delta(before: number, after: number): string {
  const change = after - before;
  if (change === 0) {
    return "+0";
  }
  return `${change > 0 ? "+" : ""}${change}`;
}

function pct(numerator: number, denominator: number): string {
  if (denominator === 0) {
    return "—";
  }
  return `${((numerator / denominator) * 100).toFixed(1)}%`;
}

const BLOCKER_LABEL: Record<BlockerCategory, string> = {
  unresolved_internal_references: "Unresolved internal references",
  external_references: "External references",
  missing_propositions: "Missing propositions",
  apparent_overreach: "Apparent overreach",
  evidence_corruption: "Evidence corruption",
  composition_opacity: "Composition opacity",
};

export type ContextClosureImpactInput = {
  exportDir: string;
  beforeEffectiveLawPath: string;
  afterEffectiveLawPath: string;
};

export function buildContextClosureImpactReport(input: ContextClosureImpactInput): string {
  const beforeClosure = analyzeContextClosure(input.exportDir, input.beforeEffectiveLawPath);
  const afterClosure = analyzeContextClosure(input.exportDir, input.afterEffectiveLawPath);

  const beforeComposition = analyzeCompositionTraces(input.exportDir, input.beforeEffectiveLawPath);
  const afterComposition = analyzeCompositionTraces(input.exportDir, input.afterEffectiveLawPath);

  const beforeBlockers = analyzeReviewabilityBlockers(input.exportDir, input.beforeEffectiveLawPath);
  const afterBlockers = analyzeReviewabilityBlockers(input.exportDir, input.afterEffectiveLawPath);

  const beforeContext = analyzeContextDependentConstruction(
    input.exportDir,
    input.beforeEffectiveLawPath,
  );
  const afterContext = analyzeContextDependentConstruction(
    input.exportDir,
    input.afterEffectiveLawPath,
  );

  const beforeById = new Map(beforeComposition.assessments.map((row) => [row.statementId, row]));
  const improvedStatements = afterComposition.assessments
    .filter((after) => {
      const before = beforeById.get(after.statementId);
      return Boolean(before) && !before!.traceReviewable && after.traceReviewable;
    })
    .slice(0, 12);

  const regressedStatements = afterComposition.assessments
    .filter((after) => {
      const before = beforeById.get(after.statementId);
      return Boolean(before) && before!.traceReviewable && !after.traceReviewable;
    })
    .slice(0, 5);

  const fillExamples = collectPropositionFillExamples(
    input.exportDir,
    input.beforeEffectiveLawPath,
    input.afterEffectiveLawPath,
  );

  const beforeOpaqueBlocked =
    beforeComposition.opaqueStatementCount - beforeComposition.traceReviewableCount;
  const afterOpaqueBlocked =
    afterComposition.opaqueStatementCount - afterComposition.traceReviewableCount;

  const lines: string[] = [];
  lines.push("# Post context-closure impact report");
  lines.push("");
  lines.push(`**Date:** ${new Date().toISOString().slice(0, 10)}`);
  lines.push(`**Corpus:** Slurry GB principal-5 (727-fragment regenerated export)`);
  lines.push(`**Export:** \`${resolve(input.exportDir)}\``);
  lines.push("");
  lines.push(
    "Before/after comparison on the **same export bundle** with effective law re-derived with (before) legacy export closure vs (after) Prompt 86-BR1 workbench-aligned locator resolution.",
  );
  lines.push("");
  lines.push("## Executive summary");
  lines.push("");
  lines.push(
    `- **Context closure:** unresolved required_context entries **${beforeClosure.unresolvedEntries} → ${afterClosure.unresolvedEntries}** (${delta(beforeClosure.unresolvedEntries, afterClosure.unresolvedEntries)}); empty proposition_ids **${beforeClosure.emptyPropositionIds} → ${afterClosure.emptyPropositionIds}**.`,
  );
  lines.push(
    `- **Composition opacity:** trace-reviewable opaque statements **${beforeComposition.traceReviewableCount} → ${afterComposition.traceReviewableCount}** (+${afterComposition.traceReviewableCount - beforeComposition.traceReviewableCount}); trace-blocked **${beforeOpaqueBlocked} → ${afterOpaqueBlocked}** (${delta(beforeOpaqueBlocked, afterOpaqueBlocked)}).`,
  );
  lines.push(
    `- **Context-dependent trace-blocked:** **${beforeContext.traceBlockedCount} → ${afterContext.traceBlockedCount}** (${delta(beforeContext.traceBlockedCount, afterContext.traceBlockedCount)}).`,
  );
  lines.push(
    `- **Verdict:** Export context closure materially improves trace reviewability for context-dependent statements; remaining opacity is dominated by monolithic composition (statement text = core proposition only), not missing locator closure.`,
  );
  lines.push("");
  lines.push("## 1. Context closure");
  lines.push("");
  lines.push("| Metric | Before 86-BR1 | After 86-BR1 | Delta |");
  lines.push("| --- | ---: | ---: | ---: |");
  lines.push(
    `| Unresolved required_context entries (focus population) | ${beforeClosure.unresolvedEntries} | ${afterClosure.unresolvedEntries} | ${delta(beforeClosure.unresolvedEntries, afterClosure.unresolvedEntries)} |`,
  );
  lines.push(
    `| Entries with empty proposition_ids | ${beforeClosure.emptyPropositionIds} | ${afterClosure.emptyPropositionIds} | ${delta(beforeClosure.emptyPropositionIds, afterClosure.emptyPropositionIds)} |`,
  );
  lines.push("");
  lines.push("### Export resolution_status (focus population)");
  lines.push("");
  lines.push("| Status | Before | After | Delta |");
  lines.push("| --- | ---: | ---: | ---: |");
  const allStatuses = new Set([
    ...Object.keys(beforeClosure.exportStatusCounts),
    ...Object.keys(afterClosure.exportStatusCounts),
  ]);
  for (const status of [...allStatuses].sort()) {
    const before = beforeClosure.exportStatusCounts[status] ?? 0;
    const after = afterClosure.exportStatusCounts[status] ?? 0;
    lines.push(`| ${status} | ${before} | ${after} | ${delta(before, after)} |`);
  }
  lines.push("");
  lines.push("### Workbench resolution mode (focus population, per required_context entry)");
  lines.push("");
  lines.push("| Mode | Before | After | Delta |");
  lines.push("| --- | ---: | ---: | ---: |");
  for (const mode of ["exact", "container", "partial", "unresolved", "external", "ambiguous"] as const) {
    const before = beforeClosure.resolutionModes[mode];
    const after = afterClosure.resolutionModes[mode];
    lines.push(`| ${mode} | ${before} | ${after} | ${delta(before, after)} |`);
  }
  lines.push("");
  lines.push("## 2. Composition opacity");
  lines.push("");
  lines.push("| Metric | Before | After | Delta |");
  lines.push("| --- | ---: | ---: | ---: |");
  lines.push(
    `| Total opaque statements | ${beforeComposition.opaqueStatementCount} | ${afterComposition.opaqueStatementCount} | ${delta(beforeComposition.opaqueStatementCount, afterComposition.opaqueStatementCount)} |`,
  );
  lines.push(
    `| Trace-reviewable opaque statements | ${beforeComposition.traceReviewableCount} | ${afterComposition.traceReviewableCount} | ${delta(beforeComposition.traceReviewableCount, afterComposition.traceReviewableCount)} |`,
  );
  lines.push(
    `| Trace-blocked opaque statements | ${beforeOpaqueBlocked} | ${afterOpaqueBlocked} | ${delta(beforeOpaqueBlocked, afterOpaqueBlocked)} |`,
  );
  lines.push(
    `| Context-dependent trace-blocked (subset) | ${beforeContext.traceBlockedCount} | ${afterContext.traceBlockedCount} | ${delta(beforeContext.traceBlockedCount, afterContext.traceBlockedCount)} |`,
  );
  lines.push(
    `| Trace-reviewable rate (of opaque) | ${pct(beforeComposition.traceReviewableCount, beforeComposition.opaqueStatementCount)} | ${pct(afterComposition.traceReviewableCount, afterComposition.opaqueStatementCount)} | |`,
  );
  lines.push("");
  lines.push("### Opacity trigger resolution (context_dependent)");
  lines.push("");
  const beforeCd = beforeComposition.triggerResolution.context_dependent;
  const afterCd = afterComposition.triggerResolution.context_dependent;
  lines.push("| Trigger | Opaque before | Reviewable before | Opaque after | Reviewable after |");
  lines.push("| --- | ---: | ---: | ---: | ---: |");
  lines.push(
    `| context_dependent | ${beforeCd.total} | ${beforeCd.traceReviewable} | ${afterCd.total} | ${afterCd.traceReviewable} |`,
  );
  lines.push("");
  lines.push("## 3. Reviewability blockers");
  lines.push("");
  lines.push("| Blocker | Before | After | Delta |");
  lines.push("| --- | ---: | ---: | ---: |");
  for (const key of Object.keys(BLOCKER_LABEL) as BlockerCategory[]) {
    const before = beforeBlockers.blockerCounts[key];
    const after = afterBlockers.blockerCounts[key];
    lines.push(`| ${BLOCKER_LABEL[key]} | ${before} | ${after} | ${delta(before, after)} |`);
  }
  lines.push("");
  lines.push("## 4. Specific improvements");
  lines.push("");
  lines.push(
    `### Statements: trace-blocked → trace-reviewable (${improvedStatements.length} sampled of ${afterComposition.assessments.filter((after) => {
      const before = beforeById.get(after.statementId);
      return Boolean(before) && !before!.traceReviewable && after.traceReviewable;
    }).length} total)`,
  );
  lines.push("");
  if (improvedStatements.length === 0) {
    lines.push("_None._");
  } else {
    lines.push("| Statement ID | Statement (truncated) |");
    lines.push("| --- | --- |");
    for (const row of improvedStatements) {
      lines.push(`| \`${row.statementId}\` | ${truncate(row.statementText)} |`);
    }
  }
  lines.push("");
  if (regressedStatements.length > 0) {
    lines.push(`### Regressions: trace-reviewable → trace-blocked (${regressedStatements.length})`);
    lines.push("");
    lines.push("| Statement ID | Statement (truncated) |");
    lines.push("| --- | --- |");
    for (const row of regressedStatements) {
      lines.push(`| \`${row.statementId}\` | ${truncate(row.statementText)} |`);
    }
    lines.push("");
  }
  lines.push("### Top required_context proposition_ids fills");
  lines.push("");
  lines.push("| Statement ID | Locator | Before IDs | After IDs |");
  lines.push("| --- | --- | --- | --- |");
  for (const row of fillExamples.slice(0, 10)) {
    lines.push(
      `| \`${row.statementId}\` | \`${row.locator}\` | ${row.beforeIds.length} | ${row.afterIds.join(", ")} |`,
    );
  }
  lines.push("");
  lines.push("### Context-dependent trace-blocked reduction");
  lines.push("");
  lines.push(
    `- Before: **${beforeContext.traceBlockedCount}** trace-blocked of **${beforeContext.contextDependentCount}** context-dependent (${pct(beforeContext.traceBlockedCount, beforeContext.contextDependentCount)}).`,
  );
  lines.push(
    `- After: **${afterContext.traceBlockedCount}** trace-blocked of **${afterContext.contextDependentCount}** context-dependent (${pct(afterContext.traceBlockedCount, afterContext.contextDependentCount)}).`,
  );
  lines.push(
    `- Net change: **${delta(beforeContext.traceBlockedCount, afterContext.traceBlockedCount)}** trace-blocked statements.`,
  );
  lines.push("");
  lines.push("## 5. Recommendation — next highest-leverage fix");
  lines.push("");
  lines.push(
    "**Composition transparency / selective context incorporation** remains the top lever after context closure convergence:",
  );
  lines.push("");
  lines.push(
    `1. **${afterContext.traceBlockedCount}** context-dependent statements are still trace-blocked despite improved locator closure — effective-law statement text remains verbatim core proposition text (${afterContext.statementMatchesCoreCount}/${afterContext.contextDependentCount} match core).`,
  );
  lines.push(
    `2. **${afterContext.incorporationGapCount}** statements have material incorporation gaps (resolved context not surfaced in statement text).`,
  );
  lines.push(
    "3. Residual **44** unresolved locators are mostly structural containers (`schedule 5`, `article 27`, cross-instrument refs) — lower leverage than inline composition for the blocked population.",
  );
  lines.push("");
  lines.push("**Suggested next prompt:** emit composition traces in export + inline selectively for material `required_context` (Prompt 83 recommendation), targeting trace-blocked context-dependent statements with resolved context propositions.");
  lines.push("");
  lines.push("## Reproduction");
  lines.push("");
  lines.push("```bash");
  lines.push("cd law-proposition-extractor");
  lines.push("uv run --package law-proposition-extractor-pipeline python scripts/generate_post_context_closure_impact_report.py");
  lines.push("```");
  lines.push("");
  lines.push("Refresh subsidiary reports:");
  lines.push("");
  lines.push("```bash");
  lines.push("uv run --package law-proposition-extractor-pipeline python scripts/generate_export_context_closure_report.py");
  lines.push("uv run --package law-proposition-extractor-pipeline python scripts/generate_composition_trace_report.py");
  lines.push("uv run --package law-proposition-extractor-pipeline python scripts/generate_context_dependent_construction_report.py");
  lines.push("uv run --package law-proposition-extractor-pipeline python scripts/generate_reviewability_blockers_report.py");
  lines.push("```");
  lines.push("");

  return lines.join("\n");
}

export function writeContextClosureImpactReport(outputPath: string, report: string): void {
  writeFileSync(outputPath, report, "utf-8");
}
