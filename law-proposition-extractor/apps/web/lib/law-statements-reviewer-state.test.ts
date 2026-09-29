import { describe, expect, it } from "vitest";

import {
  emptyReviewerAssessment,
  hasReviewerInput,
} from "@/lib/law-statements-reviewer-state";

describe("law-statements-reviewer-state", () => {
  it("defaults mode-specific fields in empty assessment", () => {
    const assessment = emptyReviewerAssessment();
    expect(assessment.review_mode).toBe("evidence");
    expect(assessment.coverage_missing_from_statement).toEqual({});
    expect(assessment.composition_issues).toEqual([]);
    expect(assessment.wrong_proposition_ids).toEqual([]);
  });

  it("detects mode-specific reviewer input", () => {
    expect(hasReviewerInput(emptyReviewerAssessment())).toBe(false);
    expect(
      hasReviewerInput({
        ...emptyReviewerAssessment(),
        coverage_missing_from_statement: { "coverage:conditions_preserved": "yes" },
      }),
    ).toBe(true);
    expect(
      hasReviewerInput({
        ...emptyReviewerAssessment(),
        composition_issues: ["should_split"],
      }),
    ).toBe(true);
  });
});
