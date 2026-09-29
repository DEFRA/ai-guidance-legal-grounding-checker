"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import type {
  LawStatementRow,
  PropositionRow,
  SourceRow,
  StatementQualityAssessment,
} from "@/lib/law-statements-index";
import {
  QUEUE_PRESET_OPTIONS,
  buildReviewQueue,
  buildReviewQueueManifest,
  buildStatementSamplingContexts,
  countTraceBlockedHardCases,
  downloadReviewQueueManifest,
  findNextUnreviewedQueueItem,
  loadReviewQueue,
  loadRunReviewsForQueue,
  refreshQueueReviewFlags,
  saveReviewQueue,
  type QueuePreset,
  type StoredReviewQueue,
} from "@/lib/review-workbench-queue";
import { buildCompositionContext } from "@/lib/export-composition-trace";

export function ReviewQueuePanel(props: {
  runId: string;
  filterStatementIds: string[];
  statements: LawStatementRow[];
  propositions: PropositionRow[];
  sources: SourceRow[];
  sourceFragments: SourceFragmentRow[];
  completenessByPropositionId: Map<string, string>;
  qualityById: Map<string, StatementQualityAssessment>;
  propositionMatcherStatementIds: Set<string>;
  instrumentKeyByPropositionId: Map<string, string>;
  currentStatementId?: string;
  reviewTick: number;
  onNavigateToStatement: (statementId: string) => void;
}): JSX.Element {
  const {
    runId,
    filterStatementIds,
    statements,
    propositions,
    sources,
    sourceFragments,
    completenessByPropositionId,
    qualityById,
    propositionMatcherStatementIds,
    instrumentKeyByPropositionId,
    currentStatementId,
    reviewTick,
    onNavigateToStatement,
  } = props;

  const [preset, setPreset] = useState<QueuePreset>("needs_review_mix");
  const [sampleSize, setSampleSize] = useState(20);
  const [seed, setSeed] = useState("review-queue-v1");
  const [queue, setQueue] = useState<StoredReviewQueue | null>(null);

  const statementById = useMemo(() => {
    const map = new Map<string, LawStatementRow>();
    for (const statement of statements) {
      map.set(statement.id, statement);
    }
    return map;
  }, [statements]);

  const compositionContext = useMemo(
    () =>
      buildCompositionContext({
        propositions,
        source_fragments: sourceFragments,
        source_records: sources,
        effective_law_statements: { statements },
        proposition_completeness_assessments: Array.from(
          completenessByPropositionId.entries(),
        ).map(([proposition_id, status]) => ({ proposition_id, status })),
      }),
    [completenessByPropositionId, propositions, sourceFragments, sources, statements],
  );

  const samplingContexts = useMemo(
    () =>
      buildStatementSamplingContexts(
        filterStatementIds
          .map((statementId) => statementById.get(statementId))
          .filter((statement): statement is LawStatementRow => statement != null),
        {
          qualityById,
          propositionMatcherStatementIds,
          instrumentKeyByPropositionId,
          compositionContext,
          reviews: loadRunReviewsForQueue(runId),
        },
      ),
    [
      propositionMatcherStatementIds,
      compositionContext,
      filterStatementIds,
      instrumentKeyByPropositionId,
      qualityById,
      reviewTick,
      runId,
      statementById,
    ],
  );

  const traceBlockedHardCaseCount = useMemo(
    () => countTraceBlockedHardCases(samplingContexts),
    [samplingContexts],
  );

  const regenerateQueue = useCallback(() => {
    const nextQueue = buildReviewQueue(
      runId,
      filterStatementIds,
      samplingContexts,
      preset,
      sampleSize,
      seed,
    );
    setQueue(nextQueue);
    saveReviewQueue(runId, nextQueue);
  }, [filterStatementIds, preset, runId, sampleSize, samplingContexts, seed]);

  useEffect(() => {
    const stored = loadReviewQueue(runId);
    if (stored) {
      setPreset(stored.preset);
      setSampleSize(stored.sample_size);
      setSeed(stored.seed);
      setQueue(stored);
    } else {
      setQueue(null);
    }
  }, [runId]);

  const queueWithReviewFlags = useMemo(() => {
    if (!queue) {
      return null;
    }
    return refreshQueueReviewFlags(queue, loadRunReviewsForQueue(runId));
  }, [queue, reviewTick, runId]);

  useEffect(() => {
    if (!queueWithReviewFlags || !queue) {
      return;
    }
    const changed = queueWithReviewFlags.items.some(
      (item, index) => item.already_reviewed !== queue.items[index]?.already_reviewed,
    );
    if (changed) {
      setQueue(queueWithReviewFlags);
      saveReviewQueue(runId, queueWithReviewFlags);
    }
  }, [queue, queueWithReviewFlags, runId]);

  const queueSummary = useMemo(() => {
    if (!queueWithReviewFlags) {
      return null;
    }
    const reviewed = queueWithReviewFlags.items.filter((item) => item.already_reviewed).length;
    return {
      total: queueWithReviewFlags.items.length,
      reviewed,
      unreviewed: queueWithReviewFlags.items.length - reviewed,
    };
  }, [queueWithReviewFlags]);

  const filterChanged =
    queueWithReviewFlags != null &&
    queueWithReviewFlags.filter_statement_ids.join("\n") !==
      [...filterStatementIds].sort().join("\n");

  const handleReviewNext = useCallback(() => {
    const activeQueue =
      queueWithReviewFlags ??
      buildReviewQueue(runId, filterStatementIds, samplingContexts, preset, sampleSize, seed);
    if (!queueWithReviewFlags) {
      setQueue(activeQueue);
      saveReviewQueue(runId, activeQueue);
    }
    const next = findNextUnreviewedQueueItem(activeQueue, currentStatementId);
    if (next) {
      onNavigateToStatement(next.statement_id);
    }
  }, [
    currentStatementId,
    filterStatementIds,
    onNavigateToStatement,
    preset,
    queueWithReviewFlags,
    runId,
    sampleSize,
    samplingContexts,
    seed,
  ]);

  const handleExportManifest = useCallback(() => {
    if (!queueWithReviewFlags) {
      return;
    }
    downloadReviewQueueManifest(buildReviewQueueManifest(runId, queueWithReviewFlags));
  }, [queueWithReviewFlags, runId]);

  return (
    <div className="rw-card flex h-full flex-col">
      <div className="rw-card-header">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="rw-card-title">Review queue</p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Deterministic sampling from the current filter to avoid cherry-picking.
            </p>
          </div>
          {queueSummary ? (
            <div className="flex flex-wrap gap-2 text-[11px]">
              <span className="rw-summary-chip">Queue {queueSummary.total}</span>
              <span className="rw-summary-chip">Reviewed {queueSummary.reviewed}</span>
              <span className="rw-summary-chip">Unreviewed {queueSummary.unreviewed}</span>
            </div>
          ) : null}
        </div>
      </div>

      <div className="rw-card-body flex-1">
        {preset === "trace_blocked_hard_cases" ? (
          <p className="mb-3 text-[11px] text-muted-foreground">
            {traceBlockedHardCaseCount} statement
            {traceBlockedHardCaseCount === 1 ? "" : "s"} in the current filter have export
            composition traces but remain trace-blocked. Queue is priority-ranked (reviewer_required
            first).
          </p>
        ) : null}

        <div className="mb-3 flex flex-wrap gap-2">
          {QUEUE_PRESET_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setPreset(option.value)}
              className={preset === option.value ? "rw-btn-preset-active" : "rw-btn-preset-idle"}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div className="mb-3 grid gap-3 md:grid-cols-3">
          <label className="flex flex-col gap-1 text-xs">
            <span className="uppercase tracking-wide text-muted-foreground">Sample size</span>
            <input
              type="number"
              min={1}
              max={Math.max(1, filterStatementIds.length)}
              value={sampleSize}
              onChange={(event) => setSampleSize(Math.max(1, Number(event.target.value) || 1))}
              className="rounded border border-border/80 bg-background px-2 py-1 outline-none focus:border-navy"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs md:col-span-2">
            <span className="uppercase tracking-wide text-muted-foreground">Seed</span>
            <input
              type="text"
              value={seed}
              onChange={(event) => setSeed(event.target.value)}
              className="rounded border border-border/80 bg-background px-2 py-1 font-mono text-[12px] outline-none focus:border-navy"
            />
          </label>
        </div>

        <div className="mb-3 flex flex-wrap gap-2">
          <button type="button" onClick={regenerateQueue} className="rw-btn-secondary-on-light">
            Regenerate queue
          </button>
          <button type="button" onClick={handleReviewNext} className="rw-btn-primary">
            Review next unreviewed in queue
          </button>
          <button
            type="button"
            onClick={handleExportManifest}
            disabled={!queueWithReviewFlags}
            className="rw-btn-secondary-on-light"
          >
            Export queue manifest JSON
          </button>
        </div>

        {filterChanged ? (
          <p className="mb-3 text-[11px] text-amber-900">
            Current filter differs from the saved queue filter. Regenerate to resample from the active
            filter.
          </p>
        ) : null}

        {queueWithReviewFlags && queueWithReviewFlags.items.length > 0 ? (
          <div className="max-h-56 space-y-1 overflow-y-auto rounded border border-border/70 bg-background p-2">
            {queueWithReviewFlags.items.map((item, index) => {
              const active = item.statement_id === currentStatementId;
              return (
                <button
                  key={`${item.statement_id}-${index}`}
                  type="button"
                  onClick={() => onNavigateToStatement(item.statement_id)}
                  className={`flex w-full flex-col gap-0.5 rounded border px-2 py-1.5 text-left text-[11px] ${
                    active
                      ? "border-navy/70 bg-navy/8"
                      : "border-transparent hover:border-border/70 hover:bg-muted/40"
                  }`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {index + 1}. {item.statement_id}
                    </span>
                    <span className="rw-summary-chip">score {item.priority_score}</span>
                    {item.already_reviewed ? (
                      <span className="rounded border border-emerald-700/35 bg-emerald-950/10 px-1.5 py-0.5 text-emerald-900">
                        reviewed
                      </span>
                    ) : (
                      <span className="rw-summary-chip text-muted-foreground">unreviewed</span>
                    )}
                  </div>
                  <span className="text-muted-foreground">{item.sample_reason}</span>
                  {item.trace_metadata ? (
                    <span className="flex flex-wrap gap-1.5 text-[10px] text-muted-foreground">
                      <span className="rw-summary-chip">
                        {item.trace_metadata.trace_block_reason.replaceAll("_", " ")}
                      </span>
                      <span className="rw-summary-chip">
                        props {item.trace_metadata.proposition_count}
                      </span>
                      <span className="rw-summary-chip">
                        unresolved {item.trace_metadata.unresolved_locator_count}
                      </span>
                      <span className="rw-summary-chip">
                        material {item.trace_metadata.material_context_count}
                      </span>
                      {item.trace_metadata.incorporation_counts.reviewer_required > 0 ? (
                        <span className="rw-chip-warn">reviewer</span>
                      ) : null}
                      {item.trace_metadata.incorporation_counts.should_split > 0 ? (
                        <span className="rounded border border-violet-700/35 bg-violet-950/10 px-1.5 py-0.5 text-violet-950">
                          split
                        </span>
                      ) : null}
                      {item.trace_metadata.incorporation_counts.should_inline > 0 ? (
                        <span className="rounded border border-sky-700/35 bg-sky-950/10 px-1.5 py-0.5 text-sky-950">
                          inline
                        </span>
                      ) : null}
                      <span className="rw-summary-chip font-mono">
                        {item.trace_metadata.source_instrument}
                      </span>
                    </span>
                  ) : null}
                  <span className="font-mono text-[10px] text-muted-foreground/80">
                    {item.sample_bucket}
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <p className="text-[11px] text-muted-foreground">
            No active queue yet. Choose a preset and regenerate to create a reproducible review batch.
          </p>
        )}
      </div>
    </div>
  );
}
