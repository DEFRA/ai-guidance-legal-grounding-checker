import { describe, expect, it } from "vitest";

import {
  assessReviewCompleteness,
  buildFilterReviewSummary,
  buildWorkbenchReviewExport,
  emptyWorkbenchReview,
  enrichReviewForExport,
  hasWorkbenchReviewInput,
} from "@/lib/review-workbench-state";

describe("review-workbench-state", () => {
  it("defaults empty review", () => {
    const review = emptyWorkbenchReview();
    expect(review.verdicts).toEqual([]);
    expect(review.fragment_missing_proposition).toEqual({});
    expect(review.fragment_coverage_gap).toEqual({});
    expect(review.proposition_issues).toEqual({});
    expect(review.context_assessments).toEqual({});
    expect(review.failure_stages).toEqual([]);
    expect(review.severity).toBe("");
    expect(assessReviewCompleteness(review).status).toBe("unreviewed");
  });

  it("detects reviewer input from verdicts and annotations", () => {
    expect(hasWorkbenchReviewInput(emptyWorkbenchReview())).toBe(false);
    expect(
      hasWorkbenchReviewInput({
        ...emptyWorkbenchReview(),
        verdicts: ["accurate"],
      }),
    ).toBe(true);
    expect(
      hasWorkbenchReviewInput({
        ...emptyWorkbenchReview(),
        fragment_missing_proposition: { "law-fragment-0": true },
      }),
    ).toBe(true);
    expect(
      hasWorkbenchReviewInput({
        ...emptyWorkbenchReview(),
        fragment_coverage_gap: { "law-fragment-0": true },
      }),
    ).toBe(true);
  });

  it("marks accurate-only review complete without severity", () => {
    const review = {
      ...emptyWorkbenchReview(),
      verdicts: ["accurate" as const],
    };
    expect(assessReviewCompleteness(review)).toEqual({
      status: "complete_review",
      reasons: [],
    });
  });

  it("requires severity when verdict is not only accurate", () => {
    const review = {
      ...emptyWorkbenchReview(),
      verdicts: ["incomplete" as const],
      fragment_coverage_gap: { f1: true },
    };
    expect(assessReviewCompleteness(review).status).toBe("draft_review");
    expect(assessReviewCompleteness(review).reasons).toContain(
      "Select a severity (not required when verdict is only accurate).",
    );
  });

  it("requires evidence for issue verdicts", () => {
    const incomplete = {
      ...emptyWorkbenchReview(),
      verdicts: ["incomplete" as const],
      severity: "minor" as const,
    };
    expect(assessReviewCompleteness(incomplete).reasons).toContain(
      "Incomplete verdict needs a missing-source mark, coverage gap mark, or notes.",
    );

    const overreaching = {
      ...emptyWorkbenchReview(),
      verdicts: ["overreaching" as const],
      severity: "minor" as const,
    };
    expect(assessReviewCompleteness(overreaching).reasons[0]).toMatch(/Overreaching verdict/);

    const badMerge = {
      ...emptyWorkbenchReview(),
      verdicts: ["bad_merge" as const],
      severity: "minor" as const,
    };
    expect(assessReviewCompleteness(badMerge).reasons[0]).toMatch(/Bad merge verdict/);

    const missingProps = {
      ...emptyWorkbenchReview(),
      verdicts: ["missing_propositions" as const],
      severity: "minor" as const,
    };
    expect(assessReviewCompleteness(missingProps).reasons[0]).toMatch(/Missing propositions verdict/);
  });

  it("accepts notes as evidence for issue verdicts", () => {
    const review = {
      ...emptyWorkbenchReview(),
      verdicts: ["incomplete" as const, "overreaching" as const, "bad_merge" as const],
      severity: "significant" as const,
      free_text_notes: "see notes",
    };
    expect(assessReviewCompleteness(review).status).toBe("complete_review");
  });

  it("builds export rows with review status metadata", () => {
    const row = enrichReviewForExport("stmt-1", {
      ...emptyWorkbenchReview(),
      verdicts: ["accurate"],
      updated_at: "2026-01-01T00:00:00.000Z",
      completed_at: "2026-01-01T00:00:00.000Z",
    });
    expect(row.review_status).toBe("complete_review");
    expect(row.review_status_reasons).toEqual([]);
    expect(row.statement_id).toBe("stmt-1");
  });

  it("exports context assessment flags as v3 extension fields", () => {
    const row = enrichReviewForExport("stmt-ctx", {
      ...emptyWorkbenchReview(),
      verdicts: ["accurate"],
      context_assessments: {
        "Reg 2(3)": {
          only_for_assessment: true,
          confirms_statement: true,
        },
      },
      updated_at: "2026-01-01T00:00:00.000Z",
      completed_at: "2026-01-01T00:00:00.000Z",
    });
    expect(row.context_assessments).toEqual({
      "Reg 2(3)": {
        only_for_assessment: true,
        confirms_statement: true,
      },
    });
    expect(hasWorkbenchReviewInput(row)).toBe(true);
  });

  it("builds filter summary and marks draft exports", () => {
    const reviews = {
      "stmt-complete": {
        ...emptyWorkbenchReview(),
        verdicts: ["accurate" as const],
      },
      "stmt-draft": {
        ...emptyWorkbenchReview(),
        verdicts: ["incomplete" as const],
        severity: "minor" as const,
      },
    };
    const summary = buildFilterReviewSummary(["stmt-complete", "stmt-draft", "stmt-open"], reviews);
    expect(summary.total_in_filter).toBe(3);
    expect(summary.complete).toBe(1);
    expect(summary.draft).toBe(1);
    expect(summary.unreviewed).toBe(1);
    expect(summary.reviewed).toBe(2);

    const payload = buildWorkbenchReviewExport("run-1", reviews, [
      "stmt-complete",
      "stmt-draft",
      "stmt-open",
    ]);
    expect(payload.summary.draft_in_export).toBe(1);
    expect(payload.reviews.find((row) => row.statement_id === "stmt-draft")?.review_status).toBe(
      "draft_review",
    );
  });
});
