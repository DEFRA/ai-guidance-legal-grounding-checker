"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { ReviewQueuePanel } from "@/components/review-queue-panel";
import { StatementReviewWorkbench } from "@/components/statement-review-workbench";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  shortInstrumentLabel,
  sourceInstrumentFamilyKeyFromSourceRecord,
  type UnknownRecord,
} from "@/components/proposition-explorer-helpers";
import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import {
  assessStatementQuality,
  buildStatementIndexes,
  matchesStatementFilters,
  presentationRoleLabel,
  matchesQualityPreset,
  sortStatements,
  uniqueInstrumentKeysForStatement,
  type LawStatementRow,
  type StatementQualityAssessment,
  type PropositionRow,
  type SourceRow,
  type SourceSnapshotRow,
  type StatementQualityPreset,
  type StatementSortMode,
} from "@/lib/law-statements-index";
import { indexSnapshotsById } from "@/lib/source-version-provenance";
import {
  emptySourceLegalEffectsArtifact,
  parseSourceLegalEffectsArtifact,
  type SourceLegalEffectsArtifactRow,
} from "@/lib/source-legal-effects";
import {
  buildDecisionExplanationIndex,
  emptyDecisionExplanationsArtifact,
  heuristicByRuleId,
  parseDecisionExplanationsResponse,
  parseHeuristicsResponse,
  type DecisionExplanationIndex,
  type HeuristicDefinition,
} from "@/lib/decision-explanations";
import {
  assessReviewCompleteness,
  buildFilterReviewSummary,
  buildWorkbenchReviewExport,
  downloadWorkbenchReviewExport,
  emptyWorkbenchReview,
  FAILURE_STAGE_OPTIONS,
  loadRunWorkbenchReviews,
  STATEMENT_VERDICT_OPTIONS,
  type ReviewStatus,
} from "@/lib/review-workbench-state";
import { RW_CHIP, RW_CHIP_WARN } from "@/lib/review-workbench-ui";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_LAW_PROPOSITION_EXTRACTOR_API_BASE_URL ?? "http://127.0.0.1:8010"
).replace(/\/+$/, "");

const META_CHIP_CLASS = RW_CHIP;

const WARN_CHIP_CLASS = RW_CHIP_WARN;

const INSTRUMENT_CHIP_CLASS =
  "rounded border border-sky-700/35 bg-sky-950/10 px-2 py-0.5 font-mono text-[11px] leading-5 text-sky-950 dark:text-sky-100";

type RunListRow = {
  run_id: string;
  created_at?: string;
  proposition_count?: number | null;
};

type CompletenessRow = {
  proposition_id?: string;
  status?: string;
};

const QUALITY_PRESETS: ReadonlyArray<{
  id: StatementQualityPreset;
  label: string;
}> = [
  { id: "needs_review", label: "Needs review" },
  { id: "incomplete", label: "Incomplete" },
  { id: "unresolved_context", label: "Unresolved context" },
  { id: "high_composition", label: "High composition" },
];

const REVIEW_STATUS_CHIP: Record<ReviewStatus, string> = {
  unreviewed: "border-border/70 text-muted-foreground",
  draft_review: "border-amber-700/35 bg-amber-950/10 text-amber-950 dark:text-amber-100",
  complete_review: "border-emerald-700/35 bg-emerald-950/10 text-emerald-900 dark:text-emerald-100",
};

function countEntries(counts: Record<string, number | undefined>): Array<[string, number]> {
  return Object.entries(counts).filter((entry): entry is [string, number] => (entry[1] ?? 0) > 0);
}

function LawStatementsExplorerInner(): JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [runs, setRuns] = useState<RunListRow[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [statements, setStatements] = useState<LawStatementRow[]>([]);
  const [propositions, setPropositions] = useState<PropositionRow[]>([]);
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [sourceSnapshots, setSourceSnapshots] = useState<SourceSnapshotRow[]>([]);
  const [sourceLegalEffects, setSourceLegalEffects] =
    useState<SourceLegalEffectsArtifactRow | null>(null);
  const [decisionExplanationIndex, setDecisionExplanationIndex] =
    useState<DecisionExplanationIndex | null>(null);
  const [heuristicsById, setHeuristicsById] = useState<Map<string, HeuristicDefinition>>(new Map());
  const [propositionMatcherStatementIds, setPropositionMatcherStatementIds] = useState<Set<string>>(new Set());
  const [completenessByPropositionId, setCompletenessByPropositionId] = useState<Map<string, string>>(
    new Map(),
  );
  const [runsLoading, setRunsLoading] = useState(true);
  const [dataLoading, setDataLoading] = useState(false);
  const [fragmentsLoading, setFragmentsLoading] = useState(false);
  const [sourceFragments, setSourceFragments] = useState<SourceFragmentRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [browseOpen, setBrowseOpen] = useState(false);
  const [reviewTick, setReviewTick] = useState(0);

  const [search, setSearch] = useState("");
  const [presentationRole, setPresentationRole] = useState("");
  const [standaloneStatus, setStandaloneStatus] = useState("");
  const [propositionMatcherOnly, setPropositionMatcherOnly] = useState(false);
  const [qualityPreset, setQualityPreset] = useState<StatementQualityPreset>("needs_review");
  const [minPropositionCount, setMinPropositionCount] = useState(1);
  const [sortMode, setSortMode] = useState<StatementSortMode>("review_priority");

  const selectedStatementId = searchParams.get("stmt")?.trim() ?? "";
  const selectedPropositionId = searchParams.get("prop")?.trim() ?? "";

  const loadRuns = useCallback(async (signal: AbortSignal) => {
    const response = await fetch(`${API_BASE_URL}/ops/runs`, {
      headers: { Accept: "application/json" },
      signal,
    });
    if (!response.ok) {
      throw new Error(`Request failed (${response.status})`);
    }
    const payload = (await response.json()) as { runs?: RunListRow[] };
    return Array.isArray(payload.runs) ? payload.runs : [];
  }, []);

  const loadRunData = useCallback(async (runId: string, signal: AbortSignal) => {
    const [
      statementsRes,
      propositionsRes,
      sourcesRes,
      snapshotsRes,
      sourceLegalEffectsRes,
      decisionExplanationsRes,
      heuristicsRes,
      beatriceRes,
      completenessRes,
    ] = await Promise.all([
      fetch(`${API_BASE_URL}/ops/effective-law-statements?run_id=${encodeURIComponent(runId)}`, {
        headers: { Accept: "application/json" },
        signal,
      }),
      fetch(`${API_BASE_URL}/ops/propositions?run_id=${encodeURIComponent(runId)}`, {
        headers: { Accept: "application/json" },
        signal,
      }),
      fetch(`${API_BASE_URL}/ops/sources?run_id=${encodeURIComponent(runId)}`, {
        headers: { Accept: "application/json" },
        signal,
      }),
      fetch(`${API_BASE_URL}/ops/source-snapshots?run_id=${encodeURIComponent(runId)}`, {
        headers: { Accept: "application/json" },
        signal,
      }),
      fetch(`${API_BASE_URL}/ops/source-legal-effects?run_id=${encodeURIComponent(runId)}`, {
        headers: { Accept: "application/json" },
        signal,
      }),
      fetch(`${API_BASE_URL}/ops/decision-explanations?run_id=${encodeURIComponent(runId)}`, {
        headers: { Accept: "application/json" },
        signal,
      }),
      fetch(
        `${API_BASE_URL}/ops/heuristics?run_id=${encodeURIComponent(runId)}&referenced_only=true`,
        {
          headers: { Accept: "application/json" },
          signal,
        },
      ),
      fetch(`${API_BASE_URL}/ops/proposition-matcher-law-candidates?run_id=${encodeURIComponent(runId)}`, {
        headers: { Accept: "application/json" },
        signal,
      }),
      fetch(
        `${API_BASE_URL}/ops/proposition-completeness-assessments?run_id=${encodeURIComponent(runId)}`,
        {
          headers: { Accept: "application/json" },
          signal,
        },
      ),
    ]);

    if (!statementsRes.ok || !propositionsRes.ok || !sourcesRes.ok) {
      throw new Error("Failed to load law statement artifacts");
    }

    const statementsPayload = (await statementsRes.json()) as {
      effective_law_statements?: { statements?: LawStatementRow[] };
    };
    const propositionsPayload = (await propositionsRes.json()) as {
      propositions?: PropositionRow[];
    };
    const sourcesPayload = (await sourcesRes.json()) as {
      source_records?: SourceRow[];
    };
    // Older exports / older APIs may lack the run-level snapshots route.
    let snapshotRows: SourceSnapshotRow[] = [];
    if (snapshotsRes.ok) {
      const snapshotsPayload = (await snapshotsRes.json()) as {
        source_snapshots?: SourceSnapshotRow[];
      };
      snapshotRows = Array.isArray(snapshotsPayload.source_snapshots)
        ? snapshotsPayload.source_snapshots
        : [];
    }

    // Soft-fail: older APIs/runs without the artifact load as empty/unknown.
    let sourceLegalEffectsArtifact = emptySourceLegalEffectsArtifact(runId);
    if (sourceLegalEffectsRes.ok) {
      try {
        const effectsPayload = await sourceLegalEffectsRes.json();
        sourceLegalEffectsArtifact = parseSourceLegalEffectsArtifact(effectsPayload, runId);
      } catch {
        sourceLegalEffectsArtifact = emptySourceLegalEffectsArtifact(runId);
      }
    }

    // Soft-fail: older APIs/runs without decision explanations remain usable.
    let decisionIndex: DecisionExplanationIndex = buildDecisionExplanationIndex(
      emptyDecisionExplanationsArtifact(runId),
      { artifactPresent: false },
    );
    if (decisionExplanationsRes.ok) {
      try {
        const decisionPayload = await decisionExplanationsRes.json();
        const parsed = parseDecisionExplanationsResponse(decisionPayload, runId);
        decisionIndex = buildDecisionExplanationIndex(parsed.decision_explanations, {
          artifactPresent: parsed.artifact_present,
        });
      } catch {
        decisionIndex = buildDecisionExplanationIndex(emptyDecisionExplanationsArtifact(runId), {
          artifactPresent: false,
        });
      }
    }

    let heuristicsMap = new Map<string, HeuristicDefinition>();
    if (heuristicsRes.ok) {
      try {
        const heuristicsPayload = await heuristicsRes.json();
        heuristicsMap = heuristicByRuleId(parseHeuristicsResponse(heuristicsPayload).heuristics);
      } catch {
        heuristicsMap = new Map();
      }
    }

    const statementRows = Array.isArray(statementsPayload.effective_law_statements?.statements)
      ? statementsPayload.effective_law_statements.statements
      : [];

    let propositionMatcherIds = new Set<string>();
    if (beatriceRes.ok) {
      const beatricePayload = (await beatriceRes.json()) as {
        proposition_matcher_law_candidates?: { candidates?: Array<{ law_statement_id?: string }> };
      };
      const candidates = beatricePayload.proposition_matcher_law_candidates?.candidates;
      if (Array.isArray(candidates)) {
        propositionMatcherIds = new Set(
          candidates
            .map((row) => String(row.law_statement_id ?? "").trim())
            .filter(Boolean),
        );
      }
    }

    const completenessById = new Map<string, string>();
    if (completenessRes.ok) {
      const completenessPayload = (await completenessRes.json()) as {
        proposition_completeness_assessments?: CompletenessRow[];
      };
      const rows = completenessPayload.proposition_completeness_assessments;
      if (Array.isArray(rows)) {
        for (const row of rows) {
          const propositionId = String(row.proposition_id ?? "").trim();
          const status = String(row.status ?? "").trim();
          if (propositionId && status) {
            completenessById.set(propositionId, status);
          }
        }
      }
    }

    return {
      statementRows,
      propositionRows: Array.isArray(propositionsPayload.propositions)
        ? propositionsPayload.propositions
        : [],
      sourceRows: Array.isArray(sourcesPayload.source_records) ? sourcesPayload.source_records : [],
      snapshotRows,
      sourceLegalEffectsArtifact,
      decisionIndex,
      heuristicsMap,
      propositionMatcherIds,
      completenessById,
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setRunsLoading(true);
    setError(null);
    void loadRuns(controller.signal)
      .then((rows) => {
        setRuns(rows);
        setSelectedRunId((current) => current ?? rows[0]?.run_id ?? null);
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Failed to load runs");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setRunsLoading(false);
        }
      });
    return () => controller.abort();
  }, [loadRuns]);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }
    const controller = new AbortController();
    setDataLoading(true);
    setError(null);
    void loadRunData(selectedRunId, controller.signal)
      .then((payload) => {
        setStatements(payload.statementRows);
        setPropositions(payload.propositionRows);
        setSources(payload.sourceRows);
        setSourceSnapshots(payload.snapshotRows);
        setSourceLegalEffects(payload.sourceLegalEffectsArtifact);
        setDecisionExplanationIndex(payload.decisionIndex);
        setHeuristicsById(payload.heuristicsMap);
        setPropositionMatcherStatementIds(payload.propositionMatcherIds);
        setCompletenessByPropositionId(payload.completenessById);
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Failed to load statements");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setDataLoading(false);
        }
      });
    return () => controller.abort();
  }, [loadRunData, selectedRunId]);

  const indexes = useMemo(() => buildStatementIndexes(statements), [statements]);
  const propositionById = useMemo(
    () => new Map(propositions.map((row) => [row.id, row])),
    [propositions],
  );
  const sourceById = useMemo(() => new Map(sources.map((row) => [row.id, row])), [sources]);
  const snapshotById = useMemo(
    () => indexSnapshotsById(sourceSnapshots, selectedRunId),
    [selectedRunId, sourceSnapshots],
  );
  const fragmentById = useMemo(() => {
    const map = new Map<string, SourceFragmentRow>();
    for (const fragment of sourceFragments) {
      const id = String(fragment.id ?? fragment.fragment_id ?? "").trim();
      if (id) {
        map.set(id, fragment);
      }
    }
    return map;
  }, [sourceFragments]);

  const instrumentKeyByPropositionId = useMemo(() => {
    const map = new Map<string, string>();
    for (const proposition of propositions) {
      const source = proposition.source_record_id
        ? sourceById.get(proposition.source_record_id)
        : undefined;
      map.set(
        proposition.id,
        source
          ? sourceInstrumentFamilyKeyFromSourceRecord(source as UnknownRecord)
          : "__unknown_instrument__",
      );
    }
    return map;
  }, [propositions, sourceById]);

  const instrumentLabelByKey = useMemo(() => {
    const map = new Map<string, string>();
    for (const source of sources) {
      const key = sourceInstrumentFamilyKeyFromSourceRecord(source as UnknownRecord);
      if (!map.has(key)) {
        map.set(key, shortInstrumentLabel(source as UnknownRecord));
      }
    }
    return map;
  }, [sources]);

  const qualityById = useMemo(() => {
    const map = new Map<string, StatementQualityAssessment>();
    for (const statement of statements) {
      map.set(
        statement.id,
        assessStatementQuality(statement, {
          minHighCompositionCount: 3,
          sourceCompletenessByPropositionId: completenessByPropositionId,
        }),
      );
    }
    return map;
  }, [statements, completenessByPropositionId]);

  const qualitySummary = useMemo(() => {
    const counts: Record<StatementQualityPreset, number> = {
      "": statements.length,
      needs_review: 0,
      incomplete: 0,
      unresolved_context: 0,
      high_composition: 0,
    };
    for (const statement of statements) {
      const assessment = qualityById.get(statement.id);
      if (!assessment) {
        continue;
      }
      for (const preset of QUALITY_PRESETS) {
        if (matchesQualityPreset(assessment, preset.id)) {
          counts[preset.id] += 1;
        }
      }
    }
    return counts;
  }, [statements, qualityById]);

  const filteredStatements = useMemo(() => {
    const filters = {
      search,
      presentationRole,
      standaloneStatus,
      propositionMatcherOnly,
      propositionMatcherStatementIds,
      qualityPreset,
      minPropositionCount,
      qualityById,
    };
    const filtered = statements.filter((statement) => matchesStatementFilters(statement, filters));
    return sortStatements(filtered, sortMode, qualityById);
  }, [
    statements,
    search,
    presentationRole,
    standaloneStatus,
    propositionMatcherOnly,
    propositionMatcherStatementIds,
    qualityPreset,
    minPropositionCount,
    qualityById,
    sortMode,
  ]);

  const selectedStatement = useMemo(() => {
    if (selectedStatementId) {
      return indexes.statementsById.get(selectedStatementId) ?? null;
    }
    if (selectedPropositionId) {
      return indexes.statementsByPropositionId.get(selectedPropositionId)?.[0] ?? null;
    }
    return filteredStatements[0] ?? null;
  }, [
    filteredStatements,
    indexes.statementsById,
    indexes.statementsByPropositionId,
    selectedPropositionId,
    selectedStatementId,
  ]);

  const selectedStatementQuality = useMemo(() => {
    if (!selectedStatement) {
      return null;
    }
    return qualityById.get(selectedStatement.id) ?? null;
  }, [qualityById, selectedStatement]);

  const selectedIndex = useMemo(() => {
    if (!selectedStatement) {
      return -1;
    }
    return filteredStatements.findIndex((statement) => statement.id === selectedStatement.id);
  }, [filteredStatements, selectedStatement]);

  const filterStatementIds = useMemo(
    () => filteredStatements.map((statement) => statement.id),
    [filteredStatements],
  );

  const reviewSummary = useMemo(() => {
    void reviewTick;
    if (!selectedRunId) {
      return buildFilterReviewSummary(filterStatementIds, {});
    }
    return buildFilterReviewSummary(filterStatementIds, loadRunWorkbenchReviews(selectedRunId));
  }, [filterStatementIds, reviewTick, selectedRunId]);

  const presentationRoles = useMemo(() => {
    const values = new Set(statements.map((row) => row.presentation_role).filter(Boolean));
    return Array.from(values).sort();
  }, [statements]);

  const standaloneStatuses = useMemo(() => {
    const values = new Set(statements.map((row) => row.standalone_status).filter(Boolean));
    return Array.from(values).sort();
  }, [statements]);

  useEffect(() => {
    if (!selectedRunId || !selectedStatement) {
      setSourceFragments([]);
      return;
    }

    const sourceRecordIds = new Set<string>();
    for (const propositionId of [
      ...(selectedStatement.source_proposition_ids ?? []),
      ...(selectedStatement.supporting_proposition_ids ?? []),
    ]) {
      const sourceRecordId = propositionById.get(propositionId)?.source_record_id?.trim();
      if (sourceRecordId) {
        sourceRecordIds.add(sourceRecordId);
      }
    }
    for (const ctx of selectedStatement.required_context ?? []) {
      for (const propositionId of ctx.proposition_ids ?? []) {
        const sourceRecordId = propositionById.get(propositionId)?.source_record_id?.trim();
        if (sourceRecordId) {
          sourceRecordIds.add(sourceRecordId);
        }
      }
    }
    for (const ctx of selectedStatement.connector_context ?? []) {
      for (const propositionId of [
        ...(ctx.proposition_ids ?? []),
        ...(ctx.via_proposition_ids ?? []),
        ...(ctx.target_proposition_ids ?? []),
      ]) {
        const sourceRecordId = propositionById.get(propositionId)?.source_record_id?.trim();
        if (sourceRecordId) {
          sourceRecordIds.add(sourceRecordId);
        }
      }
    }

    if (sourceRecordIds.size === 0) {
      setSourceFragments([]);
      return;
    }

    const controller = new AbortController();
    setFragmentsLoading(true);
    void Promise.all(
      Array.from(sourceRecordIds).map(async (sourceRecordId) => {
        const response = await fetch(
          `${API_BASE_URL}/ops/source-fragments?run_id=${encodeURIComponent(selectedRunId)}&source_record_id=${encodeURIComponent(sourceRecordId)}`,
          {
            headers: { Accept: "application/json" },
            signal: controller.signal,
          },
        );
        if (!response.ok) {
          return [] as SourceFragmentRow[];
        }
        const payload = (await response.json()) as { source_fragments?: SourceFragmentRow[] };
        return Array.isArray(payload.source_fragments) ? payload.source_fragments : [];
      }),
    )
      .then((groups) => {
        setSourceFragments(groups.flat());
      })
      .catch((loadError: unknown) => {
        if (!controller.signal.aborted) {
          setError(
            loadError instanceof Error ? loadError.message : "Failed to load source fragments",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setFragmentsLoading(false);
        }
      });

    return () => controller.abort();
  }, [propositionById, selectedRunId, selectedStatement]);

  const setUrlSelection = useCallback(
    (next: { stmt?: string; prop?: string }) => {
      const params = new URLSearchParams(searchParams.toString());
      if (next.stmt) {
        params.set("stmt", next.stmt);
        params.delete("prop");
      } else if (next.prop) {
        params.set("prop", next.prop);
        params.delete("stmt");
      } else {
        params.delete("stmt");
        params.delete("prop");
      }
      const query = params.toString();
      router.replace(query ? `/statements?${query}` : "/statements", { scroll: false });
    },
    [router, searchParams],
  );

  const goToStatementAtIndex = useCallback(
    (index: number) => {
      const target = filteredStatements[index];
      if (target) {
        setUrlSelection({ stmt: target.id });
        setReviewTick((tick) => tick + 1);
      }
    },
    [filteredStatements, setUrlSelection],
  );

  const handleNext = useCallback(() => {
    if (selectedIndex < 0) {
      return;
    }
    goToStatementAtIndex(Math.min(selectedIndex + 1, filteredStatements.length - 1));
  }, [filteredStatements.length, goToStatementAtIndex, selectedIndex]);

  const handlePrevious = useCallback(() => {
    if (selectedIndex < 0) {
      return;
    }
    goToStatementAtIndex(Math.max(selectedIndex - 1, 0));
  }, [goToStatementAtIndex, selectedIndex]);

  const handleExportAll = useCallback(() => {
    if (!selectedRunId) {
      return;
    }
    const payload = buildWorkbenchReviewExport(
      selectedRunId,
      loadRunWorkbenchReviews(selectedRunId),
      filterStatementIds,
    );
    downloadWorkbenchReviewExport(payload);
  }, [filterStatementIds, selectedRunId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (event.key === "j" || event.key === "ArrowRight") {
        event.preventDefault();
        handleNext();
      } else if (event.key === "k" || event.key === "ArrowLeft") {
        event.preventDefault();
        handlePrevious();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleNext, handlePrevious]);

  useEffect(() => {
    const onStorage = () => setReviewTick((tick) => tick + 1);
    window.addEventListener("storage", onStorage);
    const interval = window.setInterval(() => setReviewTick((tick) => tick + 1), 2000);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.clearInterval(interval);
    };
  }, []);

  return (
    <div className="space-y-4">
      <div className="rw-card">
        <div className="rw-card-header">
          <p className="rw-card-title">Run</p>
        </div>
        <div className="rw-card-body">
          <label className="flex max-w-md flex-col gap-1 text-xs">
            <span className="uppercase tracking-wide text-muted-foreground">Export run</span>
            <select
              value={selectedRunId ?? ""}
              onChange={(event) => setSelectedRunId(event.target.value || null)}
              className="rounded border border-border/80 bg-background px-2 py-1 outline-none focus:border-navy"
            >
              {runs.map((run) => (
                <option key={run.run_id} value={run.run_id}>
                  {run.run_id}
                  {run.proposition_count != null ? ` (${run.proposition_count} props)` : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rw-card">
          <div className="rw-card-header">
            <p className="rw-card-title">Review quality summary (current filter)</p>
          </div>
          <div className="rw-card-body">
            <div className="flex flex-wrap gap-2 text-[11px]">
              <span className="rw-summary-chip">Total {reviewSummary.total_in_filter}</span>
              <span className="rw-summary-chip">Reviewed {reviewSummary.reviewed}</span>
              <span className={`rw-summary-chip ${REVIEW_STATUS_CHIP.complete_review}`}>
                Complete {reviewSummary.complete}
              </span>
              <span className={`rw-summary-chip ${REVIEW_STATUS_CHIP.draft_review}`}>
                Draft {reviewSummary.draft}
              </span>
              <span className={`rw-summary-chip ${REVIEW_STATUS_CHIP.unreviewed}`}>
                Unreviewed {reviewSummary.unreviewed}
              </span>
            </div>
            {countEntries(reviewSummary.verdict_counts).length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                <span className="text-muted-foreground">Verdicts:</span>
                {STATEMENT_VERDICT_OPTIONS.map((option) => {
                  const count = reviewSummary.verdict_counts[option.value] ?? 0;
                  if (count === 0) {
                    return null;
                  }
                  return (
                    <span key={option.value} className="rw-summary-chip">
                      {option.label} {count}
                    </span>
                  );
                })}
              </div>
            ) : null}
            {countEntries(reviewSummary.failure_stage_counts).length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                <span className="text-muted-foreground">Failure stages:</span>
                {FAILURE_STAGE_OPTIONS.map((option) => {
                  const count = reviewSummary.failure_stage_counts[option.value] ?? 0;
                  if (count === 0) {
                    return null;
                  }
                  return (
                    <span key={option.value} className="rw-summary-chip">
                      {option.label} {count}
                    </span>
                  );
                })}
              </div>
            ) : null}
            {countEntries(reviewSummary.severity_counts).length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                <span className="text-muted-foreground">Severity:</span>
                {countEntries(reviewSummary.severity_counts).map(([severity, count]) => (
                  <span key={severity} className="rw-summary-chip">
                    {severity} {count}
                  </span>
                ))}
              </div>
            ) : null}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button type="button" onClick={handleExportAll} className="rw-btn-secondary-on-light">
                Export reviews JSON
              </button>
              {reviewSummary.draft > 0 ? (
                <span className="text-[10px] text-amber-900">
                  Export includes {reviewSummary.draft} draft review
                  {reviewSummary.draft === 1 ? "" : "s"} (marked draft_review in JSON).
                </span>
              ) : null}
            </div>
          </div>
        </div>

        {selectedRunId ? (
          <ReviewQueuePanel
            runId={selectedRunId}
            filterStatementIds={filterStatementIds}
            statements={statements}
            propositions={propositions}
            sources={sources}
            sourceFragments={sourceFragments}
            completenessByPropositionId={completenessByPropositionId}
            qualityById={qualityById}
            propositionMatcherStatementIds={propositionMatcherStatementIds}
            instrumentKeyByPropositionId={instrumentKeyByPropositionId}
            currentStatementId={selectedStatement?.id}
            reviewTick={reviewTick}
            onNavigateToStatement={(statementId) => setUrlSelection({ stmt: statementId })}
          />
        ) : (
          <div className="rw-card">
            <div className="rw-card-header">
              <p className="rw-card-title">Review queue</p>
            </div>
            <div className="rw-card-body">
              <p className="text-[11px] text-muted-foreground">Select a run to configure the review queue.</p>
            </div>
          </div>
        )}
      </div>

      {runsLoading || dataLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : null}

      {error ? (
        <Card className="border-destructive/40">
          <CardHeader>
            <CardTitle className="text-base text-destructive">Unable to load statements</CardTitle>
            <CardDescription>
              Confirm the API is running and the export includes effective law artifacts.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <code className="text-sm text-destructive">{error}</code>
          </CardContent>
        </Card>
      ) : null}

      {!runsLoading && !dataLoading && !error ? (
        <>
          {selectedStatement && selectedRunId ? (
            <div className="rw-card overflow-hidden">
              {fragmentsLoading ? (
                <p className="border-b border-border/60 px-4 py-2 text-sm text-muted-foreground">
                  Loading source fragments…
                </p>
              ) : null}
              <StatementReviewWorkbench
                runId={selectedRunId}
                apiBaseUrl={API_BASE_URL}
                statement={selectedStatement}
                quality={selectedStatementQuality}
                isPropositionMatcherCandidate={propositionMatcherStatementIds.has(selectedStatement.id)}
                propositionById={propositionById}
                sourceById={sourceById}
                snapshotById={snapshotById}
                fragmentById={fragmentById}
                sourceFragments={sourceFragments}
                sourceLegalEffects={sourceLegalEffects}
                decisionExplanationIndex={decisionExplanationIndex}
                heuristicsById={heuristicsById}
                sourceCompletenessByPropositionId={completenessByPropositionId}
                filterStatementIds={filterStatementIds}
                onNext={selectedIndex < filteredStatements.length - 1 ? handleNext : undefined}
                onPrevious={selectedIndex > 0 ? handlePrevious : undefined}
                positionLabel={
                  selectedIndex >= 0
                    ? `Statement ${selectedIndex + 1} of ${filteredStatements.length}`
                    : undefined
                }
              />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No statement selected.</p>
          )}

          <div className="rw-card">
            <button
              type="button"
              onClick={() => setBrowseOpen((open) => !open)}
              className="flex w-full items-center justify-between px-6 py-4 text-left"
            >
              <div>
                <p className="text-base font-semibold">Browse</p>
                <p className="text-sm text-muted-foreground">
                  Filters and statement list ({filteredStatements.length} of {statements.length})
                </p>
              </div>
              <span className="text-muted-foreground">{browseOpen ? "▲" : "▼"}</span>
            </button>
            {browseOpen ? (
              <div className="space-y-4 border-t border-border/70 px-6 pb-6 pt-4">
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setQualityPreset("")}
                    className={qualityPreset === "" ? "rw-btn-preset-active" : "rw-btn-preset-idle"}
                  >
                    All ({statements.length})
                  </button>
                  {QUALITY_PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => setQualityPreset(preset.id)}
                      className={
                        qualityPreset === preset.id ? "rw-btn-preset-active" : "rw-btn-preset-idle"
                      }
                    >
                      {preset.label} ({qualitySummary[preset.id]})
                    </button>
                  ))}
                </div>

                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                  <label className="flex flex-col gap-1 text-xs">
                    <span className="uppercase tracking-wide text-muted-foreground">
                      Presentation role
                    </span>
                    <select
                      value={presentationRole}
                      onChange={(event) => setPresentationRole(event.target.value)}
                      className="rounded border border-border/80 px-2 py-1 outline-none focus:border-primary"
                    >
                      <option value="">(any)</option>
                      {presentationRoles.map((role) => (
                        <option key={role} value={role}>
                          {presentationRoleLabel(role)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1 text-xs">
                    <span className="uppercase tracking-wide text-muted-foreground">
                      Standalone status
                    </span>
                    <select
                      value={standaloneStatus}
                      onChange={(event) => setStandaloneStatus(event.target.value)}
                      className="rounded border border-border/80 px-2 py-1 outline-none focus:border-primary"
                    >
                      <option value="">(any)</option>
                      {standaloneStatuses.map((status) => (
                        <option key={status} value={status}>
                          {status.replaceAll("_", " ")}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1 text-xs">
                    <span className="uppercase tracking-wide text-muted-foreground">Search</span>
                    <input
                      type="search"
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Statement text, id, proposition id…"
                      className="rounded border border-border/80 px-2 py-1.5 text-[12px] outline-none focus:border-primary"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs">
                    <span className="uppercase tracking-wide text-muted-foreground">
                      Min propositions
                    </span>
                    <select
                      value={String(minPropositionCount)}
                      onChange={(event) => setMinPropositionCount(Number(event.target.value))}
                      className="rounded border border-border/80 px-2 py-1 outline-none focus:border-primary"
                    >
                      <option value="1">(any)</option>
                      <option value="2">2+</option>
                      <option value="3">3+</option>
                      <option value="4">4+</option>
                      <option value="5">5+</option>
                    </select>
                  </label>
                  <label className="flex flex-col gap-1 text-xs">
                    <span className="uppercase tracking-wide text-muted-foreground">Sort</span>
                    <select
                      value={sortMode}
                      onChange={(event) => setSortMode(event.target.value as StatementSortMode)}
                      className="rounded border border-border/80 px-2 py-1 outline-none focus:border-primary"
                    >
                      <option value="review_priority">Review priority</option>
                      <option value="proposition_count">Proposition count</option>
                      <option value="text">Statement text</option>
                    </select>
                  </label>
                </div>

                <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={propositionMatcherOnly}
                    onChange={(event) => setPropositionMatcherOnly(event.target.checked)}
                    className="rounded border-border accent-primary"
                  />
                  Proposition Matcher guidance-matching candidates only ({propositionMatcherStatementIds.size})
                </label>

                <div className="max-h-[50vh] space-y-2 overflow-y-auto">
                  {filteredStatements.map((statement) => {
                    const active = selectedStatement?.id === statement.id;
                    const quality = qualityById.get(statement.id);
                    const instrumentKeys = uniqueInstrumentKeysForStatement(
                      statement,
                      instrumentKeyByPropositionId,
                    );
                    const reviewStatus = selectedRunId
                      ? assessReviewCompleteness(
                          loadRunWorkbenchReviews(selectedRunId)[statement.id] ??
                            emptyWorkbenchReview(),
                        ).status
                      : "unreviewed";
                    return (
                      <button
                        key={statement.id}
                        type="button"
                        onClick={() => setUrlSelection({ stmt: statement.id })}
                        className={`w-full rounded-md border px-3 py-2 text-left transition ${
                          active
                            ? "border-navy/70 bg-navy/8"
                            : quality && quality.reviewScore > 0
                              ? "border-amber-700/25 bg-amber-950/[0.04] hover:bg-amber-950/[0.08]"
                              : "border-border/80 bg-background hover:bg-muted/40"
                        }`}
                      >
                        <div className="mb-1 flex flex-wrap gap-2">
                          <span className={META_CHIP_CLASS}>
                            {presentationRoleLabel(statement.presentation_role)}
                          </span>
                          <span className={META_CHIP_CLASS}>{statement.standalone_status}</span>
                          {reviewStatus !== "unreviewed" ? (
                            <span
                              className={`rounded border px-2 py-0.5 text-[10px] font-medium ${REVIEW_STATUS_CHIP[reviewStatus]}`}
                            >
                              {reviewStatus === "complete_review" ? "Complete" : "Draft"}
                            </span>
                          ) : null}
                          {quality && quality.uniquePropositionCount > 1 ? (
                            <span className={WARN_CHIP_CLASS}>
                              {quality.uniquePropositionCount} props
                            </span>
                          ) : null}
                          {quality && quality.reviewScore > 0 ? (
                            <span className={WARN_CHIP_CLASS}>score {quality.reviewScore}</span>
                          ) : null}
                          {propositionMatcherStatementIds.has(statement.id) ? (
                            <span className={META_CHIP_CLASS}>Proposition Matcher</span>
                          ) : null}
                          {instrumentKeys.map((instrumentKey) => (
                            <span key={instrumentKey} className={INSTRUMENT_CHIP_CLASS}>
                              {instrumentLabelByKey.get(instrumentKey) ?? instrumentKey}
                            </span>
                          ))}
                        </div>
                        {quality && quality.issueLabels.length > 0 ? (
                          <p className="mb-1 text-[11px] text-amber-950 dark:text-amber-100">
                            {quality.issueLabels.join(" · ")}
                          </p>
                        ) : null}
                        <p className="text-sm leading-snug text-foreground">
                          {statement.statement_text}
                        </p>
                        <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                          {statement.id}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}

export function LawStatementsExplorer(): JSX.Element {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Loading statements…</p>}>
      <LawStatementsExplorerInner />
    </Suspense>
  );
}
