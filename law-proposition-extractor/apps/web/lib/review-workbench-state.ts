export type StatementVerdict =
  | "accurate"
  | "incomplete"
  | "overreaching"
  | "bad_merge"
  | "missing_propositions";

export type FailureStage =
  | "source_selection"
  | "proposition_extraction"
  | "proposition_normalisation"
  | "context_resolution"
  | "composition"
  | "statement_wording"
  | "beatrice_suitability";

export type ReviewSeverity = "" | "cosmetic" | "minor" | "significant" | "critical";

export type PropositionIssue = "wrong_extraction" | "should_not_exist" | "missing_extraction";

export type ContextAssessmentFlag =
  | "should_have_been_incorporated"
  | "only_for_assessment"
  | "changes_meaning_materially"
  | "confirms_statement";

export type ContextAssessmentFlags = Partial<Record<ContextAssessmentFlag, boolean>>;

export type ReviewStatus = "unreviewed" | "draft_review" | "complete_review";

export type WorkbenchReview = {
  verdicts: StatementVerdict[];
  fragment_missing_proposition: Record<string, boolean>;
  fragment_coverage_gap: Record<string, boolean>;
  proposition_issues: Record<string, PropositionIssue[]>;
  context_assessments: Record<string, ContextAssessmentFlags>;
  failure_stages: FailureStage[];
  severity: ReviewSeverity;
  free_text_notes: string;
  updated_at: string;
  completed_at: string;
};

export type ReviewCompletenessAssessment = {
  status: ReviewStatus;
  reasons: string[];
};

export type WorkbenchReviewExportRow = WorkbenchReview & {
  statement_id: string;
  review_status: ReviewStatus;
  review_status_reasons: string[];
};

export type WorkbenchExportSummary = {
  total_in_filter: number;
  reviewed: number;
  complete: number;
  draft: number;
  unreviewed: number;
  draft_in_export: number;
  verdict_counts: Partial<Record<StatementVerdict, number>>;
  failure_stage_counts: Partial<Record<FailureStage, number>>;
  severity_counts: Partial<Record<Exclude<ReviewSeverity, "">, number>>;
};

export type WorkbenchReviewExport = {
  schema_version: "3";
  exported_at: string;
  run_id: string;
  filter_statement_ids: string[];
  summary: WorkbenchExportSummary;
  reviews: WorkbenchReviewExportRow[];
};

const STORAGE_KEY = "law-proposition-extractor.review-workbench.v2";

export const COMPOSITION_RELATED_FAILURE_STAGES: ReadonlyArray<FailureStage> = [
  "composition",
  "proposition_normalisation",
  "context_resolution",
];

export const OVERREACHING_PROPOSITION_ISSUES: ReadonlyArray<PropositionIssue> = [
  "wrong_extraction",
  "should_not_exist",
];

export const STATEMENT_VERDICT_OPTIONS: ReadonlyArray<{ value: StatementVerdict; label: string }> =
  [
    { value: "accurate", label: "Accurate" },
    { value: "incomplete", label: "Incomplete" },
    { value: "overreaching", label: "Overreaching" },
    { value: "bad_merge", label: "Bad merge" },
    { value: "missing_propositions", label: "Missing propositions" },
  ];

export const FAILURE_STAGE_OPTIONS: ReadonlyArray<{ value: FailureStage; label: string }> = [
  { value: "source_selection", label: "Source selection" },
  { value: "proposition_extraction", label: "Proposition extraction" },
  { value: "proposition_normalisation", label: "Proposition normalisation" },
  { value: "context_resolution", label: "Context resolution" },
  { value: "composition", label: "Composition" },
  { value: "statement_wording", label: "Statement wording" },
  { value: "beatrice_suitability", label: "Proposition Matcher suitability" },
];

export const REVIEW_SEVERITY_OPTIONS: ReadonlyArray<{ value: ReviewSeverity; label: string }> = [
  { value: "", label: "Unset" },
  { value: "cosmetic", label: "Cosmetic" },
  { value: "minor", label: "Minor" },
  { value: "significant", label: "Significant" },
  { value: "critical", label: "Critical" },
];

export const PROPOSITION_ISSUE_OPTIONS: ReadonlyArray<{ value: PropositionIssue; label: string }> =
  [
    { value: "wrong_extraction", label: "Wrong extraction" },
    { value: "should_not_exist", label: "Should not exist" },
    { value: "missing_extraction", label: "Missing extraction" },
  ];

export const CONTEXT_ASSESSMENT_OPTIONS: ReadonlyArray<{
  value: ContextAssessmentFlag;
  label: string;
}> = [
  {
    value: "should_have_been_incorporated",
    label: "Context should have been incorporated into statement",
  },
  { value: "only_for_assessment", label: "Context only needed for assessment" },
  { value: "changes_meaning_materially", label: "Context changes meaning materially" },
  { value: "confirms_statement", label: "Context confirms statement" },
];

export function emptyWorkbenchReview(): WorkbenchReview {
  return {
    verdicts: [],
    fragment_missing_proposition: {},
    fragment_coverage_gap: {},
    proposition_issues: {},
    context_assessments: {},
    failure_stages: [],
    severity: "",
    free_text_notes: "",
    updated_at: "",
    completed_at: "",
  };
}

function normalizeStoredReview(review: Partial<WorkbenchReview>): WorkbenchReview {
  const base = emptyWorkbenchReview();
  return {
    ...base,
    ...review,
    verdicts: Array.isArray(review.verdicts) ? review.verdicts : [],
    fragment_missing_proposition: review.fragment_missing_proposition ?? {},
    fragment_coverage_gap: review.fragment_coverage_gap ?? {},
    proposition_issues: review.proposition_issues ?? {},
    context_assessments: review.context_assessments ?? {},
    failure_stages: Array.isArray(review.failure_stages) ? review.failure_stages : [],
    severity: review.severity ?? "",
    free_text_notes: review.free_text_notes ?? "",
    completed_at: review.completed_at ?? "",
  };
}

type StoredReviewState = Record<string, Record<string, WorkbenchReview>>;

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

export function hasNonEmptyNotes(review: WorkbenchReview): boolean {
  return review.free_text_notes.trim().length > 0;
}

export function hasMissingSourceAnnotation(review: WorkbenchReview): boolean {
  return Object.values(review.fragment_missing_proposition).some(Boolean);
}

export function hasCoverageGapAnnotation(review: WorkbenchReview): boolean {
  return Object.values(review.fragment_coverage_gap).some(Boolean);
}

export function hasOverreachingEvidence(review: WorkbenchReview): boolean {
  return Object.values(review.proposition_issues).some((issues) =>
    issues.some((issue) => OVERREACHING_PROPOSITION_ISSUES.includes(issue)),
  );
}

export function hasContextAssessmentInput(review: WorkbenchReview): boolean {
  return Object.values(review.context_assessments).some((flags) =>
    Object.values(flags ?? {}).some(Boolean),
  );
}

export function hasCompositionFailureStage(review: WorkbenchReview): boolean {
  return review.failure_stages.some((stage) => COMPOSITION_RELATED_FAILURE_STAGES.includes(stage));
}

export function isOnlyAccurateVerdict(review: WorkbenchReview): boolean {
  return review.verdicts.length === 1 && review.verdicts[0] === "accurate";
}

export function hasWorkbenchReviewInput(review: WorkbenchReview): boolean {
  return (
    review.verdicts.length > 0 ||
    hasMissingSourceAnnotation(review) ||
    hasCoverageGapAnnotation(review) ||
    Object.values(review.proposition_issues).some((issues) => issues.length > 0) ||
    hasContextAssessmentInput(review) ||
    review.failure_stages.length > 0 ||
    review.severity !== "" ||
    hasNonEmptyNotes(review)
  );
}

export function assessReviewCompleteness(review: WorkbenchReview): ReviewCompletenessAssessment {
  if (!hasWorkbenchReviewInput(review)) {
    return { status: "unreviewed", reasons: [] };
  }

  const reasons: string[] = [];

  if (review.verdicts.length === 0) {
    reasons.push("Select at least one verdict.");
  }

  if (!isOnlyAccurateVerdict(review) && review.severity === "") {
    reasons.push("Select a severity (not required when verdict is only accurate).");
  }

  if (review.verdicts.includes("incomplete")) {
    const hasEvidence =
      hasMissingSourceAnnotation(review) || hasCoverageGapAnnotation(review) || hasNonEmptyNotes(review);
    if (!hasEvidence) {
      reasons.push(
        "Incomplete verdict needs a missing-source mark, coverage gap mark, or notes.",
      );
    }
  }

  if (review.verdicts.includes("overreaching")) {
    const hasEvidence = hasOverreachingEvidence(review) || hasNonEmptyNotes(review);
    if (!hasEvidence) {
      reasons.push(
        "Overreaching verdict needs a wrong-extraction / should-not-exist issue or notes.",
      );
    }
  }

  if (review.verdicts.includes("bad_merge")) {
    const hasEvidence = hasCompositionFailureStage(review) || hasNonEmptyNotes(review);
    if (!hasEvidence) {
      reasons.push(
        "Bad merge verdict needs a composition-related failure stage or notes.",
      );
    }
  }

  if (review.verdicts.includes("missing_propositions")) {
    const hasEvidence = hasMissingSourceAnnotation(review) || hasNonEmptyNotes(review);
    if (!hasEvidence) {
      reasons.push(
        'Missing propositions verdict needs a law fragment marked "missing proposition here" or notes.',
      );
    }
  }

  if (reasons.length === 0) {
    return { status: "complete_review", reasons: [] };
  }

  return { status: "draft_review", reasons };
}

export function enrichReviewForExport(
  statementId: string,
  review: WorkbenchReview,
): WorkbenchReviewExportRow {
  const { status, reasons } = assessReviewCompleteness(review);
  return {
    statement_id: statementId,
    ...review,
    review_status: status,
    review_status_reasons: reasons,
  };
}

export function buildFilterReviewSummary(
  statementIds: string[],
  reviews: Record<string, WorkbenchReview>,
): WorkbenchExportSummary {
  const summary: WorkbenchExportSummary = {
    total_in_filter: statementIds.length,
    reviewed: 0,
    complete: 0,
    draft: 0,
    unreviewed: 0,
    draft_in_export: 0,
    verdict_counts: {},
    failure_stage_counts: {},
    severity_counts: {},
  };

  for (const statementId of statementIds) {
    const review = reviews[statementId] ?? emptyWorkbenchReview();
    const { status } = assessReviewCompleteness(review);

    if (status === "unreviewed") {
      summary.unreviewed += 1;
      continue;
    }

    summary.reviewed += 1;
    if (status === "complete_review") {
      summary.complete += 1;
    } else {
      summary.draft += 1;
    }

    for (const verdict of review.verdicts) {
      summary.verdict_counts[verdict] = (summary.verdict_counts[verdict] ?? 0) + 1;
    }
    for (const stage of review.failure_stages) {
      summary.failure_stage_counts[stage] = (summary.failure_stage_counts[stage] ?? 0) + 1;
    }
    if (review.severity !== "") {
      summary.severity_counts[review.severity] = (summary.severity_counts[review.severity] ?? 0) + 1;
    }
  }

  return summary;
}

export function loadWorkbenchReview(runId: string, statementId: string): WorkbenchReview {
  const stored = readStorage();
  const raw = stored[runId]?.[statementId];
  return raw ? normalizeStoredReview(raw) : emptyWorkbenchReview();
}

export function saveWorkbenchReview(
  runId: string,
  statementId: string,
  review: WorkbenchReview,
): void {
  const stored = readStorage();
  const runBucket = stored[runId] ?? {};
  const previous = runBucket[statementId];
  const now = new Date().toISOString();
  const nextReview = normalizeStoredReview(review);
  const nextAssessment = assessReviewCompleteness(nextReview);
  const previousAssessment = previous
    ? assessReviewCompleteness(normalizeStoredReview(previous))
    : { status: "unreviewed" as ReviewStatus, reasons: [] };

  let completed_at = "";
  if (nextAssessment.status === "complete_review") {
    completed_at =
      previousAssessment.status === "complete_review" && previous?.completed_at
        ? previous.completed_at
        : now;
  }

  runBucket[statementId] = {
    ...nextReview,
    updated_at: now,
    completed_at,
  };
  stored[runId] = runBucket;
  writeStorage(stored);
}

export function loadRunWorkbenchReviews(runId: string): Record<string, WorkbenchReview> {
  const stored = readStorage();
  return stored[runId] ?? {};
}

export function buildWorkbenchReviewExport(
  runId: string,
  reviews: Record<string, WorkbenchReview>,
  filterStatementIds: string[],
): WorkbenchReviewExport {
  const exportRows = Object.entries(reviews)
    .filter(([, review]) => hasWorkbenchReviewInput(review))
    .map(([statementId, review]) => enrichReviewForExport(statementId, review))
    .sort((left, right) => left.statement_id.localeCompare(right.statement_id));

  const summary = buildFilterReviewSummary(filterStatementIds, reviews);
  summary.draft_in_export = exportRows.filter((row) => row.review_status === "draft_review").length;

  return {
    schema_version: "3",
    exported_at: new Date().toISOString(),
    run_id: runId,
    filter_statement_ids: [...filterStatementIds].sort(),
    summary,
    reviews: exportRows,
  };
}

export function downloadWorkbenchReviewExport(payload: WorkbenchReviewExport): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  const draftSuffix = payload.summary.draft_in_export > 0 ? "-includes-draft" : "";
  anchor.download = `review-workbench-${payload.run_id}-${payload.exported_at.slice(0, 10)}${draftSuffix}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}
