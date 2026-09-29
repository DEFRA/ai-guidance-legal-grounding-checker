"use client";

import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Clock3,
  Loader2,
  MinusCircle,
  XCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  formatPipelineStageLabel,
  formatStageDuration,
  getStageDisplayStatus,
  isTerminalJobStatus,
  latestStageOutcomes,
  pickLatestExtractionDetail,
  PIPELINE_STAGES_ORDERED,
  type StageDisplayUiKey,
} from "@/lib/registry-run-progress-utils";

type JobMetrics = {
  source_count?: number;
  fragment_count?: number;
  proposition_count?: number;
  llm_extraction_call_count?: number;
  llm_extraction_skipped_count?: number;
  max_estimated_input_tokens?: number | null;
  fallback_count?: number;
  low_confidence_count?: number;
  warning_count?: number;
  error_count?: number;
  context_window_risk_count?: number;
};

export type RegistryRunJobSummary = {
  id?: string;
  status?: string;
  run_id?: string | null;
  requested_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
  current_stage?: string | null;
  progress_message?: string | null;
  metrics?: JobMetrics;
  event_count?: number;
};

const STAGE_STATUS_UI: Record<
  StageDisplayUiKey,
  {
    label: string;
    Icon: LucideIcon;
    rowClass: string;
    iconClass: string;
    badgeClass: string;
  }
> = {
  complete: {
    label: "Complete",
    Icon: CheckCircle2,
    rowClass:
      "border-emerald-200/70 bg-emerald-50/60 dark:border-emerald-900/60 dark:bg-emerald-950/20",
    iconClass: "text-emerald-600 dark:text-emerald-400",
    badgeClass:
      "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300",
  },
  running: {
    label: "Running",
    Icon: Loader2,
    rowClass:
      "border-blue-200 bg-blue-50/70 shadow-sm dark:border-blue-900/70 dark:bg-blue-950/30",
    iconClass: "text-blue-600 dark:text-blue-400 animate-spin",
    badgeClass:
      "border-blue-200 bg-blue-100 text-blue-800 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-300",
  },
  failed: {
    label: "Failed",
    Icon: XCircle,
    rowClass:
      "border-destructive/40 bg-destructive/10 dark:border-destructive/50 dark:bg-destructive/15",
    iconClass: "text-destructive",
    badgeClass: "border-destructive/30 bg-destructive/10 text-destructive",
  },
  pending: {
    label: "Pending",
    Icon: Clock3,
    rowClass:
      "border-amber-200/70 bg-amber-50/50 dark:border-amber-900/60 dark:bg-amber-950/20",
    iconClass: "text-amber-600 dark:text-amber-400",
    badgeClass:
      "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300",
  },
  skipped: {
    label: "Skipped",
    Icon: MinusCircle,
    rowClass: "border-border bg-muted/30 text-muted-foreground",
    iconClass: "text-muted-foreground",
    badgeClass: "border-border bg-muted text-muted-foreground",
  },
  not_started: {
    label: "Not started",
    Icon: Circle,
    rowClass: "border-border bg-background text-muted-foreground",
    iconClass: "text-muted-foreground",
    badgeClass: "border-border bg-background text-muted-foreground",
  },
  warning: {
    label: "Warning",
    Icon: AlertTriangle,
    rowClass:
      "border-amber-200/70 bg-amber-50/50 dark:border-amber-900/60 dark:bg-amber-950/25",
    iconClass: "text-amber-600 dark:text-amber-400",
    badgeClass:
      "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300",
  },
};

function jobRunSummaryBadgeClass(statusLower: string): string {
  if (statusLower === "pass") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300";
  }
  if (statusLower === "warning") {
    return "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200";
  }
  if (statusLower === "fail" || statusLower === "cancelled") {
    return "border-destructive/30 bg-destructive/10 text-destructive";
  }
  if (statusLower === "queued") {
    return "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300";
  }
  return "border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-300";
}

function jobRunSummaryLabel(statusLower: string): string {
  if (statusLower === "pass") return "Complete";
  if (statusLower === "warning") return "Warning";
  if (statusLower === "fail") return "Failed";
  if (statusLower === "cancelled") return "Cancelled";
  if (statusLower === "queued") return "Queued";
  if (statusLower === "running") return "Running";
  return statusLower ? statusLower.replace(/_/g, " ") : "Unknown";
}

export function RegistryRunProgressPanel(props: {
  job: RegistryRunJobSummary | null;
  events: readonly Record<string, unknown>[];
  /** Overrides default `/propositions` link when the job completes (equine corpus → scope filter). */
  viewPropositionsHref?: string;
}): JSX.Element | null {
  const { job, events, viewPropositionsHref = "/propositions" } = props;
  if (!job?.id) return null;

  const statusLower = String(job.status || "").toLowerCase();
  const terminal = isTerminalJobStatus(job.status);
  const stageMap = latestStageOutcomes(events);
  const extractionLive = pickLatestExtractionDetail(events);
  const m = job.metrics || {};

  const stageSlugs = PIPELINE_STAGES_ORDERED.filter((s) => s !== "done");

  const elapsedHint = (() => {
    const start = job.started_at ? Date.parse(String(job.started_at)) : NaN;
    const end = job.finished_at
      ? Date.parse(String(job.finished_at))
      : terminal
        ? NaN
        : Date.now();
    if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
    const sec = Math.max(0, Math.round((end - start) / 1000));
    if (sec < 60) return `${sec}s`;
    const mm = Math.floor(sec / 60);
    const ss = sec % 60;
    return `${mm}m ${ss}s`;
  })();

  const stageRows = stageSlugs.map((slug) => {
    const stageLevelOutcome = stageMap.get(slug);
    const displayStatus = getStageDisplayStatus({
      slug,
      stageLevelOutcome,
      currentStage: job.current_stage,
      runStatus: job.status,
    });
    return { slug, stageLevelOutcome, displayStatus };
  });

  let stagesCompleteCount = 0;
  let stagesResolvedCount = 0;
  for (const row of stageRows) {
    if (row.stageLevelOutcome) {
      stagesResolvedCount += 1;
    }
    if (row.displayStatus === "complete" || row.displayStatus === "warning") {
      stagesCompleteCount += 1;
    }
  }

  const progressPercent =
    stageSlugs.length > 0
      ? Math.min(100, Math.round((stagesResolvedCount / stageSlugs.length) * 100))
      : 0;

  const currentStageLabel = job.current_stage
    ? formatPipelineStageLabel(String(job.current_stage))
    : null;

  return (
    <div className="mt-3 rounded-lg border border-border/80 bg-muted/20 p-3 text-xs">
      <div className="rounded-md border border-border/70 bg-card/40 px-3 py-2.5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="font-semibold text-foreground">Run progress</div>
            <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
              job <span className="break-all">{job.id}</span>
            </div>
            {job.run_id ? (
              <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                run <span className="break-all">{String(job.run_id)}</span>
              </div>
            ) : null}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1 text-right">
            <span
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-[11px] font-semibold",
                jobRunSummaryBadgeClass(statusLower)
              )}
            >
              {jobRunSummaryLabel(statusLower)}
            </span>
            {elapsedHint ? (
              <div className="font-mono text-[11px] text-muted-foreground">
                Elapsed {elapsedHint}
              </div>
            ) : null}
          </div>
        </div>

        <div
          className="mt-2 h-2 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-valuenow={progressPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Pipeline stages resolved"
        >
          <div
            className="h-2 rounded-full bg-primary transition-all"
            style={{ width: `${progressPercent}%` }}
          />
        </div>

        <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
          {currentStageLabel ? (
            <>
              <span className="font-medium text-foreground">Current stage:</span>{" "}
              <span className="text-foreground">{currentStageLabel}</span>
              <span className="mx-1.5 text-muted-foreground">·</span>
            </>
          ) : null}
          <span>
            {stagesCompleteCount} of {stageSlugs.length} stages complete
          </span>
        </p>

        {job.progress_message ? (
          <p className="mt-1 text-[11px] text-muted-foreground">{job.progress_message}</p>
        ) : null}
      </div>

      <div className="mt-3">
        <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Stages
        </div>
        <ul className="max-h-56 space-y-2 overflow-y-auto pr-0.5">
          {stageRows.map(({ slug, stageLevelOutcome: ev, displayStatus }) => {
            const statusUi = STAGE_STATUS_UI[displayStatus];
            const Icon = statusUi.Icon;
            const runningExtractionMsg =
              displayStatus === "running" &&
              slug === "proposition_extraction" &&
              extractionLive &&
              typeof extractionLive.message === "string"
                ? extractionLive.message.trim()
                : "";
            const messageRaw =
              runningExtractionMsg ||
              (ev && typeof ev.message === "string" ? ev.message.trim() : "");
            const message = messageRaw || null;
            const dur =
              displayStatus === "running" || displayStatus === "pending"
                ? null
                : formatStageDuration(ev?.duration_ms);

            return (
              <li key={slug}>
                <div
                  className={cn(
                    "grid grid-cols-[auto_1fr_auto] items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors",
                    statusUi.rowClass
                  )}
                >
                  <Icon
                    className={cn("mt-0.5 h-4 w-4 shrink-0", statusUi.iconClass)}
                    aria-hidden="true"
                  />

                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={cn(
                          "font-medium",
                          displayStatus === "running" && "font-semibold text-foreground"
                        )}
                      >
                        {formatPipelineStageLabel(slug)}
                      </span>

                      {displayStatus === "running" ? (
                        <span className="text-xs font-medium text-blue-700 dark:text-blue-300">
                          Current stage
                        </span>
                      ) : null}
                    </div>

                    {message ? (
                      <p className="mt-1 truncate text-sm text-muted-foreground">{message}</p>
                    ) : null}
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    <span
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-xs font-semibold",
                        statusUi.badgeClass
                      )}
                    >
                      {statusUi.label}
                    </span>

                    {dur ? (
                      <span className="min-w-12 text-right font-mono text-xs text-muted-foreground">
                        {dur}
                      </span>
                    ) : null}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="mt-3 rounded border border-border/50 bg-background/60 p-2">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Proposition extraction
        </div>
        {extractionLive ? (
          <div className="mt-1 space-y-0.5 font-mono text-[11px]">
            <div>{String(extractionLive.message || "—")}</div>
            {extractionLive.model_alias ? (
              <div>model: {String(extractionLive.model_alias)}</div>
            ) : null}
            {extractionLive.extraction_mode ? (
              <div>mode: {String(extractionLive.extraction_mode)}</div>
            ) : null}
            {typeof extractionLive.estimated_input_tokens === "number" ? (
              <div>est. input tokens: {String(extractionLive.estimated_input_tokens)}</div>
            ) : null}
            {typeof extractionLive.configured_context_limit === "number" ? (
              <div>context limit: {String(extractionLive.configured_context_limit)}</div>
            ) : null}
            {extractionLive.context_window_risk === true ? (
              <div className="text-amber-800">context-window risk</div>
            ) : null}
          </div>
        ) : (
          <div className="mt-1 text-[11px] text-muted-foreground">No live extraction step yet.</div>
        )}
        <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-0.5 font-mono text-[11px] text-muted-foreground">
          <span>LLM calls</span>
          <span className="text-right text-foreground">
            {String(m.llm_extraction_call_count ?? "—")}
          </span>
          <span>LLM skipped</span>
          <span className="text-right text-foreground">
            {String(m.llm_extraction_skipped_count ?? "—")}
          </span>
          <span>max est. tokens</span>
          <span className="text-right text-foreground">
            {m.max_estimated_input_tokens != null ? String(m.max_estimated_input_tokens) : "—"}
          </span>
          <span>fallbacks</span>
          <span className="text-right text-foreground">{String(m.fallback_count ?? "—")}</span>
          <span>ctx-window risks</span>
          <span className="text-right text-foreground">
            {String(m.context_window_risk_count ?? "—")}
          </span>
        </div>
      </div>

      {terminal ? (
        <div className="mt-3 space-y-1 border-t border-border/60 pt-2">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Summary
          </div>
          <div className="grid grid-cols-2 gap-x-2 font-mono text-[11px]">
            <span className="text-muted-foreground">Sources</span>
            <span className="text-right">{String(m.source_count ?? "—")}</span>
            <span className="text-muted-foreground">Fragments</span>
            <span className="text-right">{String(m.fragment_count ?? "—")}</span>
            <span className="text-muted-foreground">Propositions</span>
            <span className="text-right">{String(m.proposition_count ?? "—")}</span>
            <span className="text-muted-foreground">Low-confidence traces</span>
            <span className="text-right">{String(m.low_confidence_count ?? "—")}</span>
            <span className="text-muted-foreground">Lint warnings</span>
            <span className="text-right">{String(m.warning_count ?? "—")}</span>
            <span className="text-muted-foreground">Lint errors</span>
            <span className="text-right">{String(m.error_count ?? "—")}</span>
          </div>
          {job.run_id ? (
            <Link
              href={viewPropositionsHref}
              className="mt-2 inline-block rounded border border-priguidance-discovery/50 bg-priguidance-discovery/[0.08] px-2 py-1 text-[11px] font-medium text-primary hover:bg-priguidance-discovery/[0.14]"
            >
              View propositions
            </Link>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
