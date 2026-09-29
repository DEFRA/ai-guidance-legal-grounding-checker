import {
  assessTraceBlockedHardCase,
  isTraceBlockedHardCase,
  type IncorporationRecommendationCounts,
  type TraceBlockedHardCaseProfile,
} from "@/lib/analyze-trace-blocked-hard-cases";
import type { CompositionBuildContext } from "@/lib/law-statements-composition";
import type { LawStatementRow, StatementQualityAssessment } from "@/lib/law-statements-index";
import { matchesQualityPreset, uniqueInstrumentKeysForStatement } from "@/lib/law-statements-index";
import {
  assessReviewCompleteness,
  emptyWorkbenchReview,
  loadRunWorkbenchReviews,
  type ReviewStatus,
  type WorkbenchReview,
} from "@/lib/review-workbench-state";

export type QueuePreset =
  | "needs_review_mix"
  | "beatrice_candidates"
  | "high_composition"
  | "unresolved_context"
  | "trace_blocked_hard_cases"
  | "random_sample"
  | "stratified_sample";

export type TraceBlockedQueueMetadata = {
  trace_block_reason: string;
  incorporation_counts: IncorporationRecommendationCounts;
  unresolved_locator_count: number;
  material_context_count: number;
  proposition_count: number;
  source_instrument: string;
};

export type QueueItem = {
  statement_id: string;
  sample_reason: string;
  sample_bucket: string;
  priority_score: number;
  already_reviewed: boolean;
  trace_metadata?: TraceBlockedQueueMetadata;
};

export type ReviewQueueManifest = {
  schema_version: "1";
  exported_at: string;
  run_id: string;
  preset: QueuePreset;
  seed: string;
  sample_size: number;
  filter_statement_ids: string[];
  items: QueueItem[];
  summary: {
    total: number;
    reviewed: number;
    unreviewed: number;
  };
};

export type StoredReviewQueue = {
  preset: QueuePreset;
  seed: string;
  sample_size: number;
  generated_at: string;
  filter_statement_ids: string[];
  items: QueueItem[];
};

export type StatementSamplingContext = {
  statement: LawStatementRow;
  quality: StatementQualityAssessment;
  isPropositionMatcherCandidate: boolean;
  instrumentKey: string;
  reviewStatus: ReviewStatus;
  traceHardCase?: TraceBlockedHardCaseProfile | null;
};

export const QUEUE_PRESET_OPTIONS: ReadonlyArray<{ value: QueuePreset; label: string }> = [
  { value: "needs_review_mix", label: "Needs review mix" },
  { value: "beatrice_candidates", label: "Proposition Matcher candidates" },
  { value: "high_composition", label: "High composition" },
  { value: "unresolved_context", label: "Unresolved context" },
  { value: "trace_blocked_hard_cases", label: "Trace-blocked hard cases" },
  { value: "random_sample", label: "Random sample" },
  { value: "stratified_sample", label: "Stratified sample" },
];

const QUEUE_STORAGE_KEY = "law-proposition-extractor.review-workbench.queue.v2";

type StoredQueueState = Record<string, StoredReviewQueue>;

export function hashStringToUint32(input: string): number {
  let hash = 2166136261;
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export function seededRandomUnit(seed: string, statementId: string): number {
  let state = hashStringToUint32(`${seed}\0${statementId}`);
  state += 0x6d2b79f5;
  let value = Math.imul(state ^ (state >>> 15), state | 1);
  value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
  return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
}

export function deterministicSample<T>(
  items: readonly T[],
  sampleSize: number,
  seed: string,
  idOf: (item: T) => string,
): T[] {
  if (sampleSize <= 0 || items.length === 0) {
    return [];
  }
  if (items.length <= sampleSize) {
    return [...items];
  }
  const scored = items.map((item) => ({
    item,
    score: seededRandomUnit(seed, idOf(item)),
  }));
  scored.sort(
    (left, right) =>
      left.score - right.score || idOf(left.item).localeCompare(idOf(right.item)),
  );
  return scored.slice(0, sampleSize).map((row) => row.item);
}

export function propositionCountBucket(count: number): "1" | "2-3" | "4-6" | "7+" {
  if (count <= 1) {
    return "1";
  }
  if (count <= 3) {
    return "2-3";
  }
  if (count <= 6) {
    return "4-6";
  }
  return "7+";
}

export function standaloneCompletenessBucket(standaloneStatus: string): "complete" | "incomplete" {
  return standaloneStatus === "standalone" ? "complete" : "incomplete";
}

export function hasUnresolvedContext(quality: StatementQualityAssessment): boolean {
  return (
    quality.flags.includes("unresolved_context") || quality.flags.includes("ambiguous_context")
  );
}

export function stratificationKey(ctx: StatementSamplingContext): string {
  const completeBucket = standaloneCompletenessBucket(ctx.statement.standalone_status);
  const propBucket = propositionCountBucket(ctx.quality.uniquePropositionCount);
  const proposition-matcher = ctx.isPropositionMatcherCandidate ? "yes" : "no";
  const unresolved = hasUnresolvedContext(ctx.quality) ? "yes" : "no";
  return `${completeBucket}|${propBucket}|proposition-matcher:${proposition-matcher}|unresolved:${unresolved}|instrument:${ctx.instrumentKey}`;
}

export function primaryInstrumentKey(
  statement: LawStatementRow,
  instrumentKeyByPropositionId: Map<string, string>,
): string {
  const keys = uniqueInstrumentKeysForStatement(statement, instrumentKeyByPropositionId);
  return keys[0] ?? "__unknown_instrument__";
}

export function buildStatementSamplingContexts(
  statements: LawStatementRow[],
  options: {
    qualityById: Map<string, StatementQualityAssessment>;
    propositionMatcherStatementIds: Set<string>;
    instrumentKeyByPropositionId: Map<string, string>;
    compositionContext?: CompositionBuildContext;
    reviews?: Record<string, WorkbenchReview>;
  },
): StatementSamplingContext[] {
  const reviews = options.reviews ?? {};
  return statements.map((statement) => {
    const quality =
      options.qualityById.get(statement.id) ??
      ({
        uniquePropositionCount: 0,
        refCount: 0,
        flags: [],
        issueLabels: [],
        reviewScore: 0,
      } satisfies StatementQualityAssessment);
    const review = reviews[statement.id] ?? emptyWorkbenchReview();
    const traceHardCase = options.compositionContext
      ? assessTraceBlockedHardCase({
          statement,
          context: options.compositionContext,
          instrumentKeyByPropositionId: options.instrumentKeyByPropositionId,
          quality,
        })
      : null;
    return {
      statement,
      quality,
      isPropositionMatcherCandidate: options.propositionMatcherStatementIds.has(statement.id),
      instrumentKey: primaryInstrumentKey(statement, options.instrumentKeyByPropositionId),
      reviewStatus: assessReviewCompleteness(review).status,
      traceHardCase,
    };
  });
}

function isAlreadyReviewed(reviewStatus: ReviewStatus): boolean {
  return reviewStatus !== "unreviewed";
}

function traceMetadataFromProfile(
  profile: TraceBlockedHardCaseProfile,
): TraceBlockedQueueMetadata {
  return {
    trace_block_reason: profile.traceBlockReason,
    incorporation_counts: profile.incorporationCounts,
    unresolved_locator_count: profile.unresolvedLocatorCount,
    material_context_count: profile.materialContextCount,
    proposition_count: profile.propositionCount,
    source_instrument: profile.sourceInstrument,
  };
}

function toQueueItem(
  ctx: StatementSamplingContext,
  sampleReason: string,
  sampleBucket: string,
  priorityScore?: number,
): QueueItem {
  return {
    statement_id: ctx.statement.id,
    sample_reason: sampleReason,
    sample_bucket: sampleBucket,
    priority_score: priorityScore ?? ctx.quality.reviewScore,
    already_reviewed: isAlreadyReviewed(ctx.reviewStatus),
    trace_metadata: ctx.traceHardCase ? traceMetadataFromProfile(ctx.traceHardCase) : undefined,
  };
}

function filterContextsForPreset(
  contexts: StatementSamplingContext[],
  preset: QueuePreset,
): StatementSamplingContext[] {
  switch (preset) {
    case "beatrice_candidates":
      return contexts.filter((ctx) => ctx.isPropositionMatcherCandidate);
    case "high_composition":
      return contexts.filter((ctx) => ctx.quality.flags.includes("high_composition"));
    case "unresolved_context":
      return contexts.filter((ctx) => hasUnresolvedContext(ctx.quality));
    case "needs_review_mix":
      return contexts.filter((ctx) => matchesQualityPreset(ctx.quality, "needs_review"));
    case "trace_blocked_hard_cases":
      return contexts.filter((ctx) => isTraceBlockedHardCase(ctx.traceHardCase));
    case "random_sample":
    case "stratified_sample":
      return contexts;
    default:
      return contexts;
  }
}

function buildNeedsReviewMixSample(
  contexts: StatementSamplingContext[],
  sampleSize: number,
  seed: string,
): StatementSamplingContext[] {
  const pool =
    contexts.filter((ctx) => matchesQualityPreset(ctx.quality, "needs_review")).length > 0
      ? contexts.filter((ctx) => matchesQualityPreset(ctx.quality, "needs_review"))
      : contexts;

  const ranked = [...pool].sort((left, right) => {
    const scoreDiff = right.quality.reviewScore - left.quality.reviewScore;
    if (scoreDiff !== 0) {
      return scoreDiff;
    }
    const leftRand = seededRandomUnit(seed, left.statement.id);
    const rightRand = seededRandomUnit(seed, right.statement.id);
    return leftRand - rightRand || left.statement.id.localeCompare(right.statement.id);
  });

  return ranked.slice(0, sampleSize);
}

function buildTraceBlockedHardCasesSample(
  contexts: StatementSamplingContext[],
  sampleSize: number,
): StatementSamplingContext[] {
  const ranked = [...contexts]
    .filter((ctx) => isTraceBlockedHardCase(ctx.traceHardCase))
    .sort((left, right) => {
      const leftScore = left.traceHardCase?.priorityScore ?? 0;
      const rightScore = right.traceHardCase?.priorityScore ?? 0;
      const scoreDiff = rightScore - leftScore;
      if (scoreDiff !== 0) {
        return scoreDiff;
      }
      return left.statement.id.localeCompare(right.statement.id);
    });
  return ranked.slice(0, sampleSize);
}

export function countTraceBlockedHardCases(contexts: StatementSamplingContext[]): number {
  return contexts.filter((ctx) => isTraceBlockedHardCase(ctx.traceHardCase)).length;
}

function buildStratifiedSample(
  contexts: StatementSamplingContext[],
  sampleSize: number,
  seed: string,
): StatementSamplingContext[] {
  if (contexts.length === 0 || sampleSize <= 0) {
    return [];
  }

  const strata = new Map<string, StatementSamplingContext[]>();
  for (const ctx of contexts) {
    const key = stratificationKey(ctx);
    const bucket = strata.get(key) ?? [];
    bucket.push(ctx);
    strata.set(key, bucket);
  }

  const total = contexts.length;
  const allocations: Array<{ key: string; items: StatementSamplingContext[]; take: number }> = [];
  let allocated = 0;

  for (const [key, items] of strata) {
    const proportion = items.length / total;
    let take = Math.floor(sampleSize * proportion);
    if (take === 0 && items.length > 0 && allocated < sampleSize) {
      take = 1;
    }
    take = Math.min(take, items.length);
    allocations.push({ key, items, take });
    allocated += take;
  }

  let remainder = sampleSize - allocated;
  const sortedAllocations = [...allocations].sort(
    (left, right) => right.items.length - left.items.length,
  );
  for (const row of sortedAllocations) {
    if (remainder <= 0) {
      break;
    }
    const extra = Math.min(remainder, row.items.length - row.take);
    row.take += extra;
    remainder -= extra;
  }

  const selected: StatementSamplingContext[] = [];
  for (const { key, items, take } of allocations) {
    if (take <= 0) {
      continue;
    }
    selected.push(...deterministicSample(items, take, `${seed}|${key}`, (ctx) => ctx.statement.id));
  }

  selected.sort((left, right) => {
    const scoreDiff = right.quality.reviewScore - left.quality.reviewScore;
    if (scoreDiff !== 0) {
      return scoreDiff;
    }
    return left.statement.id.localeCompare(right.statement.id);
  });

  return selected.slice(0, sampleSize);
}

export function buildReviewQueueItems(
  contexts: StatementSamplingContext[],
  preset: QueuePreset,
  sampleSize: number,
  seed: string,
): QueueItem[] {
  const pool = filterContextsForPreset(contexts, preset);
  const workingPool =
    pool.length > 0 || preset === "trace_blocked_hard_cases" ? pool : contexts;

  let selected: StatementSamplingContext[];
  switch (preset) {
    case "needs_review_mix":
      selected = buildNeedsReviewMixSample(workingPool, sampleSize, seed);
      break;
    case "trace_blocked_hard_cases":
      selected = buildTraceBlockedHardCasesSample(workingPool, sampleSize);
      break;
    case "stratified_sample":
      selected = buildStratifiedSample(workingPool, sampleSize, seed);
      break;
    case "random_sample":
    case "beatrice_candidates":
    case "high_composition":
    case "unresolved_context":
      selected = deterministicSample(workingPool, sampleSize, seed, (ctx) => ctx.statement.id);
      break;
    default:
      selected = deterministicSample(workingPool, sampleSize, seed, (ctx) => ctx.statement.id);
  }

  return selected.map((ctx) => {
    const bucket =
      preset === "stratified_sample"
        ? stratificationKey(ctx)
        : preset === "needs_review_mix"
          ? "needs_review"
          : preset === "trace_blocked_hard_cases"
            ? ctx.traceHardCase?.traceBlockReason ?? "trace_blocked"
            : preset;
    const reason =
      preset === "stratified_sample"
        ? `stratified: ${bucket}`
        : preset === "needs_review_mix"
          ? `needs_review mix (score ${ctx.quality.reviewScore})`
          : preset === "trace_blocked_hard_cases" && ctx.traceHardCase
            ? `trace-blocked: ${ctx.traceHardCase.traceBlockReason.replaceAll("_", " ")} (priority ${ctx.traceHardCase.priorityScore})`
            : `${preset.replaceAll("_", " ")} (score ${ctx.quality.reviewScore})`;
    const priorityScore =
      preset === "trace_blocked_hard_cases" && ctx.traceHardCase
        ? ctx.traceHardCase.priorityScore
        : ctx.quality.reviewScore;
    return toQueueItem(ctx, reason, bucket, priorityScore);
  });
}

export function buildReviewQueue(
  runId: string,
  filterStatementIds: string[],
  contexts: StatementSamplingContext[],
  preset: QueuePreset,
  sampleSize: number,
  seed: string,
): StoredReviewQueue {
  const filterSet = new Set(filterStatementIds);
  const filteredContexts = contexts.filter((ctx) => filterSet.has(ctx.statement.id));
  const items = buildReviewQueueItems(filteredContexts, preset, sampleSize, seed);
  return {
    preset,
    seed,
    sample_size: sampleSize,
    generated_at: new Date().toISOString(),
    filter_statement_ids: [...filterStatementIds].sort(),
    items,
  };
}

export function refreshQueueReviewFlags(
  queue: StoredReviewQueue,
  reviews: Record<string, WorkbenchReview>,
): StoredReviewQueue {
  return {
    ...queue,
    items: queue.items.map((item) => {
      const review = reviews[item.statement_id] ?? emptyWorkbenchReview();
      return {
        ...item,
        already_reviewed: isAlreadyReviewed(assessReviewCompleteness(review).status),
      };
    }),
  };
}

export function buildReviewQueueManifest(
  runId: string,
  queue: StoredReviewQueue,
): ReviewQueueManifest {
  const reviewed = queue.items.filter((item) => item.already_reviewed).length;
  return {
    schema_version: "1",
    exported_at: new Date().toISOString(),
    run_id: runId,
    preset: queue.preset,
    seed: queue.seed,
    sample_size: queue.sample_size,
    filter_statement_ids: queue.filter_statement_ids,
    items: queue.items,
    summary: {
      total: queue.items.length,
      reviewed,
      unreviewed: queue.items.length - reviewed,
    },
  };
}

export function downloadReviewQueueManifest(manifest: ReviewQueueManifest): void {
  const blob = new Blob([JSON.stringify(manifest, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `review-queue-${manifest.run_id}-${manifest.preset}-${manifest.exported_at.slice(0, 10)}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function findNextUnreviewedQueueItem(
  queue: StoredReviewQueue,
  currentStatementId?: string,
): QueueItem | null {
  if (queue.items.length === 0) {
    return null;
  }

  const startIndex =
    currentStatementId != null
      ? Math.max(
          0,
          queue.items.findIndex((item) => item.statement_id === currentStatementId) + 1,
        )
      : 0;

  for (let index = startIndex; index < queue.items.length; index += 1) {
    const item = queue.items[index];
    if (!item.already_reviewed) {
      return item;
    }
  }

  for (let index = 0; index < startIndex; index += 1) {
    const item = queue.items[index];
    if (!item.already_reviewed) {
      return item;
    }
  }

  return null;
}

function readQueueStorage(): StoredQueueState {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(QUEUE_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as StoredQueueState;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeQueueStorage(state: StoredQueueState): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(QUEUE_STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* ignore quota errors */
  }
}

export function loadReviewQueue(runId: string): StoredReviewQueue | null {
  const stored = readQueueStorage()[runId];
  if (!stored || !Array.isArray(stored.items)) {
    return null;
  }
  return stored;
}

export function saveReviewQueue(runId: string, queue: StoredReviewQueue): void {
  const stored = readQueueStorage();
  stored[runId] = queue;
  writeQueueStorage(stored);
}

export function loadRunReviewsForQueue(runId: string): Record<string, WorkbenchReview> {
  return loadRunWorkbenchReviews(runId);
}
