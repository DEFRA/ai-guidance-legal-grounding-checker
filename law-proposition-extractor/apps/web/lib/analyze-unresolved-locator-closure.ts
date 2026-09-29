import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { assessCompositionTrace } from "@/lib/analyze-composition-traces";
import {
  buildContextRequirementResolutions,
  buildLocatorResolutionReport,
  locatorMatchesTarget,
  normalizeCrossReferenceLocator,
  parseColonLocatorSegments,
  parseLocatorReference,
  parseLocatorStructuralContext,
  primarySourceRecordIdForStatement,
} from "@/lib/context-locator-resolution";
import {
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

export type UnresolvedLocatorCause =
  | "parser_miss"
  | "fragment_missing"
  | "proposition_missing"
  | "external_reference"
  | "generic_broad"
  | "ambiguous"
  | "noisy_required_context"
  | "other";

export type UnresolvedLocatorEntry = {
  statementId: string;
  standaloneStatus: string;
  traceBlocked: boolean;
  contextDependent: boolean;
  locator: string;
  kind: string;
  exportResolutionStatus: string;
  exportPropositionIds: string[];
  cause: UnresolvedLocatorCause;
  sourceRecordId: string | null;
  sourceInstrument: string;
  parsedLocator: boolean;
  sourceFragmentExists: boolean;
  matchedFragmentIds: string[];
  propositionExistsForFragment: boolean;
  workbenchResolvable: boolean;
  workbenchReason: string | undefined;
  candidateFragmentCount: number;
};

export type UnresolvedLocatorAnalysis = {
  exportDir: string;
  contextDependentCount: number;
  traceBlockedCount: number;
  unresolvedLocatorTotal: number;
  causeCounts: Record<UnresolvedLocatorCause, number>;
  workbenchResolvableCount: number;
  exportResolvableCount: number;
  topLocators: Array<{ locator: string; count: number }>;
  topInstruments: Array<{ instrument: string; count: number }>;
  examplesByCause: Record<UnresolvedLocatorCause, UnresolvedLocatorEntry[]>;
  entries: UnresolvedLocatorEntry[];
};

const CAUSE_LABEL: Record<UnresolvedLocatorCause, string> = {
  parser_miss: "1. Internal locator parser miss",
  fragment_missing: "2. Internal locator exists but source fragment missing",
  proposition_missing: "3. Internal locator exists but no proposition extracted",
  external_reference: "4. External instrument reference",
  generic_broad: "5. Generic/broad reference",
  ambiguous: "6. Ambiguous reference",
  noisy_required_context: "7. Noisy/false required_context",
  other: "8. Other/unknown",
};

const GENERIC_BROAD_RE =
  /\b(this|these|that|those)\s+(schedule|regulation|regulations|part|article|paragraph|rule|rules|section|sections)\b|\bthe\s+(preceding|following|above|below)\b|\b(herein|hereunder|aforementioned)\b|^\s*(the\s+)?schedule\s*$/i;

const EXTERNAL_INSTRUMENT_RE =
  /\b(?:regulation|reg\.?|article|schedule|part)\s+\d+[a-z]?(?:\s*\([^)]+\))?\s+of\s+the\s+/i;

function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf-8")) as T;
}

function fragmentRowId(fragment: SourceFragmentRow): string {
  return String(fragment.id ?? fragment.fragment_id ?? "").trim();
}

function loadBundle(exportDir: string): ExportBundle {
  return {
    propositions: readJson(resolve(exportDir, "propositions.json")),
    source_fragments: readJson(resolve(exportDir, "source_fragments.json")),
    source_records: readJson(resolve(exportDir, "sources.json")),
    effective_law_statements: readJson(resolve(exportDir, "effective_law_statements.json")),
  };
}

function normalizeText(text: string): string {
  return text.trim().toLowerCase().replace(/\s+/g, " ");
}

function locatorReferencedInText(locator: string, text: string): boolean {
  const normalizedLocator = normalizeText(locator);
  if (!normalizedLocator) {
    return false;
  }
  return normalizeText(text).includes(normalizedLocator);
}

function isNoisyRequiredContext(input: {
  entry: NonNullable<LawStatementRow["required_context"]>[number];
  statementText: string;
}): boolean {
  const resolutionStatus = String(input.entry.resolution_status ?? "").trim();
  const propositionIds = (input.entry.proposition_ids ?? []).map((id) => String(id).trim()).filter(Boolean);
  if (propositionIds.length > 0) {
    return false;
  }
  if (resolutionStatus === "external_reference") {
    return true;
  }
  const locator = String(input.entry.locator ?? "").trim();
  if (locatorReferencedInText(locator, input.statementText)) {
    return false;
  }
  const kind = String(input.entry.kind ?? "").trim().toLowerCase();
  if (kind === "incorporated_rule" || kind === "host_rule" || kind === "incorporated_factors") {
    return false;
  }
  return true;
}

function matchFragmentsInSource(
  sourceRecordId: string,
  locator: string,
  sourceFragments: SourceFragmentRow[],
): SourceFragmentRow[] {
  const matches: SourceFragmentRow[] = [];
  const seen = new Set<string>();
  for (const fragment of sourceFragments) {
    if (String(fragment.source_record_id ?? "").trim() !== sourceRecordId) {
      continue;
    }
    const fragmentLocator = String(fragment.locator ?? "").trim();
    if (!fragmentLocator || !locatorMatchesTarget(fragmentLocator, locator)) {
      continue;
    }
    const id = fragmentRowId(fragment);
    if (!id || seen.has(id)) {
      continue;
    }
    seen.add(id);
    matches.push(fragment);
  }
  return matches;
}

function heuristicFragmentMatches(
  sourceRecordId: string,
  locator: string,
  sourceFragments: SourceFragmentRow[],
): SourceFragmentRow[] {
  const raw = String(locator ?? "").trim().toLowerCase();
  if (!raw || !sourceRecordId) {
    return [];
  }

  const tokens = new Set<string>();
  const colonSegments = parseColonLocatorSegments(raw);
  if (colonSegments) {
    for (const segment of colonSegments) {
      tokens.add(`${segment.kind}:${segment.num}`);
      tokens.add(segment.num);
    }
  }
  const structural = parseLocatorStructuralContext(raw);
  if (structural) {
    for (const segment of structural.segments) {
      tokens.add(`${segment.kind}:${segment.num}`);
      tokens.add(segment.num);
    }
  }
  const numbers = raw.match(/\d+[a-z]?/g) ?? [];
  for (const num of numbers) {
    tokens.add(num);
  }

  const matches: SourceFragmentRow[] = [];
  const seen = new Set<string>();
  for (const fragment of sourceFragments) {
    if (String(fragment.source_record_id ?? "").trim() !== sourceRecordId) {
      continue;
    }
    const fragmentLocator = String(fragment.locator ?? "").trim().toLowerCase();
    if (!fragmentLocator) {
      continue;
    }
    const hit = Array.from(tokens).some(
      (token) => token.length >= 2 && fragmentLocator.includes(token),
    );
    if (!hit) {
      continue;
    }
    const id = fragmentRowId(fragment);
    if (!id || seen.has(id)) {
      continue;
    }
    seen.add(id);
    matches.push(fragment);
  }
  return matches;
}

function propositionsForFragments(
  fragmentIds: string[],
  propositions: PropositionRow[],
): PropositionRow[] {
  const idSet = new Set(fragmentIds);
  return propositions.filter((prop) => {
    const fragmentId = String(prop.source_fragment_id ?? "").trim();
    return fragmentId && idSet.has(fragmentId);
  });
}

function sourceInstrumentLabel(
  sourceRecordId: string | null,
  sourceById: Map<string, SourceRow>,
): string {
  if (!sourceRecordId) {
    return "unknown";
  }
  const source = sourceById.get(sourceRecordId);
  const title = String(source?.title ?? source?.instrument_title ?? "").trim();
  if (title) {
    return title;
  }
  const citation = String(source?.citation ?? source?.instrument_citation ?? "").trim();
  if (citation) {
    return citation;
  }
  return sourceRecordId;
}

function isUnresolvedContextEntry(
  entry: NonNullable<LawStatementRow["required_context"]>[number],
): boolean {
  const propositionIds = (entry.proposition_ids ?? []).map((id) => String(id).trim()).filter(Boolean);
  const status = String(entry.resolution_status ?? "").trim();
  return propositionIds.length === 0 || status === "unresolved" || status === "ambiguous" || status === "missing";
}

function classifyCause(input: {
  entry: NonNullable<LawStatementRow["required_context"]>[number];
  statementText: string;
  sourceRecordId: string | null;
  sourceFragments: SourceFragmentRow[];
  propositions: PropositionRow[];
  workbenchReason: string | undefined;
  workbenchResolved: boolean;
  matchedFragmentIds: string[];
  candidateFragmentCount: number;
}): UnresolvedLocatorCause {
  const locator = String(input.entry.locator ?? "").trim();
  const status = String(input.entry.resolution_status ?? "").trim();
  const kind = String(input.entry.kind ?? "").trim().toLowerCase();

  if (status === "external_reference" || kind.startsWith("external_") || EXTERNAL_INSTRUMENT_RE.test(locator)) {
    return "external_reference";
  }
  if (GENERIC_BROAD_RE.test(locator)) {
    return "generic_broad";
  }
  if (isNoisyRequiredContext({ entry: input.entry, statementText: input.statementText })) {
    return "noisy_required_context";
  }
  if (status === "ambiguous" || input.workbenchReason === "ambiguous") {
    return "ambiguous";
  }

  const standardMatches =
    input.sourceRecordId && locator
      ? matchFragmentsInSource(input.sourceRecordId, locator, input.sourceFragments)
      : [];
  const fragmentIds = standardMatches.map((fragment) => fragmentRowId(fragment)).filter(Boolean);
  const propsOnFragments = propositionsForFragments(fragmentIds, input.propositions);

  if (fragmentIds.length > 0 && propsOnFragments.length === 0) {
    return "proposition_missing";
  }
  if (fragmentIds.length > 0 && propsOnFragments.length > 0) {
    if (fragmentIds.length > 1 || input.workbenchReason === "ambiguous") {
      return "ambiguous";
    }
    if (input.workbenchResolved) {
      // Material exists and workbench resolves; export `resolve_locator_in_source` failed to close.
      return "parser_miss";
    }
    return "ambiguous";
  }

  const parsed =
    parseLocatorReference(locator) !== null ||
    parseColonLocatorSegments(locator) !== null ||
    parseLocatorStructuralContext(locator) !== null;

  const heuristicMatches =
    input.sourceRecordId && locator
      ? heuristicFragmentMatches(input.sourceRecordId, locator, input.sourceFragments)
      : [];

  if (heuristicMatches.length > 0) {
    const heuristicIds = heuristicMatches.map((fragment) => fragmentRowId(fragment)).filter(Boolean);
    const heuristicProps = propositionsForFragments(heuristicIds, input.propositions);
    if (heuristicProps.length === 0) {
      return "proposition_missing";
    }
    return "parser_miss";
  }

  if (parsed || normalizeCrossReferenceLocator(locator)) {
    return "fragment_missing";
  }

  return "other";
}

function emptyCauseCounts(): Record<UnresolvedLocatorCause, number> {
  return {
    parser_miss: 0,
    fragment_missing: 0,
    proposition_missing: 0,
    external_reference: 0,
    generic_broad: 0,
    ambiguous: 0,
    noisy_required_context: 0,
    other: 0,
  };
}

export function analyzeUnresolvedLocatorClosure(exportDir: string): UnresolvedLocatorAnalysis {
  const bundle = loadBundle(exportDir);
  const propositionById = new Map(bundle.propositions.map((prop) => [prop.id, prop]));
  const fragmentById = new Map(
    bundle.source_fragments.map((fragment) => [fragmentRowId(fragment), fragment]),
  );
  const sourceById = new Map(bundle.source_records.map((source) => [String(source.id ?? ""), source]));

  const context: CompositionBuildContext = {
    propositionById,
    sourceById,
    fragmentById,
  };

  const entries: UnresolvedLocatorEntry[] = [];
  let contextDependentCount = 0;
  let traceBlockedCount = 0;

  for (const statement of bundle.effective_law_statements.statements ?? []) {
    const contextDependent = statement.standalone_status === "context_dependent";
    const trace = assessCompositionTrace(statement, context);
    const traceBlocked = !trace.traceReviewable;

    if (contextDependent) {
      contextDependentCount += 1;
    }
    if (traceBlocked) {
      traceBlockedCount += 1;
    }

    if (!contextDependent && !traceBlocked) {
      continue;
    }

    const sourceRecordId = primarySourceRecordIdForStatement(statement, propositionById);
    const resolutions = buildContextRequirementResolutions(statement, {
      sourceFragments: bundle.source_fragments,
      propositionById,
      fragmentById,
    });

    for (let index = 0; index < (statement.required_context ?? []).length; index += 1) {
      const entry = statement.required_context![index]!;
      if (!isUnresolvedContextEntry(entry)) {
        continue;
      }

      const locator = String(entry.locator ?? "").trim();
      const resolution = resolutions[index];
      const report = buildLocatorResolutionReport({
        locator,
        statement,
        sourceFragments: bundle.source_fragments,
        propositionById,
        fragmentById,
      });

      const matchedFragmentIds = report.outcome.matchedFragmentIds;
      const candidateFragmentCount = report.candidateFragmentLocators.length;
      const standardMatches =
        sourceRecordId && locator
          ? matchFragmentsInSource(sourceRecordId, locator, bundle.source_fragments)
          : [];
      const heuristicMatches =
        sourceRecordId && locator
          ? heuristicFragmentMatches(sourceRecordId, locator, bundle.source_fragments)
          : [];
      const fragmentIds = new Set([
        ...matchedFragmentIds,
        ...standardMatches.map((fragment) => fragmentRowId(fragment)),
        ...heuristicMatches.map((fragment) => fragmentRowId(fragment)),
      ]);
      const propsOnFragments = propositionsForFragments(Array.from(fragmentIds), bundle.propositions);

      const cause = classifyCause({
        entry,
        statementText: statement.statement_text,
        sourceRecordId,
        sourceFragments: bundle.source_fragments,
        propositions: bundle.propositions,
        workbenchReason: resolution?.reason,
        workbenchResolved: resolution?.resolved === true,
        matchedFragmentIds,
        candidateFragmentCount,
      });

      entries.push({
        statementId: statement.id,
        standaloneStatus: String(statement.standalone_status ?? ""),
        traceBlocked,
        contextDependent,
        locator,
        kind: String(entry.kind ?? ""),
        exportResolutionStatus: String(entry.resolution_status ?? ""),
        exportPropositionIds: (entry.proposition_ids ?? []).map((id) => String(id).trim()).filter(Boolean),
        cause,
        sourceRecordId,
        sourceInstrument: sourceInstrumentLabel(sourceRecordId, sourceById),
        parsedLocator: parseLocatorReference(locator) !== null,
        sourceFragmentExists: fragmentIds.size > 0,
        matchedFragmentIds: Array.from(fragmentIds),
        propositionExistsForFragment: propsOnFragments.length > 0,
        workbenchResolvable: resolution?.resolved === true,
        workbenchReason: resolution?.reason,
        candidateFragmentCount,
      });
    }
  }

  const causeCounts = emptyCauseCounts();
  const locatorCounts = new Map<string, number>();
  const instrumentCounts = new Map<string, number>();
  let workbenchResolvableCount = 0;
  let exportResolvableCount = 0;

  for (const row of entries) {
    causeCounts[row.cause] += 1;
    locatorCounts.set(row.locator, (locatorCounts.get(row.locator) ?? 0) + 1);
    instrumentCounts.set(row.sourceInstrument, (instrumentCounts.get(row.sourceInstrument) ?? 0) + 1);
    if (row.workbenchResolvable) {
      workbenchResolvableCount += 1;
    }
    if (row.exportPropositionIds.length > 0) {
      exportResolvableCount += 1;
    }
  }

  const topLocators = Array.from(locatorCounts.entries())
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, 30)
    .map(([locator, count]) => ({ locator, count }));

  const topInstruments = Array.from(instrumentCounts.entries())
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, 15)
    .map(([instrument, count]) => ({ instrument, count }));

  const examplesByCause = Object.fromEntries(
    (Object.keys(causeCounts) as UnresolvedLocatorCause[]).map((cause) => [
      cause,
      entries.filter((row) => row.cause === cause).slice(0, 5),
    ]),
  ) as Record<UnresolvedLocatorCause, UnresolvedLocatorEntry[]>;

  return {
    exportDir,
    contextDependentCount,
    traceBlockedCount,
    unresolvedLocatorTotal: entries.length,
    causeCounts,
    workbenchResolvableCount,
    exportResolvableCount,
    topLocators,
    topInstruments,
    examplesByCause,
    entries,
  };
}

function formatExample(entry: UnresolvedLocatorEntry): string[] {
  return [
    `- **Locator:** \`${entry.locator}\``,
    `  - Statement: \`${entry.statementId}\` (${entry.standaloneStatus}, trace-blocked: ${entry.traceBlocked ? "yes" : "no"})`,
    `  - Export status: \`${entry.exportResolutionStatus}\`; kind: \`${entry.kind}\``,
    `  - Source: ${entry.sourceInstrument}`,
    `  - Parsed: ${entry.parsedLocator ? "yes" : "no"}; fragment exists: ${entry.sourceFragmentExists ? "yes" : "no"}; proposition on fragment: ${entry.propositionExistsForFragment ? "yes" : "no"}`,
    `  - Workbench resolvable: ${entry.workbenchResolvable ? "yes" : "no"}${entry.workbenchReason ? ` (${entry.workbenchReason})` : ""}`,
    entry.matchedFragmentIds.length > 0
      ? `  - Matched fragments: ${entry.matchedFragmentIds.slice(0, 3).join(", ")}${entry.matchedFragmentIds.length > 3 ? "…" : ""}`
      : `  - Candidate fragment locators: ${entry.candidateFragmentCount}`,
  ];
}

export function buildUnresolvedLocatorClosureReport(analysis: UnresolvedLocatorAnalysis): string {
  const lines: string[] = [];
  const total = analysis.unresolvedLocatorTotal;
  const wbOnly = analysis.workbenchResolvableCount;
  const wbOnlyPct = total > 0 ? ((wbOnly / total) * 100).toFixed(1) : "0.0";

  lines.push("# Unresolved locator closure report");
  lines.push("");
  lines.push(`**Date:** ${new Date().toISOString().slice(0, 10)}`);
  lines.push("**Corpus:** Slurry GB principal-5 (regenerated export)");
  lines.push(`**Export:** \`${analysis.exportDir}\``);
  lines.push("");
  lines.push(
    "Deterministic analysis of **unresolved `required_context` locators** on `context_dependent` and trace-blocked statements. Classifies closure blockers without LLM inference.",
  );
  lines.push("");
  lines.push("## Executive summary");
  lines.push("");
  lines.push(`- **${total}** unresolved required-context locator entries in focus population.`);
  lines.push(`- **${analysis.contextDependentCount}** context-dependent statements; **${analysis.traceBlockedCount}** trace-blocked statements (non-exclusive).`);
  lines.push(
    `- **${wbOnly}** (${wbOnlyPct}%) are **Review Workbench–resolvable** despite empty export \`proposition_ids\` — export pipeline closure gap, not missing source material.`,
  );
  lines.push("");

  const rankedCauses = (Object.entries(analysis.causeCounts) as Array<[UnresolvedLocatorCause, number]>)
    .sort((left, right) => right[1] - left[1]);
  const topCause = rankedCauses[0];
  if (topCause) {
    lines.push(
      `- Top cause: **${CAUSE_LABEL[topCause[0]]}** (${topCause[1]} entries, ${total > 0 ? ((topCause[1] / total) * 100).toFixed(1) : "0.0"}%).`,
    );
  }
  lines.push("");

  lines.push("## 1. Methodology");
  lines.push("");
  lines.push("### Population");
  lines.push("");
  lines.push("- Statements with `standalone_status = context_dependent` **or** failing composition-trace reviewability gates.");
  lines.push("- `required_context` entries with empty/missing `proposition_ids` or `resolution_status` in `{unresolved, ambiguous, missing}`.");
  lines.push("");
  lines.push("### Cause taxonomy");
  lines.push("");
  for (const [cause, label] of Object.entries(CAUSE_LABEL) as Array<[UnresolvedLocatorCause, string]>) {
    lines.push(`- **${label}**`);
  }
  lines.push("");
  lines.push("### Diagnostics per entry");
  lines.push("");
  lines.push("- Export `resolution_status` and `proposition_ids`");
  lines.push("- `parseLocatorReference` / structural parse success");
  lines.push("- Source fragment match (`locatorMatchesTarget` + heuristic token overlap)");
  lines.push("- Proposition linked to matched fragment");
  lines.push("- Review Workbench `buildContextRequirementResolutions` outcome");
  lines.push("");
  lines.push(
    "Cause **1 (parser miss)** includes export-side `resolve_locator_in_source` failures where Review Workbench already resolves the same locator against existing fragments/propositions.",
  );
  lines.push("");
  lines.push("## 2. Totals");
  lines.push("");
  lines.push("| Metric | Count |");
  lines.push("| --- | ---: |");
  lines.push(`| Unresolved locator entries | ${total} |`);
  lines.push(`| Workbench-resolvable (export empty) | ${wbOnly} |`);
  lines.push(`| Export has proposition_ids (partial) | ${analysis.exportResolvableCount} |`);
  lines.push("");
  lines.push("### Counts by cause");
  lines.push("");
  lines.push("| Cause | Count | % |");
  lines.push("| --- | ---: | ---: |");
  for (const [cause, count] of rankedCauses) {
    const pct = total > 0 ? ((count / total) * 100).toFixed(1) : "0.0";
    lines.push(`| ${CAUSE_LABEL[cause]} | ${count} | ${pct} |`);
  }
  lines.push("");
  lines.push("## 3. Top 30 unresolved locator strings");
  lines.push("");
  lines.push("| Locator | Count |");
  lines.push("| --- | ---: |");
  for (const row of analysis.topLocators) {
    lines.push(`| \`${row.locator.replace(/\|/g, "\\|")}\` | ${row.count} |`);
  }
  lines.push("");
  lines.push("## 4. Top source instruments affected");
  lines.push("");
  lines.push("| Instrument | Unresolved entries |");
  lines.push("| --- | ---: |");
  for (const row of analysis.topInstruments) {
    lines.push(`| ${row.instrument.replace(/\|/g, "\\|")} | ${row.count} |`);
  }
  lines.push("");
  lines.push("## 5. Examples by cause");
  lines.push("");
  for (const [cause, label] of Object.entries(CAUSE_LABEL) as Array<[UnresolvedLocatorCause, string]>) {
    const examples = analysis.examplesByCause[cause];
    lines.push(`### ${label}`);
    lines.push("");
    if (examples.length === 0) {
      lines.push("_No examples._");
    } else {
      for (const example of examples) {
        lines.push(...formatExample(example));
        lines.push("");
      }
    }
  }
  lines.push("## 6. Workbench vs export closure gap");
  lines.push("");
  const wbGap = analysis.entries.filter((row) => row.workbenchResolvable && row.exportPropositionIds.length === 0);
  lines.push(`- **${wbGap.length}** entries resolve in Review Workbench but export leaves \`proposition_ids\` empty.`);
  if (wbGap.length > 0) {
    lines.push("- Sample locators:");
    const sampleLocators = Array.from(new Set(wbGap.map((row) => row.locator))).slice(0, 10);
    for (const locator of sampleLocators) {
      lines.push(`  - \`${locator}\``);
    }
  }
  lines.push("");
  lines.push("## 7. Recommendation");
  lines.push("");
  lines.push(recommendFix(analysis));
  lines.push("");
  lines.push("## 8. Reproduction");
  lines.push("");
  lines.push("- `uv run --package law-proposition-extractor-pipeline python scripts/generate_unresolved_locator_closure_report.py`");
  lines.push("");
  return lines.join("\n");
}

function recommendFix(analysis: UnresolvedLocatorAnalysis): string {
  const ranked = (Object.entries(analysis.causeCounts) as Array<[UnresolvedLocatorCause, number]>)
    .sort((left, right) => right[1] - left[1]);
  const [topCause, topCount] = ranked[0] ?? ["other", 0];
  const total = analysis.unresolvedLocatorTotal;
  const wbGap = analysis.workbenchResolvableCount;

  const leverage: Array<{ fix: string; score: number; rationale: string }> = [
    {
      fix: "Align export `resolve_locator_in_source` with Review Workbench locator resolution",
      score: wbGap,
      rationale: `${wbGap} entries already resolve in workbench but not in export.`,
    },
    {
      fix: "Better locator parser (extend `parseLocatorReference` / colon-path matching)",
      score: analysis.causeCounts.parser_miss,
      rationale: `${analysis.causeCounts.parser_miss} parser-miss cases with heuristic fragment matches.`,
    },
    {
      fix: "Proposition extraction for referenced fragments",
      score: analysis.causeCounts.proposition_missing,
      rationale: `${analysis.causeCounts.proposition_missing} locators hit fragments with zero extracted propositions.`,
    },
    {
      fix: "Better source fragmentation",
      score: analysis.causeCounts.fragment_missing,
      rationale: `${analysis.causeCounts.fragment_missing} parsed internal locators have no source fragment.`,
    },
    {
      fix: "Suppress noisy `required_context` generation",
      score: analysis.causeCounts.noisy_required_context,
      rationale: `${analysis.causeCounts.noisy_required_context} entries classified as false/noise context requirements.`,
    },
    {
      fix: "External reference handling (fetch / stub / reviewer deferral)",
      score: analysis.causeCounts.external_reference,
      rationale: `${analysis.causeCounts.external_reference} external instrument references.`,
    },
    {
      fix: "Generic/broad reference disambiguation",
      score: analysis.causeCounts.generic_broad,
      rationale: `${analysis.causeCounts.generic_broad} generic references need structural inheritance.`,
    },
    {
      fix: "Ambiguous reference tie-breaking",
      score: analysis.causeCounts.ambiguous,
      rationale: `${analysis.causeCounts.ambiguous} ambiguous multi-match locators.`,
    },
  ];

  leverage.sort((left, right) => right.score - left.score);
  const winner = leverage[0]!;
  const runnerUp = leverage[1];

  const lines: string[] = [];
  lines.push(
    `**Highest-leverage fix:** ${winner.fix} — ${winner.rationale}`,
  );
  if (runnerUp && runnerUp.score > 0) {
    lines.push("");
    lines.push(`**Secondary:** ${runnerUp.fix} — ${runnerUp.rationale}`);
  }
  lines.push("");
  lines.push(
    `Primary cause bucket: **${CAUSE_LABEL[topCause]}** (${topCount} / ${total}). Addressing this bucket plus the workbench/export alignment (${wbGap} entries) closes the majority of trace-reviewability blockers from unresolved context.`,
  );
  return lines.join("\n");
}

export function writeUnresolvedLocatorClosureReport(outputPath: string, report: string): void {
  writeFileSync(outputPath, report, "utf-8");
}
