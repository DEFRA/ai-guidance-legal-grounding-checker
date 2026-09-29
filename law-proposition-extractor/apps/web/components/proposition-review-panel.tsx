"use client";

import type { JSX } from "react";
import { useEffect, useRef, useState } from "react";

import { asRecord, type UnknownRecord } from "@/components/proposition-explorer-helpers";

export const REVIEW_ARTIFACT_PROPOSITION = "proposition";
export const REVIEW_ARTIFACT_STRUCTURED_DISPLAY = "structured_proposition_display";
export const REVIEW_ARTIFACT_SCOPE_LINKS = "proposition_scope_links";
export const REVIEW_ARTIFACT_COMPLETENESS = "proposition_completeness_assessment";

export type PipelineReviewAction = "approved" | "rejected" | "needs_review";

function normalizeAppliesField(field: unknown): string | null {
  if (field == null) {
    return null;
  }
  const s = String(field).trim();
  return s.length > 0 ? s : null;
}

function appliesFieldMatches(stored: unknown, requested: string | null): boolean {
  return normalizeAppliesField(stored) === requested;
}

/** Matches `resolve_current_pipeline_review_decision` in pipeline_reviews.py (append-only + supersedes). */
export function resolveCurrentPipelineReviewDecision(
  decisions: UnknownRecord[],
  artifactType: string,
  artifactId: string,
  appliesToField: string | null = null
): UnknownRecord | null {
  const superseded = new Set<string>();
  for (const d of decisions) {
    const sid = (d as UnknownRecord).supersedes_decision_id;
    if (sid != null && String(sid).trim()) {
      superseded.add(String(sid).trim());
    }
  }
  const matches = decisions.filter((d) => {
    const r = asRecord(d) ?? {};
    const id = String(r.id ?? "").trim();
    if (id && superseded.has(id)) {
      return false;
    }
    return (
      String(r.artifact_type ?? "") === artifactType &&
      String(r.artifact_id ?? "") === artifactId &&
      appliesFieldMatches(r.applies_to_field, appliesToField)
    );
  });
  if (matches.length === 0) {
    return null;
  }
  return matches.reduce((best, d) => {
    const br = asRecord(best) ?? {};
    const dr = asRecord(d) ?? {};
    const bk = `${String(br.reviewed_at ?? "")}\0${String(br.id ?? "")}`;
    const dk = `${String(dr.reviewed_at ?? "")}\0${String(dr.id ?? "")}`;
    return dk >= bk ? d : best;
  });
}

export type DecisionPresentationEmphasis = "muted" | "neutral" | "warn" | "danger";

/** Text + semantics for collapsed summary and expanded row status (persist/reload unchanged; driven by backend decision strings). */
export function pipelineReviewDecisionPresentation(decision: UnknownRecord | null): {
  text: string;
  muted: boolean;
  emphasis: DecisionPresentationEmphasis;
} {
  if (!decision) {
    return { text: "generated", muted: true, emphasis: "muted" };
  }
  const d = String((decision as UnknownRecord).decision ?? "")
    .trim()
    .toLowerCase();
  if (!d || d === "generated") {
    return { text: "generated", muted: true, emphasis: "muted" };
  }
  if (d === "needs_review") {
    return { text: "needs_review", muted: false, emphasis: "warn" };
  }
  if (d === "rejected") {
    return { text: "rejected", muted: false, emphasis: "danger" };
  }
  if (d === "approved") {
    return { text: "approved", muted: false, emphasis: "neutral" };
  }
  return { text: d, muted: false, emphasis: "neutral" };
}

function emphasisToStatusClass(emphasis: DecisionPresentationEmphasis, muted: boolean): string {
  if (muted || emphasis === "muted") {
    return "font-mono text-muted-foreground";
  }
  if (emphasis === "danger") {
    return "font-mono font-semibold text-red-700 dark:text-red-400";
  }
  if (emphasis === "warn") {
    return "font-mono font-semibold text-amber-800 dark:text-amber-400";
  }
  return "font-mono text-foreground/90";
}

function CompactReviewSummary({
  segments,
}: {
  segments: Array<{
    shortLabel: string;
    text: string;
    muted: boolean;
    emphasis: DecisionPresentationEmphasis;
  }>;
}): JSX.Element {
  return (
    <p className="break-words text-[11px] leading-snug text-foreground/88">
      {segments.map((seg, i) => {
        const valueClass = emphasisToStatusClass(seg.emphasis, seg.muted);
        return (
          <span key={`${seg.shortLabel}-${seg.text}-${String(i)}`} className="inline">
            {i > 0 ? <span className="text-muted-foreground"> · </span> : null}
            <span className="font-medium text-foreground/80">{seg.shortLabel}:</span>{" "}
            <span className={valueClass}>{seg.text}</span>
          </span>
        );
      })}
    </p>
  );
}

const BTN_APPROVE =
  "rounded border border-green-900/35 bg-green-900/[0.1] px-2 py-0.5 text-[11px] font-medium hover:bg-green-900/[0.18] disabled:opacity-45";
const BTN_REJECT =
  "rounded border border-red-900/35 bg-red-900/[0.09] px-2 py-0.5 text-[11px] font-medium hover:bg-red-900/[0.16] disabled:opacity-45";
const BTN_NEEDS =
  "rounded border border-border/70 bg-muted/40 px-2 py-0.5 text-[11px] font-medium hover:bg-muted/65 disabled:opacity-45";

const SUMMARY_CLASS =
  "cursor-pointer select-none rounded-md px-1 py-0.5 -mx-1 outline-none list-none marker:content-none [&::-webkit-details-marker]:hidden focus-visible:ring-2 focus-visible:ring-priguidance-discovery/35";

export function PropositionReviewPanel({
  propositionId,
  completenessArtifactId,
  decisions,
  busyKey,
  disabled,
  recordedFlashAt,
  onDecision,
}: {
  propositionId: string;
  /** Assessment row id when present; completeness decisions use this artifact_id, else proposition id. */
  completenessArtifactId: string;
  decisions: UnknownRecord[];
  busyKey: string | null;
  disabled: boolean;
  /** Non-null timestamps trigger a brief “saved” notice when matched to this row (UTC ms). */
  recordedFlashAt: number | null;
  onDecision: (artifactType: string, artifactId: string, decision: PipelineReviewAction) => void;
}): JSX.Element {
  const [expanded, setExpanded] = useState(false);
  const [showSavedPulse, setShowSavedPulse] = useState(false);
  const flashSeenRef = useRef<number | null>(null);
  const pid = propositionId.trim();

  const targets: Array<{
    key: string;
    label: string;
    shortLabel: string;
    artifactType: string;
    artifactId: string;
  }> = [
    {
      key: "raw",
      label: "Raw extraction",
      shortLabel: "Raw",
      artifactType: REVIEW_ARTIFACT_PROPOSITION,
      artifactId: pid,
    },
    {
      key: "structured",
      label: "Structured view",
      shortLabel: "Structured",
      artifactType: REVIEW_ARTIFACT_STRUCTURED_DISPLAY,
      artifactId: pid,
    },
    {
      key: "scopes",
      label: "Scope links",
      shortLabel: "Scopes",
      artifactType: REVIEW_ARTIFACT_SCOPE_LINKS,
      artifactId: pid,
    },
    {
      key: "complete",
      label: "Completeness",
      shortLabel: "Completeness",
      artifactType: REVIEW_ARTIFACT_COMPLETENESS,
      artifactId: completenessArtifactId.trim() || pid,
    },
  ];

  const segments = targets.map((t) => {
    const cur = resolveCurrentPipelineReviewDecision(decisions, t.artifactType, t.artifactId);
    const pres = pipelineReviewDecisionPresentation(cur);
    return {
      shortLabel: t.shortLabel,
      text: pres.text,
      muted: pres.muted,
      emphasis: pres.emphasis,
    };
  });

  useEffect(() => {
    if (recordedFlashAt == null) {
      return;
    }
    if (flashSeenRef.current === recordedFlashAt) {
      return;
    }
    flashSeenRef.current = recordedFlashAt;
    setShowSavedPulse(true);
    const t = window.setTimeout(() => setShowSavedPulse(false), 2400);
    return () => window.clearTimeout(t);
  }, [recordedFlashAt]);

  return (
    <details
      className="mt-3 rounded-md border border-border/55 bg-muted/[0.12] px-3 pt-2.5 pb-2"
      open={expanded}
      onToggle={(e) => setExpanded(e.currentTarget.open)}
    >
      <summary className={SUMMARY_CLASS}>
        <div className="flex flex-col gap-1.5 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
          <div className="min-w-0 flex-1">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Review layers
            </span>
            {!expanded ? (
              <div className="mt-1 space-y-1.5">
                <CompactReviewSummary segments={segments} />
                <p className="text-[11px] leading-snug text-muted-foreground">
                  These decisions apply to this source row, not the whole article section. Review each generated layer
                  independently: raw extraction, structured view, scope links, and completeness.
                </p>
                {showSavedPulse ? (
                  <p
                    className="text-[11px] font-medium text-emerald-800 dark:text-emerald-400"
                    role="status"
                    aria-live="polite"
                  >
                    Review saved — summary updated.
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
          <span className="mt-px shrink-0 text-[11px] text-muted-foreground sm:mt-1" aria-hidden>
            {expanded ? "Hide" : "Expand"}
          </span>
        </div>
      </summary>
      {expanded && showSavedPulse ? (
        <p
          className="mt-2 text-[11px] font-medium text-emerald-800 dark:text-emerald-400"
          role="status"
          aria-live="polite"
        >
          Review saved — status rows below reflect the latest decisions.
        </p>
      ) : null}
      <ul className="mt-3 space-y-2.5 border-t border-border/35 pt-2.5">
        {targets.map((t) => {
          const cur = resolveCurrentPipelineReviewDecision(decisions, t.artifactType, t.artifactId);
          const pres = pipelineReviewDecisionPresentation(cur);
          const rowBusy = busyKey === `${pid}|${t.artifactType}`;
          const block = disabled || rowBusy;

          return (
            <li
              key={t.key}
              className="border-t border-border/35 pt-2.5 first:border-t-0 first:pt-0"
            >
              <div className="flex flex-col gap-1.5 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="text-[12px] font-semibold text-foreground">{t.label}</p>
                  <p className="text-[11px] text-muted-foreground">
                    <span className="font-medium text-foreground/80">Status:</span>{" "}
                    <span className={emphasisToStatusClass(pres.emphasis, pres.muted)}>
                      {pres.text}
                    </span>
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-1">
                  <button
                    type="button"
                    className={BTN_APPROVE}
                    disabled={block || !pid}
                    onClick={(e) => {
                      e.stopPropagation();
                      onDecision(t.artifactType, t.artifactId, "approved");
                    }}
                  >
                    approve
                  </button>
                  <button
                    type="button"
                    className={BTN_REJECT}
                    disabled={block || !pid}
                    onClick={(e) => {
                      e.stopPropagation();
                      onDecision(t.artifactType, t.artifactId, "rejected");
                    }}
                  >
                    reject
                  </button>
                  <button
                    type="button"
                    className={BTN_NEEDS}
                    disabled={block || !pid}
                    onClick={(e) => {
                      e.stopPropagation();
                      onDecision(t.artifactType, t.artifactId, "needs_review");
                    }}
                  >
                    needs_review
                  </button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </details>
  );
}
