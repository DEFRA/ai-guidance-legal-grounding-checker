export type ReviewerRating = "" | "pass" | "concern" | "fail";

export type InspectorReviewMode = "evidence" | "coverage" | "composition";

export type MissingFromStatementAnswer = "" | "yes" | "no" | "unsure";

export type CompositionReviewIssue =
  | "good_merge"
  | "should_split"
  | "duplicate_redundant"
  | "wrong_proposition_included"
  | "missing_proposition_needed";

export type StatementReviewerAssessment = {
  accuracy: ReviewerRating;
  completeness: ReviewerRating;
  overreach: ReviewerRating;
  composition_quality: ReviewerRating;
  beatrice_suitability: ReviewerRating;
  free_text_notes: string;
  recipe_row_notes: Record<string, string>;
  review_mode: InspectorReviewMode;
  coverage_missing_from_statement: Record<string, MissingFromStatementAnswer>;
  composition_issues: CompositionReviewIssue[];
  wrong_proposition_ids: string[];
  missing_proposition_note: string;
  updated_at: string;
};

export type ReviewerAssessmentExport = {
  schema_version: "2";
  exported_at: string;
  run_id: string;
  assessments: Array<
    StatementReviewerAssessment & {
      statement_id: string;
    }
  >;
};

const STORAGE_KEY = "law-proposition-extractor.law-statement-reviews.v1";

export const REVIEWER_RATING_OPTIONS: ReadonlyArray<{ value: ReviewerRating; label: string }> = [
  { value: "", label: "Unreviewed" },
  { value: "pass", label: "Pass" },
  { value: "concern", label: "Concern" },
  { value: "fail", label: "Fail" },
];

export const INSPECTOR_REVIEW_MODES: ReadonlyArray<{
  value: InspectorReviewMode;
  label: string;
}> = [
  { value: "evidence", label: "Evidence" },
  { value: "coverage", label: "Coverage" },
  { value: "composition", label: "Composition" },
];

export const MISSING_FROM_STATEMENT_OPTIONS: ReadonlyArray<{
  value: MissingFromStatementAnswer;
  label: string;
}> = [
  { value: "", label: "Unreviewed" },
  { value: "yes", label: "Yes — missing from statement" },
  { value: "no", label: "No — present or not needed" },
  { value: "unsure", label: "Unsure" },
];

export const COMPOSITION_REVIEW_ISSUE_OPTIONS: ReadonlyArray<{
  value: CompositionReviewIssue;
  label: string;
}> = [
  { value: "good_merge", label: "Good merge" },
  { value: "should_split", label: "Should split" },
  { value: "duplicate_redundant", label: "Duplicate / redundant" },
  { value: "wrong_proposition_included", label: "Wrong proposition included" },
  { value: "missing_proposition_needed", label: "Missing proposition needed" },
];

export function emptyReviewerAssessment(): StatementReviewerAssessment {
  return {
    accuracy: "",
    completeness: "",
    overreach: "",
    composition_quality: "",
    beatrice_suitability: "",
    free_text_notes: "",
    recipe_row_notes: {},
    review_mode: "evidence",
    coverage_missing_from_statement: {},
    composition_issues: [],
    wrong_proposition_ids: [],
    missing_proposition_note: "",
    updated_at: "",
  };
}

function normalizeStoredAssessment(
  assessment: Partial<StatementReviewerAssessment>,
): StatementReviewerAssessment {
  const base = emptyReviewerAssessment();
  return {
    ...base,
    ...assessment,
    recipe_row_notes: assessment.recipe_row_notes ?? {},
    coverage_missing_from_statement: assessment.coverage_missing_from_statement ?? {},
    composition_issues: Array.isArray(assessment.composition_issues)
      ? assessment.composition_issues
      : [],
    wrong_proposition_ids: Array.isArray(assessment.wrong_proposition_ids)
      ? assessment.wrong_proposition_ids
      : [],
    missing_proposition_note: assessment.missing_proposition_note ?? "",
    review_mode: assessment.review_mode ?? "evidence",
  };
}

type StoredReviewState = Record<string, Record<string, StatementReviewerAssessment>>;

function readStorage(): StoredReviewState {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as StoredReviewState;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeStorage(state: StoredReviewState): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* ignore quota errors */
  }
}

export function loadReviewerAssessment(
  runId: string,
  statementId: string,
): StatementReviewerAssessment {
  const stored = readStorage();
  const raw = stored[runId]?.[statementId];
  return raw ? normalizeStoredAssessment(raw) : emptyReviewerAssessment();
}

export function saveReviewerAssessment(
  runId: string,
  statementId: string,
  assessment: StatementReviewerAssessment,
): void {
  const stored = readStorage();
  const runBucket = stored[runId] ?? {};
  runBucket[statementId] = {
    ...assessment,
    updated_at: new Date().toISOString(),
  };
  stored[runId] = runBucket;
  writeStorage(stored);
}

export function loadRunReviewerAssessments(
  runId: string,
): Record<string, StatementReviewerAssessment> {
  const stored = readStorage();
  return stored[runId] ?? {};
}

export function buildReviewerAssessmentExport(
  runId: string,
  assessments: Record<string, StatementReviewerAssessment>,
): ReviewerAssessmentExport {
  return {
    schema_version: "2",
    exported_at: new Date().toISOString(),
    run_id: runId,
    assessments: Object.entries(assessments)
      .filter(([, assessment]) => hasReviewerInput(assessment))
      .map(([statementId, assessment]) => ({
        statement_id: statementId,
        ...assessment,
      }))
      .sort((left, right) => left.statement_id.localeCompare(right.statement_id)),
  };
}

export function hasReviewerInput(assessment: StatementReviewerAssessment): boolean {
  return (
    assessment.accuracy !== "" ||
    assessment.completeness !== "" ||
    assessment.overreach !== "" ||
    assessment.composition_quality !== "" ||
    assessment.beatrice_suitability !== "" ||
    assessment.free_text_notes.trim().length > 0 ||
    Object.values(assessment.recipe_row_notes).some((note) => note.trim().length > 0) ||
    Object.values(assessment.coverage_missing_from_statement).some((answer) => answer !== "") ||
    assessment.composition_issues.length > 0 ||
    assessment.wrong_proposition_ids.length > 0 ||
    assessment.missing_proposition_note.trim().length > 0
  );
}

export function downloadReviewerAssessmentExport(payload: ReviewerAssessmentExport): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `law-statement-reviews-${payload.run_id}-${payload.exported_at.slice(0, 10)}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}
