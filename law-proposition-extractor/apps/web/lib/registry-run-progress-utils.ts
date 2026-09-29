/** Pipeline run job / event helpers for Operations UI (polling v1). */

export const PIPELINE_STAGES_ORDERED = [
  "loading_case",
  "source_intake",
  "source_parsing",
  "source_fragmentation",
  "proposition_extraction",
  "proposition_inventory",
  "divergence_comparison",
  "scope_linking",
  "completeness_assessment",
  "export_bundle",
  "run_quality",
  "done",
] as const;

export type PipelineStageSlug = (typeof PIPELINE_STAGES_ORDERED)[number];

export function formatPipelineStageLabel(slug: string): string {
  return slug
    .split("_")
    .map((w) => (w.length > 0 ? w[0]!.toUpperCase() + w.slice(1) : w))
    .join(" ");
}

export function isTerminalJobStatus(status: string | undefined): boolean {
  const s = (status || "").toLowerCase();
  return s === "pass" || s === "warning" || s === "fail" || s === "cancelled";
}

/** UI categories derived canonically from job + stage-level terminal events only. */
export type StageDisplayUiKey =
  | "complete"
  | "running"
  | "failed"
  | "pending"
  | "skipped"
  | "not_started"
  | "warning";

function normalizeStageSlug(value: string | null | undefined): string {
  return String(value ?? "")
    .trim()
    .toLowerCase();
}

/**
 * True when an event represents a closed pipeline *stage* (not a per-source / sub-step row).
 * Backend marks whole-stage exits with duration_ms via _close_pending; per-source extraction
 * rows omit duration_ms and finished_at.
 */
export function isStageLevelTerminalEvent(ev: Record<string, unknown>): boolean {
  const st = String(ev.status || "").toLowerCase();
  if (st === "running" || st === "pending") return false;
  const stage = String(ev.stage || "");
  if (stage === "proposition_extraction") {
    const dm = ev.duration_ms;
    return typeof dm === "number" && Number.isFinite(dm);
  }
  return true;
}

/**
 * Per-stage display status. Precedence:
 * 1. failed — stage-level terminal outcome is fail
 * 2. running — slug matches job current_stage and job is not terminal
 * 3. complete / warning / skipped — stage-level terminal outcome
 * 4. pending — job queued (no stage outcome yet)
 * 5. not_started
 */
export function getStageDisplayStatus(args: {
  slug: string;
  /** From {@link latestStageOutcomes} only (stage-level terminals). */
  stageLevelOutcome: Record<string, unknown> | undefined;
  currentStage: string | null | undefined;
  runStatus: string | undefined;
}): StageDisplayUiKey {
  const { slug, stageLevelOutcome, currentStage, runStatus } = args;
  const rs = (runStatus || "").toLowerCase();

  if (stageLevelOutcome) {
    const ost = String(stageLevelOutcome.status || "").toLowerCase();
    if (ost === "fail") return "failed";
  }

  if (
    normalizeStageSlug(slug) === normalizeStageSlug(currentStage) &&
    !isTerminalJobStatus(runStatus)
  ) {
    return "running";
  }

  if (stageLevelOutcome) {
    const ost = String(stageLevelOutcome.status || "").toLowerCase();
    if (ost === "pass") return "complete";
    if (ost === "warning") return "warning";
    if (ost === "skipped") return "skipped";
  }

  if (rs === "queued") {
    return "pending";
  }

  return "not_started";
}

export function formatStageDuration(durationMs: unknown): string | null {
  if (typeof durationMs !== "number" || !Number.isFinite(durationMs) || durationMs < 0) {
    return null;
  }
  if (durationMs < 1000) {
    return `${Math.round(durationMs)}ms`;
  }
  const sec = durationMs / 1000;
  if (sec < 60) {
    return sec >= 10 ? `${Math.round(sec)}s` : `${sec.toFixed(1)}s`;
  }
  const mm = Math.floor(sec / 60);
  const ss = Math.round(sec % 60);
  return `${mm}m ${ss}s`;
}

/**
 * Last stage-level terminal event per stage (one row per stage when the stage as a whole
 * finished/was skipped/failed). Ignores sub-step rows (e.g. per-source extraction passes).
 */
export function latestStageOutcomes(events: readonly Record<string, unknown>[]): Map<
  string,
  Record<string, unknown>
> {
  const map = new Map<string, Record<string, unknown>>();
  const ordered = [...events].sort(
    (a, b) =>
      (Number(a.sequence_number) || 0) - (Number(b.sequence_number) || 0)
  );
  for (const ev of ordered) {
    const stage = String(ev.stage || "");
    if (!stage) continue;
    const st = String(ev.status || "").toLowerCase();
    if (st === "running" || st === "pending") continue;
    if (!isStageLevelTerminalEvent(ev)) continue;
    map.set(stage, ev);
  }
  return map;
}

/** Icon / symbol for tests (not emoji — avoid UI font issues). */
export function stageStatusSymbol(status: string | undefined): string {
  const s = (status || "").toLowerCase();
  if (s === "pass") return "ok";
  if (s === "warning") return "warn";
  if (s === "fail") return "fail";
  if (s === "skipped") return "skip";
  if (s === "running" || s === "pending") return "run";
  return "—";
}

function isExtractionProgressDetailMessage(msg: string): boolean {
  const m = msg.toLowerCase();
  return (
    m.includes("calling") ||
    m.includes("finished extracting source") ||
    m.includes("extraction complete for source")
  );
}

/** Latest in-flight or sub-step extraction line for the detail panel (not stage status). */
export function pickLatestExtractionDetail(
  events: readonly Record<string, unknown>[]
): Record<string, unknown> | null {
  const prop = [...events]
    .reverse()
    .find(
      (e) =>
        String(e.stage || "") === "proposition_extraction" &&
        (String(e.status || "").toLowerCase() === "running" ||
          isExtractionProgressDetailMessage(String(e.message || "")))
    );
  return prop ?? null;
}
