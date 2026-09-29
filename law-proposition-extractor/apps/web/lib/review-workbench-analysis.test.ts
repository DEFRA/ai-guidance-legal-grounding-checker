import { describe, expect, it } from "vitest";

import {
  buildReviewAnalysis,
  buildReviewAnalysisEnrichment,
  inferPropositionMatcherCandidateProxy,
  parseQueueManifest,
  parseReviewExport,
} from "@/lib/review-workbench-analysis";
import type { ReviewQueueManifest } from "@/lib/review-workbench-queue";
import type { WorkbenchReviewExport } from "@/lib/review-workbench-state";

function exportFixture(overrides?: Partial<WorkbenchReviewExport>): WorkbenchReviewExport {
  return {
    schema_version: "3",
    exported_at: "2026-06-10T12:00:00.000Z",
    run_id: "run-1",
    filter_statement_ids: ["s1", "s2", "s3"],
    summary: {
      total_in_filter: 3,
      reviewed: 2,
      complete: 1,
      draft: 1,
      unreviewed: 1,
      draft_in_export: 1,
      verdict_counts: {},
      failure_stage_counts: {},
      severity_counts: {},
    },
    reviews: [
      {
        statement_id: "s1",
        verdicts: ["accurate"],
        fragment_missing_proposition: {},
        fragment_coverage_gap: {},
        proposition_issues: {},
        context_assessments: {},
        failure_stages: [],
        severity: "",
        free_text_notes: "",
        updated_at: "2026-06-10T12:00:00.000Z",
        completed_at: "2026-06-10T12:00:00.000Z",
        review_status: "complete_review",
        review_status_reasons: [],
      },
      {
        statement_id: "s2",
        verdicts: ["incomplete", "missing_propositions"],
        fragment_missing_proposition: { f1: true },
        fragment_coverage_gap: {},
        proposition_issues: {},
        context_assessments: {},
        failure_stages: ["proposition_extraction", "composition"],
        severity: "critical",
        free_text_notes: "gap",
        updated_at: "2026-06-10T12:00:00.000Z",
        completed_at: "",
        review_status: "complete_review",
        review_status_reasons: [],
      },
      {
        statement_id: "s3",
        verdicts: ["overreaching"],
        fragment_missing_proposition: {},
        fragment_coverage_gap: {},
        proposition_issues: { p1: ["wrong_extraction"] },
        context_assessments: {},
        failure_stages: ["beatrice_suitability"],
        severity: "minor",
        free_text_notes: "",
        updated_at: "2026-06-10T12:00:00.000Z",
        completed_at: "",
        review_status: "draft_review",
        review_status_reasons: ["needs more"],
      },
    ],
    ...overrides,
  };
}

function queueFixture(): ReviewQueueManifest {
  return {
    schema_version: "1",
    exported_at: "2026-06-10T12:00:00.000Z",
    run_id: "run-1",
    preset: "stratified_sample",
    seed: "seed",
    sample_size: 2,
    filter_statement_ids: ["s1", "s2"],
    items: [
      {
        statement_id: "s1",
        sample_reason: "stratified",
        sample_bucket: "complete|1|proposition-matcher:yes|unresolved:no|instrument:eu-reg-1",
        priority_score: 1,
        already_reviewed: true,
      },
      {
        statement_id: "s2",
        sample_reason: "stratified",
        sample_bucket: "incomplete|2-3|proposition-matcher:no|unresolved:yes|instrument:uk-act-2",
        priority_score: 8,
        already_reviewed: true,
      },
    ],
    summary: { total: 2, reviewed: 2, unreviewed: 0 },
  };
}

describe("review-workbench-analysis", () => {
  it("parses review export v3", () => {
    const parsed = parseReviewExport(exportFixture());
    expect(parsed.run_id).toBe("run-1");
    expect(parsed.reviews).toHaveLength(3);
  });

  it("rejects unsupported review export schema", () => {
    expect(() => parseReviewExport({ schema_version: "2", reviews: [] })).toThrow(/schema_version/);
  });

  it("parses queue manifest v1", () => {
    const parsed = parseQueueManifest(queueFixture());
    expect(parsed.items).toHaveLength(2);
  });

  it("infers proposition-matcher proxy from verdicts", () => {
    expect(
      inferPropositionMatcherCandidateProxy({
        verdicts: ["accurate"],
        severity: "",
        failure_stages: [],
        review_status: "complete_review",
      }),
    ).toBe("pass");
    expect(
      inferPropositionMatcherCandidateProxy({
        verdicts: ["incomplete"],
        severity: "minor",
        failure_stages: [],
        review_status: "complete_review",
      }),
    ).toBe("concern");
    expect(
      inferPropositionMatcherCandidateProxy({
        verdicts: ["overreaching"],
        severity: "minor",
        failure_stages: [],
        review_status: "complete_review",
      }),
    ).toBe("fail");
  });

  it("filters to complete reviews only by default", () => {
    const analysis = buildReviewAnalysis(exportFixture(), {
      enrichment: buildReviewAnalysisEnrichment({
        propositionMatcherCandidateIds: new Set(["s1"]),
      }),
    });
    expect(analysis.summary.reviewed).toBe(2);
    expect(analysis.summary.draft).toBe(0);
    expect(analysis.overreaching_cases).toHaveLength(0);
  });

  it("includes drafts when requested", () => {
    const analysis = buildReviewAnalysis(exportFixture(), {
      filters: { includeDrafts: true },
    });
    expect(analysis.summary.draft).toBe(1);
    expect(analysis.overreaching_cases).toHaveLength(1);
  });

  it("restricts to queue only and enriches buckets from manifest", () => {
    const manifest = queueFixture();
    const analysis = buildReviewAnalysis(exportFixture(), {
      queueManifest: manifest,
      enrichment: buildReviewAnalysisEnrichment({
        queueManifest: manifest,
        propositionMatcherCandidateIds: new Set(["s1"]),
      }),
      filters: { queueOnly: true, exportReviewsOnly: false },
    });
    expect(analysis.summary.scope_total).toBe(2);
    expect(analysis.summary.rates_by_sample_bucket.some((row) => row.bucket.includes("eu-reg-1"))).toBe(
      true,
    );
    expect(analysis.worst_instruments[0]?.instrument).toBe("uk-act-2");
  });

  it("builds special-case tables", () => {
    const analysis = buildReviewAnalysis(exportFixture());
    expect(analysis.incomplete_missing_propositions_cases.map((row) => row.statement_id)).toEqual([
      "s2",
    ]);
    expect(analysis.failure_stage_combinations[0]?.combination).toBe(
      "composition + proposition_extraction",
    );
  });
});
