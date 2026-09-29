import { describe, expect, it } from "vitest";

import {
  analyzeTraceBlockedHardCases,
  buildTraceBlockedHardCasesReport,
  writeTraceBlockedHardCasesReport,
} from "@/lib/analyze-trace-blocked-hard-cases-io";
import {
  assessTraceBlockedHardCase,
  hardCasePriorityScore,
  pickRepresentativeHardCaseSamples,
} from "@/lib/analyze-trace-blocked-hard-cases";
import { buildCompositionContext } from "@/lib/export-composition-trace";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";

function minimalContext(propositions: PropositionRow[] = []) {
  return buildCompositionContext({
    propositions,
    source_fragments: [],
    source_records: [],
    effective_law_statements: { statements: [] },
  });
}

describe("analyze-trace-blocked-hard-cases", () => {
  it("ranks reviewer_required ahead of should_inline", () => {
    const reviewerScore = hardCasePriorityScore({
      incorporationCounts: {
        reviewer_required: 1,
        should_split: 0,
        should_inline: 0,
        external_context: 0,
      },
      contextDependent: false,
      apparentOverreach: false,
      missingPropositions: false,
    });
    const inlineScore = hardCasePriorityScore({
      incorporationCounts: {
        reviewer_required: 0,
        should_split: 0,
        should_inline: 1,
        external_context: 0,
      },
      contextDependent: true,
      apparentOverreach: true,
      missingPropositions: true,
    });
    expect(reviewerScore).toBeGreaterThan(inlineScore);
  });

  it("returns null when composition trace is reviewable", () => {
    const statement: LawStatementRow = {
      id: "stmt-clean",
      statement_text: "Standalone obligation.",
      presentation_role: "guidance_matching_candidate",
      standalone_status: "standalone",
      confidence: "high",
      source_proposition_ids: ["prop-1"],
    };
    const context = buildCompositionContext({
      propositions: [
        {
          id: "prop-1",
          proposition_text: "Standalone obligation.",
          source_fragment_id: "frag-1",
          fragment_locator: "reg 1",
        },
      ],
      source_fragments: [
        {
          id: "frag-1",
          fragment_text: "Standalone obligation.",
          locator: "reg 1",
        },
      ],
      source_records: [],
      effective_law_statements: { statements: [statement] },
    });
    expect(
      assessTraceBlockedHardCase({
        statement,
        context,
        instrumentKeyByPropositionId: new Map([["prop-1", "instrument-a"]]),
      }),
    ).toBeNull();
  });

  it("picks up to 20 representative samples across buckets", () => {
    const assessments = Array.from({ length: 30 }, (_, index) => ({
      statementId: `stmt-${index}`,
      statementText: `text ${index}`,
      traceBlockReason: index % 2 === 0 ? "monolithic_composition" : "missing_proposition_mapping",
      traceBlockReasons: ["monolithic_composition"],
      incorporationCounts: {
        reviewer_required: index % 5 === 0 ? 1 : 0,
        should_split: 0,
        should_inline: index % 3 === 0 ? 1 : 0,
        external_context: 0,
      },
      unresolvedLocatorCount: 1,
      materialContextCount: 0,
      propositionCount: 2,
      sourceInstrument: "instrument-a",
      contextDependent: index % 4 === 0,
      apparentOverreach: false,
      missingPropositions: false,
      priorityScore: 100 - index,
    }));
    const samples = pickRepresentativeHardCaseSamples(assessments, 20);
    expect(samples).toHaveLength(20);
    expect(new Set(samples.map((row) => row.statementId)).size).toBe(20);
  });

  it("builds a trace-blocked hard cases report from the slurry export", () => {
    const exportDir = process.env.TRACE_BLOCKED_HARD_CASES_EXPORT_DIR;
    if (!exportDir) {
      return;
    }

    const analysis = analyzeTraceBlockedHardCases(exportDir);
    expect(analysis.hardCaseCount).toBeGreaterThan(0);
    expect(analysis.samples).toHaveLength(20);
    expect(Object.keys(analysis.traceBlockReasonCounts).length).toBeGreaterThan(0);

    const report = buildTraceBlockedHardCasesReport(analysis);
    expect(report).toContain("# Trace-blocked hard cases report");
    expect(report).toContain("## Count by trace_block_reason");
    expect(report).toContain("## Sample hard cases (20 representative)");

    const outputPath = process.env.TRACE_BLOCKED_HARD_CASES_REPORT_PATH;
    if (outputPath) {
      writeTraceBlockedHardCasesReport(outputPath, report);
    }
  });
});
