"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  shortInstrumentLabel,
  sourceInstrumentFamilyKeyFromSourceRecord,
  type UnknownRecord,
} from "@/components/proposition-explorer-helpers";
import type { LawStatementRow, PropositionRow, SourceRow } from "@/lib/law-statements-index";
import {
  buildReviewAnalysis,
  buildReviewAnalysisEnrichment,
  parseQueueManifest,
  parseReviewExport,
  type ReviewAnalysisFilters,
  type ReviewAnalysisResult,
  type ReviewCaseRow,
} from "@/lib/review-workbench-analysis";
import type { ReviewQueueManifest } from "@/lib/review-workbench-queue";
import {
  FAILURE_STAGE_OPTIONS,
  STATEMENT_VERDICT_OPTIONS,
  type WorkbenchReviewExport,
} from "@/lib/review-workbench-state";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_LAW_PROPOSITION_EXTRACTOR_API_BASE_URL ?? "http://127.0.0.1:8010"
).replace(/\/+$/, "");

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function readJsonFile(file: File): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        resolve(JSON.parse(String(reader.result ?? "")));
      } catch (error) {
        reject(error);
      }
    };
    reader.onerror = () => reject(reader.error ?? new Error("Failed to read file"));
    reader.readAsText(file);
  });
}

function RateTable(props: {
  title: string;
  rows: ReviewAnalysisResult["summary"]["rates_by_sample_bucket"];
  bucketLabel?: string;
}): JSX.Element | null {
  const { title, rows, bucketLabel = "Bucket" } = props;
  if (rows.length === 0) {
    return null;
  }
  return (
    <div className="rounded-lg border border-border/75 bg-muted/[0.08] p-3">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        {title}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[28rem] text-left text-[11px]">
          <thead>
            <tr className="border-b border-border/70 text-muted-foreground">
              <th className="px-2 py-1 font-medium">{bucketLabel}</th>
              <th className="px-2 py-1 font-medium">Total</th>
              <th className="px-2 py-1 font-medium">Reviewed</th>
              <th className="px-2 py-1 font-medium">Issue rate</th>
              <th className="px-2 py-1 font-medium">Verdict rates</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.bucket} className="border-b border-border/50 align-top">
                <td className="px-2 py-1 font-mono text-[10px]">{row.bucket}</td>
                <td className="px-2 py-1">{row.total}</td>
                <td className="px-2 py-1">{row.reviewed}</td>
                <td className="px-2 py-1">{pct(row.issue_rate)}</td>
                <td className="px-2 py-1">
                  <div className="flex flex-wrap gap-1">
                    {STATEMENT_VERDICT_OPTIONS.map((option) => {
                      const rate = row.verdict_rates[option.value];
                      if (rate == null) {
                        return null;
                      }
                      return (
                        <span
                          key={`${row.bucket}-${option.value}`}
                          className="rounded border border-border/70 px-1 py-0.5"
                        >
                          {option.label} {pct(rate)}
                        </span>
                      );
                    })}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CaseTable(props: {
  title: string;
  description: string;
  rows: ReviewCaseRow[];
  instrumentLabels: Map<string, string>;
}): JSX.Element {
  const { title, description, rows, instrumentLabels } = props;
  return (
    <div className="rounded-lg border border-border/75 bg-background/70 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        {title}
      </p>
      <p className="mb-2 text-[11px] text-muted-foreground">{description}</p>
      {rows.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">No matching cases in the current filter.</p>
      ) : (
        <div className="max-h-64 overflow-auto">
          <table className="w-full min-w-[36rem] text-left text-[11px]">
            <thead>
              <tr className="border-b border-border/70 text-muted-foreground">
                <th className="px-2 py-1 font-medium">Statement</th>
                <th className="px-2 py-1 font-medium">Status</th>
                <th className="px-2 py-1 font-medium">Verdicts</th>
                <th className="px-2 py-1 font-medium">Severity</th>
                <th className="px-2 py-1 font-medium">Failure stages</th>
                <th className="px-2 py-1 font-medium">Instrument</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.statement_id} className="border-b border-border/50 align-top">
                  <td className="px-2 py-1 font-mono text-[10px]">{row.statement_id}</td>
                  <td className="px-2 py-1">{row.review_status.replaceAll("_", " ")}</td>
                  <td className="px-2 py-1">{row.verdicts.join(", ") || "—"}</td>
                  <td className="px-2 py-1">{row.severity || "—"}</td>
                  <td className="px-2 py-1">{row.failure_stages.join(", ") || "—"}</td>
                  <td className="px-2 py-1">
                    {instrumentLabels.get(row.instrument) ?? row.instrument}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function ReviewAnalysisPanel(): JSX.Element {
  const [reviewExport, setReviewExport] = useState<WorkbenchReviewExport | null>(null);
  const [queueManifest, setQueueManifest] = useState<ReviewQueueManifest | null>(null);
  const [statements, setStatements] = useState<LawStatementRow[]>([]);
  const [propositions, setPropositions] = useState<PropositionRow[]>([]);
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [propositionMatcherCandidateIds, setPropositionMatcherCandidateIds] = useState<Set<string>>(new Set());
  const [parseError, setParseError] = useState<string | null>(null);
  const [contextError, setContextError] = useState<string | null>(null);
  const [contextLoading, setContextLoading] = useState(false);
  const [filters, setFilters] = useState<ReviewAnalysisFilters>({
    includeDrafts: false,
    queueOnly: false,
    exportReviewsOnly: true,
  });

  const handleReviewUpload = useCallback(async (file: File | null) => {
    if (!file) {
      return;
    }
    setParseError(null);
    try {
      const payload = await readJsonFile(file);
      setReviewExport(parseReviewExport(payload));
    } catch (error) {
      setReviewExport(null);
      setParseError(error instanceof Error ? error.message : "Invalid review export JSON");
    }
  }, []);

  const handleQueueUpload = useCallback(async (file: File | null) => {
    if (!file) {
      return;
    }
    setParseError(null);
    try {
      const payload = await readJsonFile(file);
      setQueueManifest(parseQueueManifest(payload));
    } catch (error) {
      setQueueManifest(null);
      setParseError(error instanceof Error ? error.message : "Invalid queue manifest JSON");
    }
  }, []);

  const loadRunContext = useCallback(async (runId: string) => {
    setContextLoading(true);
    setContextError(null);
    try {
      const [statementsRes, propositionsRes, sourcesRes, beatriceRes] = await Promise.all([
        fetch(`${API_BASE_URL}/ops/effective-law-statements?run_id=${encodeURIComponent(runId)}`, {
          headers: { Accept: "application/json" },
        }),
        fetch(`${API_BASE_URL}/ops/propositions?run_id=${encodeURIComponent(runId)}`, {
          headers: { Accept: "application/json" },
        }),
        fetch(`${API_BASE_URL}/ops/sources?run_id=${encodeURIComponent(runId)}`, {
          headers: { Accept: "application/json" },
        }),
        fetch(`${API_BASE_URL}/ops/proposition-matcher-law-candidates?run_id=${encodeURIComponent(runId)}`, {
          headers: { Accept: "application/json" },
        }),
      ]);

      if (!statementsRes.ok || !propositionsRes.ok || !sourcesRes.ok) {
        throw new Error("Failed to load run context from API");
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

      setStatements(
        Array.isArray(statementsPayload.effective_law_statements?.statements)
          ? statementsPayload.effective_law_statements.statements
          : [],
      );
      setPropositions(
        Array.isArray(propositionsPayload.propositions) ? propositionsPayload.propositions : [],
      );
      setSources(
        Array.isArray(sourcesPayload.source_records) ? sourcesPayload.source_records : [],
      );

      if (beatriceRes.ok) {
        const beatricePayload = (await beatriceRes.json()) as {
          proposition_matcher_law_candidates?: { candidates?: Array<{ law_statement_id?: string }> };
        };
        const candidates = beatricePayload.proposition_matcher_law_candidates?.candidates;
        setPropositionMatcherCandidateIds(
          new Set(
            Array.isArray(candidates)
              ? candidates
                  .map((row) => String(row.law_statement_id ?? "").trim())
                  .filter(Boolean)
              : [],
          ),
        );
      } else {
        setPropositionMatcherCandidateIds(new Set());
      }
    } catch (error) {
      setContextError(error instanceof Error ? error.message : "Failed to load run context");
    } finally {
      setContextLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!reviewExport?.run_id) {
      return;
    }
    void loadRunContext(reviewExport.run_id);
  }, [loadRunContext, reviewExport?.run_id]);

  const instrumentKeyByPropositionId = useMemo(() => {
    const sourceById = new Map(sources.map((source) => [source.id, source]));
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
  }, [propositions, sources]);

  const instrumentLabels = useMemo(() => {
    const map = new Map<string, string>();
    for (const source of sources) {
      const key = sourceInstrumentFamilyKeyFromSourceRecord(source as UnknownRecord);
      if (!map.has(key)) {
        map.set(key, shortInstrumentLabel(source as UnknownRecord));
      }
    }
    return map;
  }, [sources]);

  const enrichment = useMemo(
    () =>
      buildReviewAnalysisEnrichment({
        statements,
        instrumentKeyByPropositionId,
        propositionMatcherCandidateIds,
        queueManifest,
      }),
    [propositionMatcherCandidateIds, instrumentKeyByPropositionId, queueManifest, statements],
  );

  const analysis = useMemo(() => {
    if (!reviewExport) {
      return null;
    }
    return buildReviewAnalysis(reviewExport, {
      queueManifest,
      enrichment,
      filters,
    });
  }, [enrichment, filters, queueManifest, reviewExport]);

  const updateFilter = useCallback(
    (patch: Partial<ReviewAnalysisFilters>) => {
      setFilters((current) => ({ ...current, ...patch }));
    },
    [],
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Import review exports</CardTitle>
          <CardDescription>
            Upload review workbench export JSON (schema v3) and optionally a queue manifest JSON
            (schema v1). Run context for instrument and Proposition Matcher enrichment loads automatically when
            the API is available.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs">
              <span className="uppercase tracking-wide text-muted-foreground">
                Review export JSON (required)
              </span>
              <input
                type="file"
                accept="application/json,.json"
                onChange={(event) => void handleReviewUpload(event.target.files?.[0] ?? null)}
                className="text-[11px]"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="uppercase tracking-wide text-muted-foreground">
                Queue manifest JSON (optional)
              </span>
              <input
                type="file"
                accept="application/json,.json"
                onChange={(event) => void handleQueueUpload(event.target.files?.[0] ?? null)}
                className="text-[11px]"
              />
            </label>
          </div>

          {reviewExport ? (
            <div className="flex flex-wrap gap-2 text-[11px]">
              <span className="rounded border border-border/70 px-2 py-0.5">
                Run {reviewExport.run_id}
              </span>
              <span className="rounded border border-border/70 px-2 py-0.5">
                Exported {reviewExport.exported_at.slice(0, 10)}
              </span>
              <span className="rounded border border-border/70 px-2 py-0.5">
                Reviews in file {reviewExport.reviews.length}
              </span>
              <span className="rounded border border-border/70 px-2 py-0.5">
                Filter scope {reviewExport.filter_statement_ids.length}
              </span>
              {queueManifest ? (
                <span className="rounded border border-border/70 px-2 py-0.5">
                  Queue {queueManifest.items.length} ({queueManifest.preset})
                </span>
              ) : null}
            </div>
          ) : null}

          {parseError ? <p className="text-sm text-destructive">{parseError}</p> : null}
          {contextLoading ? (
            <p className="text-[11px] text-muted-foreground">Loading run context…</p>
          ) : null}
          {contextError ? (
            <p className="text-[11px] text-amber-950 dark:text-amber-100">
              Run context unavailable: {contextError}. Instrument / Proposition Matcher breakdowns may be
              partial; upload a queue manifest for sample buckets.
            </p>
          ) : null}
        </CardContent>
      </Card>

      {analysis ? (
        <>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Analysis filters</CardTitle>
              <CardDescription>Adjust which reviews are included in the summary.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-4 text-[11px]">
              <fieldset className="flex flex-wrap items-center gap-3">
                <legend className="sr-only">Review status filter</legend>
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="review-status-filter"
                    checked={!filters.includeDrafts}
                    onChange={() => updateFilter({ includeDrafts: false })}
                  />
                  Complete reviews only
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="review-status-filter"
                    checked={filters.includeDrafts}
                    onChange={() => updateFilter({ includeDrafts: true })}
                  />
                  Include drafts
                </label>
              </fieldset>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={filters.queueOnly}
                  disabled={!queueManifest}
                  onChange={(event) => updateFilter({ queueOnly: event.target.checked })}
                />
                Queue only
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={filters.exportReviewsOnly}
                  onChange={(event) => updateFilter({ exportReviewsOnly: event.target.checked })}
                />
                Current uploaded export only
              </label>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2 text-[11px]">
                <span className="rounded border border-border/70 px-2 py-0.5">
                  Scope {analysis.summary.scope_total}
                </span>
                <span className="rounded border border-border/70 px-2 py-0.5">
                  Reviewed {analysis.summary.reviewed}
                </span>
                <span className="rounded border border-emerald-700/35 bg-emerald-950/10 px-2 py-0.5 text-emerald-900 dark:text-emerald-100">
                  Complete {analysis.summary.complete}
                </span>
                <span className="rounded border border-amber-700/35 bg-amber-950/10 px-2 py-0.5 text-amber-950 dark:text-amber-100">
                  Draft {analysis.summary.draft}
                </span>
                <span className="rounded border border-border/70 px-2 py-0.5 text-muted-foreground">
                  Unreviewed {analysis.summary.unreviewed}
                </span>
              </div>

              <div className="grid gap-3 lg:grid-cols-2">
                <div className="rounded-lg border border-border/75 bg-muted/[0.08] p-3">
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Verdict rates
                  </p>
                  <div className="flex flex-wrap gap-1.5 text-[11px]">
                    {STATEMENT_VERDICT_OPTIONS.map((option) => {
                      const rate = analysis.summary.verdict_rates[option.value];
                      if (rate == null) {
                        return null;
                      }
                      return (
                        <span
                          key={option.value}
                          className="rounded border border-border/70 px-2 py-0.5"
                        >
                          {option.label} {pct(rate)}
                        </span>
                      );
                    })}
                  </div>
                </div>
                <div className="rounded-lg border border-border/75 bg-muted/[0.08] p-3">
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Failure stage rates
                  </p>
                  <div className="flex flex-wrap gap-1.5 text-[11px]">
                    {FAILURE_STAGE_OPTIONS.map((option) => {
                      const rate = analysis.summary.failure_stage_rates[option.value];
                      if (rate == null) {
                        return null;
                      }
                      return (
                        <span
                          key={option.value}
                          className="rounded border border-border/70 px-2 py-0.5"
                        >
                          {option.label} {pct(rate)}
                        </span>
                      );
                    })}
                  </div>
                </div>
                <div className="rounded-lg border border-border/75 bg-muted/[0.08] p-3">
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Severity distribution
                  </p>
                  <div className="flex flex-wrap gap-1.5 text-[11px]">
                    {Object.entries(analysis.summary.severity_distribution).map(([severity, count]) => (
                      <span
                        key={severity}
                        className="rounded border border-border/70 px-2 py-0.5"
                      >
                        {severity} {count}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="rounded-lg border border-border/75 bg-muted/[0.08] p-3">
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Proposition Matcher candidate proxy (pass / concern / fail)
                  </p>
                  <div className="flex flex-wrap gap-1.5 text-[11px]">
                    <span className="rounded border border-emerald-700/35 px-2 py-0.5">
                      Pass {analysis.summary.proposition_matcher_proxy.pass}
                    </span>
                    <span className="rounded border border-amber-700/35 px-2 py-0.5">
                      Concern {analysis.summary.proposition_matcher_proxy.concern}
                    </span>
                    <span className="rounded border border-rose-700/35 px-2 py-0.5">
                      Fail {analysis.summary.proposition_matcher_proxy.fail}
                    </span>
                    <span className="rounded border border-border/70 px-2 py-0.5 text-muted-foreground">
                      Unreviewed {analysis.summary.proposition_matcher_proxy.unreviewed}
                    </span>
                    <span className="rounded border border-border/70 px-2 py-0.5">
                      Candidates {analysis.summary.proposition_matcher_proxy.total_candidates}
                    </span>
                  </div>
                </div>
              </div>

              <RateTable
                title="Rates by sample bucket"
                rows={analysis.summary.rates_by_sample_bucket}
                bucketLabel="Sample bucket"
              />
              <RateTable
                title="Rates by source instrument"
                rows={analysis.summary.rates_by_instrument}
                bucketLabel="Instrument"
              />
              <RateTable
                title="Rates by proposition count bucket"
                rows={analysis.summary.rates_by_proposition_count_bucket}
                bucketLabel="Proposition count"
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Diagnostic tables</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-lg border border-border/75 bg-background/70 p-3">
                <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  Worst source instruments (significant / critical)
                </p>
                {analysis.worst_instruments.length === 0 ? (
                  <p className="mt-2 text-[11px] text-muted-foreground">No significant/critical failures.</p>
                ) : (
                  <table className="mt-2 w-full min-w-[24rem] text-left text-[11px]">
                    <thead>
                      <tr className="border-b border-border/70 text-muted-foreground">
                        <th className="px-2 py-1 font-medium">Instrument</th>
                        <th className="px-2 py-1 font-medium">Sig/crit</th>
                        <th className="px-2 py-1 font-medium">Reviewed</th>
                        <th className="px-2 py-1 font-medium">Rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analysis.worst_instruments.map((row) => (
                        <tr key={row.instrument} className="border-b border-border/50">
                          <td className="px-2 py-1">
                            {instrumentLabels.get(row.instrument) ?? row.instrument}
                          </td>
                          <td className="px-2 py-1">{row.significant_critical_count}</td>
                          <td className="px-2 py-1">{row.reviewed_count}</td>
                          <td className="px-2 py-1">{pct(row.rate)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              <div className="rounded-lg border border-border/75 bg-background/70 p-3">
                <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  Most common failure-stage combinations
                </p>
                <table className="mt-2 w-full min-w-[24rem] text-left text-[11px]">
                  <thead>
                    <tr className="border-b border-border/70 text-muted-foreground">
                      <th className="px-2 py-1 font-medium">Combination</th>
                      <th className="px-2 py-1 font-medium">Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.failure_stage_combinations.map((row) => (
                      <tr key={row.combination} className="border-b border-border/50">
                        <td className="px-2 py-1">{row.combination}</td>
                        <td className="px-2 py-1">{row.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <CaseTable
                title="Incomplete + missing propositions"
                description="Reviews flagged incomplete and/or missing propositions."
                rows={analysis.incomplete_missing_propositions_cases}
                instrumentLabels={instrumentLabels}
              />
              <CaseTable
                title="Overreaching cases"
                description="Reviews with an overreaching verdict."
                rows={analysis.overreaching_cases}
                instrumentLabels={instrumentLabels}
              />
              <CaseTable
                title="Bad merge cases"
                description="Reviews with a bad merge verdict."
                rows={analysis.bad_merge_cases}
                instrumentLabels={instrumentLabels}
              />
            </CardContent>
          </Card>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          Upload a review export JSON file to begin analysis.
        </p>
      )}
    </div>
  );
}
