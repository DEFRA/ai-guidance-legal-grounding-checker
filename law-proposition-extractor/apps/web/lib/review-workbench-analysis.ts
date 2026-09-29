import { assessStatementQuality, type LawStatementRow } from "@/lib/law-statements-index";
import {
  primaryInstrumentKey,
  propositionCountBucket,
  type ReviewQueueManifest,
} from "@/lib/review-workbench-queue";
import type { ReviewerRating } from "@/lib/law-statements-reviewer-state";
import {
  FAILURE_STAGE_OPTIONS,
  STATEMENT_VERDICT_OPTIONS,
  emptyWorkbenchReview,
  type FailureStage,
  type ReviewSeverity,
  type ReviewStatus,
  type StatementVerdict,
  type WorkbenchReviewExport,
  type WorkbenchReviewExportRow,
} from "@/lib/review-workbench-state";

export type ReviewAnalysisFilters = {
  includeDrafts: boolean;
  queueOnly: boolean;
  exportReviewsOnly: boolean;
};

export type ReviewAnalysisEnrichment = {
  instrumentByStatementId: Map<string, string>;
  propositionCountBucketByStatementId: Map<string, string>;
  propositionMatcherCandidateIds: Set<string>;
  sampleBucketByStatementId: Map<string, string>;
};

export type RateBreakdown = {
  bucket: string;
  total: number;
  reviewed: number;
  verdict_rates: Partial<Record<StatementVerdict, number>>;
  issue_rate: number;
};

export type PropositionMatcherProxyBreakdown = {
  pass: number;
  concern: number;
  fail: number;
  unreviewed: number;
  total_candidates: number;
};

export type ReviewAnalysisSummary = {
  scope_total: number;
  reviewed: number;
  complete: number;
  draft: number;
  unreviewed: number;
  verdict_rates: Partial<Record<StatementVerdict, number>>;
  failure_stage_rates: Partial<Record<FailureStage, number>>;
  severity_distribution: Partial<Record<Exclude<ReviewSeverity, "">, number>>;
  rates_by_sample_bucket: RateBreakdown[];
  rates_by_instrument: RateBreakdown[];
  rates_by_proposition_count_bucket: RateBreakdown[];
  proposition_matcher_proxy: PropositionMatcherProxyBreakdown;
};

export type InstrumentFailureRow = {
  instrument: string;
  significant_critical_count: number;
  reviewed_count: number;
  rate: number;
};

export type FailureStageComboRow = {
  combination: string;
  count: number;
};

export type ReviewCaseRow = {
  statement_id: string;
  review_status: ReviewStatus;
  verdicts: StatementVerdict[];
  severity: ReviewSeverity;
  failure_stages: FailureStage[];
  sample_bucket: string;
  instrument: string;
  proposition_count_bucket: string;
  proposition_matcher_proxy: ReviewerRating | null;
  free_text_notes: string;
};

export type ReviewAnalysisResult = {
  summary: ReviewAnalysisSummary;
  worst_instruments: InstrumentFailureRow[];
  failure_stage_combinations: FailureStageComboRow[];
  incomplete_missing_propositions_cases: ReviewCaseRow[];
  overreaching_cases: ReviewCaseRow[];
  bad_merge_cases: ReviewCaseRow[];
  filters: ReviewAnalysisFilters;
  run_id: string;
  export_run_id: string | null;
  queue_run_id: string | null;
};

const UNKNOWN_BUCKET = "__unknown__";
const ISSUE_VERDICTS: ReadonlyArray<StatementVerdict> = [
  "incomplete",
  "overreaching",
  "bad_merge",
  "missing_propositions",
];

export function parseReviewExport(input: unknown): WorkbenchReviewExport {
  if (!input || typeof input !== "object") {
    throw new Error("Review export must be a JSON object.");
  }
  const payload = input as Partial<WorkbenchReviewExport>;
  if (payload.schema_version !== "3") {
    throw new Error(`Unsupported review export schema_version: ${String(payload.schema_version)}`);
  }
  if (!Array.isArray(payload.reviews)) {
    throw new Error("Review export is missing a reviews array.");
  }
  if (!Array.isArray(payload.filter_statement_ids)) {
    throw new Error("Review export is missing filter_statement_ids.");
  }
  return payload as WorkbenchReviewExport;
}

export function parseQueueManifest(input: unknown): ReviewQueueManifest {
  if (!input || typeof input !== "object") {
    throw new Error("Queue manifest must be a JSON object.");
  }
  const payload = input as Partial<ReviewQueueManifest>;
  if (payload.schema_version !== "1") {
    throw new Error(`Unsupported queue manifest schema_version: ${String(payload.schema_version)}`);
  }
  if (!Array.isArray(payload.items)) {
    throw new Error("Queue manifest is missing an items array.");
  }
  return payload as ReviewQueueManifest;
}

export function parseInstrumentFromSampleBucket(sampleBucket: string): string | null {
  const marker = "instrument:";
  const index = sampleBucket.lastIndexOf(marker);
  if (index < 0) {
    return null;
  }
  const instrument = sampleBucket.slice(index + marker.length).trim();
  return instrument || null;
}

export function parsePropositionCountBucketFromSampleBucket(sampleBucket: string): string | null {
  if (!sampleBucket.includes("|")) {
    return null;
  }
  const [_, propBucket] = sampleBucket.split("|");
  if (!propBucket || !["1", "2-3", "4-6", "7+"].includes(propBucket)) {
    return null;
  }
  return propBucket;
}

export function buildReviewAnalysisEnrichment(options: {
  statements?: LawStatementRow[];
  instrumentKeyByPropositionId?: Map<string, string>;
  propositionMatcherCandidateIds?: Set<string>;
  queueManifest?: ReviewQueueManifest | null;
}): ReviewAnalysisEnrichment {
  const instrumentByStatementId = new Map<string, string>();
  const propositionCountBucketByStatementId = new Map<string, string>();
  const sampleBucketByStatementId = new Map<string, string>();
  const propositionMatcherCandidateIds = new Set(options.propositionMatcherCandidateIds ?? []);

  for (const item of options.queueManifest?.items ?? []) {
    sampleBucketByStatementId.set(item.statement_id, item.sample_bucket);
    const instrument = parseInstrumentFromSampleBucket(item.sample_bucket);
    if (instrument) {
      instrumentByStatementId.set(item.statement_id, instrument);
    }
    const propBucket = parsePropositionCountBucketFromSampleBucket(item.sample_bucket);
    if (propBucket) {
      propositionCountBucketByStatementId.set(item.statement_id, propBucket);
    }
  }

  const instrumentKeyByPropositionId = options.instrumentKeyByPropositionId ?? new Map();
  for (const statement of options.statements ?? []) {
    if (!instrumentByStatementId.has(statement.id)) {
      instrumentByStatementId.set(
        statement.id,
        primaryInstrumentKey(statement, instrumentKeyByPropositionId),
      );
    }
    if (!propositionCountBucketByStatementId.has(statement.id)) {
      const quality = assessStatementQuality(statement);
      propositionCountBucketByStatementId.set(
        statement.id,
        propositionCountBucket(quality.uniquePropositionCount),
      );
    }
  }

  return {
    instrumentByStatementId,
    propositionCountBucketByStatementId,
    propositionMatcherCandidateIds,
    sampleBucketByStatementId,
  };
}

export function inferPropositionMatcherCandidateProxy(
  review: Pick<WorkbenchReviewExportRow, "verdicts" | "severity" | "failure_stages" | "review_status">,
): ReviewerRating | null {
  if (review.review_status === "unreviewed" || review.verdicts.length === 0) {
    return null;
  }

  if (
    review.severity === "significant" ||
    review.severity === "critical" ||
    review.verdicts.some((verdict) =>
      (["overreaching", "bad_merge", "missing_propositions"] as StatementVerdict[]).includes(
        verdict,
      ),
    ) ||
    review.failure_stages.includes("beatrice_suitability")
  ) {
    return "fail";
  }

  if (review.verdicts.length === 1 && review.verdicts[0] === "accurate") {
    return "pass";
  }

  return "concern";
}

function rate(count: number, total: number): number {
  return total > 0 ? count / total : 0;
}

function failureStageCombinationKey(stages: FailureStage[]): string {
  return [...stages].sort().join(" + ") || "(none)";
}

function hasIssueVerdict(verdicts: StatementVerdict[]): boolean {
  return verdicts.some((verdict) => ISSUE_VERDICTS.includes(verdict));
}

function buildRateBreakdowns(
  rows: ReviewCaseRow[],
  bucketOf: (row: ReviewCaseRow) => string,
): RateBreakdown[] {
  const buckets = new Map<string, ReviewCaseRow[]>();
  for (const row of rows) {
    const bucket = bucketOf(row) || UNKNOWN_BUCKET;
    const group = buckets.get(bucket) ?? [];
    group.push(row);
    buckets.set(bucket, group);
  }

  return [...buckets.entries()]
    .map(([bucket, groupRows]) => {
      const reviewedRows = groupRows.filter((row) => row.review_status !== "unreviewed");
      const reviewed = reviewedRows.length;
      const verdictCounts: Partial<Record<StatementVerdict, number>> = {};
      for (const row of reviewedRows) {
        for (const verdict of row.verdicts) {
          verdictCounts[verdict] = (verdictCounts[verdict] ?? 0) + 1;
        }
      }
      const verdict_rates: Partial<Record<StatementVerdict, number>> = {};
      for (const option of STATEMENT_VERDICT_OPTIONS) {
        const count = verdictCounts[option.value] ?? 0;
        if (count > 0) {
          verdict_rates[option.value] = rate(count, reviewed);
        }
      }
      const issueCount = reviewedRows.filter((row) => hasIssueVerdict(row.verdicts)).length;
      return {
        bucket,
        total: groupRows.length,
        reviewed,
        verdict_rates,
        issue_rate: rate(issueCount, reviewed),
      };
    })
    .sort((left, right) => right.total - left.total || left.bucket.localeCompare(right.bucket));
}

function toCaseRow(
  statementId: string,
  review: WorkbenchReviewExportRow | null,
  enrichment: ReviewAnalysisEnrichment,
): ReviewCaseRow {
  const resolved = review ?? {
    statement_id: statementId,
    ...emptyWorkbenchReview(),
    review_status: "unreviewed" as const,
    review_status_reasons: [],
  };
  const isBeatrice = enrichment.propositionMatcherCandidateIds.has(statementId);
  return {
    statement_id: statementId,
    review_status: resolved.review_status,
    verdicts: resolved.verdicts,
    severity: resolved.severity,
    failure_stages: resolved.failure_stages,
    sample_bucket: enrichment.sampleBucketByStatementId.get(statementId) ?? UNKNOWN_BUCKET,
    instrument: enrichment.instrumentByStatementId.get(statementId) ?? UNKNOWN_BUCKET,
    proposition_count_bucket:
      enrichment.propositionCountBucketByStatementId.get(statementId) ?? UNKNOWN_BUCKET,
    proposition_matcher_proxy: isBeatrice ? inferPropositionMatcherCandidateProxy(resolved) : null,
    free_text_notes: resolved.free_text_notes,
  };
}

export function buildReviewAnalysis(
  reviewExport: WorkbenchReviewExport,
  options?: {
    queueManifest?: ReviewQueueManifest | null;
    enrichment?: ReviewAnalysisEnrichment;
    filters?: Partial<ReviewAnalysisFilters>;
  },
): ReviewAnalysisResult {
  const filters: ReviewAnalysisFilters = {
    includeDrafts: options?.filters?.includeDrafts ?? false,
    queueOnly: options?.filters?.queueOnly ?? false,
    exportReviewsOnly: options?.filters?.exportReviewsOnly ?? true,
  };

  const enrichment =
    options?.enrichment ??
    buildReviewAnalysisEnrichment({ queueManifest: options?.queueManifest ?? null });

  const reviewsById = new Map(
    reviewExport.reviews.map((row) => [row.statement_id, row] as const),
  );

  let scopeIds: string[];
  if (filters.exportReviewsOnly) {
    scopeIds = reviewExport.reviews.map((row) => row.statement_id);
  } else {
    scopeIds = [...reviewExport.filter_statement_ids];
  }

  if (filters.queueOnly) {
    const queueIds = new Set(
      (options?.queueManifest?.items ?? []).map((item) => item.statement_id),
    );
    scopeIds = scopeIds.filter((statementId) => queueIds.has(statementId));
  }

  const scopeRows = scopeIds.map((statementId) =>
    toCaseRow(statementId, reviewsById.get(statementId) ?? null, enrichment),
  );

  const statusFilteredRows = scopeRows.filter((row) => {
    if (row.review_status === "unreviewed") {
      return true;
    }
    if (filters.includeDrafts) {
      return true;
    }
    return row.review_status === "complete_review";
  });

  const reviewedRows = statusFilteredRows.filter((row) => row.review_status !== "unreviewed");
  const complete = reviewedRows.filter((row) => row.review_status === "complete_review").length;
  const draft = reviewedRows.filter((row) => row.review_status === "draft_review").length;
  const unreviewed = statusFilteredRows.filter((row) => row.review_status === "unreviewed").length;

  const verdictCounts: Partial<Record<StatementVerdict, number>> = {};
  const failureStageCounts: Partial<Record<FailureStage, number>> = {};
  const severityCounts: Partial<Record<Exclude<ReviewSeverity, "">, number>> = {};

  for (const row of reviewedRows) {
    for (const verdict of row.verdicts) {
      verdictCounts[verdict] = (verdictCounts[verdict] ?? 0) + 1;
    }
    for (const stage of row.failure_stages) {
      failureStageCounts[stage] = (failureStageCounts[stage] ?? 0) + 1;
    }
    if (row.severity !== "") {
      severityCounts[row.severity] = (severityCounts[row.severity] ?? 0) + 1;
    }
  }

  const verdict_rates: Partial<Record<StatementVerdict, number>> = {};
  for (const option of STATEMENT_VERDICT_OPTIONS) {
    const count = verdictCounts[option.value] ?? 0;
    if (count > 0) {
      verdict_rates[option.value] = rate(count, reviewedRows.length);
    }
  }

  const failure_stage_rates: Partial<Record<FailureStage, number>> = {};
  for (const option of FAILURE_STAGE_OPTIONS) {
    const count = failureStageCounts[option.value] ?? 0;
    if (count > 0) {
      failure_stage_rates[option.value] = rate(count, reviewedRows.length);
    }
  }

  const propositionMatcherCandidates = reviewedRows.filter(
    (row) => enrichment.propositionMatcherCandidateIds.has(row.statement_id) || row.proposition_matcher_proxy != null,
  );
  const proposition_matcher_proxy: PropositionMatcherProxyBreakdown = {
    pass: 0,
    concern: 0,
    fail: 0,
    unreviewed: 0,
    total_candidates: enrichment.propositionMatcherCandidateIds.size || propositionMatcherCandidates.length,
  };
  for (const statementId of enrichment.propositionMatcherCandidateIds) {
    const row = statusFilteredRows.find((entry) => entry.statement_id === statementId);
    if (!row || row.review_status === "unreviewed") {
      proposition_matcher_proxy.unreviewed += 1;
      continue;
    }
    if (!filters.includeDrafts && row.review_status === "draft_review") {
      proposition_matcher_proxy.unreviewed += 1;
      continue;
    }
    const proxy = inferPropositionMatcherCandidateProxy(row);
    if (proxy === "pass") {
      proposition_matcher_proxy.pass += 1;
    } else if (proxy === "concern") {
      proposition_matcher_proxy.concern += 1;
    } else if (proxy === "fail") {
      proposition_matcher_proxy.fail += 1;
    }
  }

  const instrumentFailures = new Map<string, { sigCrit: number; reviewed: number }>();
  for (const row of reviewedRows) {
    const instrument = row.instrument;
    const bucket = instrumentFailures.get(instrument) ?? { sigCrit: 0, reviewed: 0 };
    bucket.reviewed += 1;
    if (row.severity === "significant" || row.severity === "critical") {
      bucket.sigCrit += 1;
    }
    instrumentFailures.set(instrument, bucket);
  }

  const comboCounts = new Map<string, number>();
  for (const row of reviewedRows) {
    const key = failureStageCombinationKey(row.failure_stages);
    comboCounts.set(key, (comboCounts.get(key) ?? 0) + 1);
  }

  const caseMatchesVerdict = (row: ReviewCaseRow, verdict: StatementVerdict) =>
    row.verdicts.includes(verdict);

  return {
    summary: {
      scope_total: statusFilteredRows.length,
      reviewed: reviewedRows.length,
      complete,
      draft,
      unreviewed,
      verdict_rates,
      failure_stage_rates,
      severity_distribution: severityCounts,
      rates_by_sample_bucket: buildRateBreakdowns(statusFilteredRows, (row) => row.sample_bucket),
      rates_by_instrument: buildRateBreakdowns(statusFilteredRows, (row) => row.instrument),
      rates_by_proposition_count_bucket: buildRateBreakdowns(
        statusFilteredRows,
        (row) => row.proposition_count_bucket,
      ),
      proposition_matcher_proxy,
    },
    worst_instruments: [...instrumentFailures.entries()]
      .map(([instrument, counts]) => ({
        instrument,
        significant_critical_count: counts.sigCrit,
        reviewed_count: counts.reviewed,
        rate: rate(counts.sigCrit, counts.reviewed),
      }))
      .filter((row) => row.significant_critical_count > 0)
      .sort(
        (left, right) =>
          right.significant_critical_count - left.significant_critical_count ||
          right.rate - left.rate ||
          left.instrument.localeCompare(right.instrument),
      ),
    failure_stage_combinations: [...comboCounts.entries()]
      .map(([combination, count]) => ({ combination, count }))
      .sort((left, right) => {
        const countDiff = right.count - left.count;
        if (countDiff !== 0) {
          return countDiff;
        }
        if (left.combination === "(none)") {
          return 1;
        }
        if (right.combination === "(none)") {
          return -1;
        }
        return left.combination.localeCompare(right.combination);
      }),
    incomplete_missing_propositions_cases: reviewedRows.filter(
      (row) =>
        caseMatchesVerdict(row, "incomplete") || caseMatchesVerdict(row, "missing_propositions"),
    ),
    overreaching_cases: reviewedRows.filter((row) => caseMatchesVerdict(row, "overreaching")),
    bad_merge_cases: reviewedRows.filter((row) => caseMatchesVerdict(row, "bad_merge")),
    filters,
    run_id: reviewExport.run_id,
    export_run_id: reviewExport.run_id,
    queue_run_id: options?.queueManifest?.run_id ?? null,
  };
}
