"use client";

import type { JSX, ReactNode } from "react";
import { useState } from "react";
import { CardDescription } from "@/components/ui/card";
import type { UnknownRecord } from "@/components/proposition-explorer-helpers";
import { buildSourceContextLine, deriveStructuredProposition, type ProvisionType } from "@/components/structured-proposition";

export type PropositionDisplayMode = "structured" | "raw";

/** Matches proposition-explorer scope chips for consistency. */
export const SCOPE_META_CHIP_CLASS =
  "rounded border border-border/70 bg-muted/80 px-2 py-0.5 font-mono text-[11px] leading-5 text-foreground/85";

export function isPrimaryScopeLink(ln: UnknownRecord): boolean {
  const relevance = String(ln.relevance ?? "")
    .trim()
    .toLowerCase();
  const confidence = String(ln.confidence ?? "")
    .trim()
    .toLowerCase();
  return relevance === "direct" && confidence === "high";
}

function scopeLinkConfidenceRank(confidence: string | undefined): number {
  const c = String(confidence ?? "")
    .trim()
    .toLowerCase();
  if (c === "high") {
    return 0;
  }
  if (c === "medium") {
    return 1;
  }
  if (c === "low") {
    return 2;
  }
  return 3;
}

function compareScopeLinksByConfidence(a: UnknownRecord, b: UnknownRecord): number {
  return (
    scopeLinkConfidenceRank(typeof a.confidence === "string" ? a.confidence : undefined) -
    scopeLinkConfidenceRank(typeof b.confidence === "string" ? b.confidence : undefined)
  );
}

/** Primary = direct + high; each bucket sorted by link confidence (high → medium → low). */
export function partitionScopeLinksSorted(rows: UnknownRecord[]): {
  primary: UnknownRecord[];
  secondary: UnknownRecord[];
} {
  const primary = rows.filter(isPrimaryScopeLink).sort(compareScopeLinksByConfidence);
  const secondary = rows.filter((r) => !isPrimaryScopeLink(r)).sort(compareScopeLinksByConfidence);
  return { primary, secondary };
}

export function PropositionScopeLinksSection({
  propositionId,
  scopeRows,
  scopeById,
}: {
  propositionId: string;
  scopeRows: UnknownRecord[];
  scopeById: ReadonlyMap<string, UnknownRecord>;
}): JSX.Element {
  const [showAllScopes, setShowAllScopes] = useState(false);
  const { primary, secondary } = partitionScopeLinksSorted(scopeRows);
  const hasSecondary = secondary.length > 0;
  const orderedVisible = showAllScopes ? [...primary, ...secondary] : primary;

  return (
    <div>
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Scope links</p>
      {scopeRows.length === 0 ? (
        <p className="mt-1 text-xs text-muted-foreground">none</p>
      ) : (
        <>
          {orderedVisible.length === 0 ? (
            <p className="mt-1 text-xs text-muted-foreground">
              No direct high-confidence scope links.{hasSecondary ? " Use “Show all scopes” below for contextual or lower-confidence links." : ""}
            </p>
          ) : (
            <ul className="mt-1 space-y-1">
              {orderedVisible.map((ln) => {
                const sco = String((ln as { scope_id?: string }).scope_id ?? "");
                const sc = scopeById.get(sco);
                const slug = sc?.slug ?? sco;
                const lab = typeof sc?.label === "string" ? sc.label : sco;
                return (
                  <li key={`${propositionId}-${sco}-${String((ln as { id?: string }).id)}`}>
                    <span className={SCOPE_META_CHIP_CLASS}>{String(slug)}</span>
                    {lab !== String(slug) ? (
                      <span className="ml-1.5 text-xs text-foreground/80">{lab}</span>
                    ) : null}
                    <span className="ml-1.5 text-xs text-muted-foreground">
                      relevance {String((ln as { relevance?: string }).relevance ?? "—")} · link conf{" "}
                      {String((ln as { confidence?: string }).confidence ?? "—")}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
          {hasSecondary ? (
            <button
              type="button"
              className="mt-2 text-[11px] font-medium text-primary underline-offset-2 hover:underline"
              onClick={() => setShowAllScopes((v) => !v)}
            >
              {showAllScopes ? "Hide secondary scopes" : "Show all scopes"}
            </button>
          ) : null}
        </>
      )}
    </div>
  );
}

const FIELD_LABEL = "text-[10px] font-semibold uppercase tracking-wide text-muted-foreground";
const FIELD_VAL = "text-[13px] font-semibold leading-snug text-foreground";

function provisionTypeDisplayLabel(pt: ProvisionType): string {
  switch (pt) {
    case "transitional":
      return "Transitional";
    case "definition":
      return "Definition";
    case "exception":
      return "Exception";
    case "cross_reference":
      return "Cross-reference";
    case "core":
    default:
      return "Core rule";
  }
}

function ProvisionTypeBanner({ provisionType }: { provisionType: ProvisionType }): JSX.Element {
  return (
    <div className="rounded-md border border-priguidance-discovery/40 bg-priguidance-discovery/[0.09] px-3 py-2.5 shadow-sm dark:bg-priguidance-discovery/[0.06]">
      <p className={`${FIELD_LABEL} mb-1`}>Provision type</p>
      <p className="text-[15px] font-semibold leading-snug tracking-tight text-foreground">
        {provisionTypeDisplayLabel(provisionType)}
      </p>
    </div>
  );
}

/** Completeness assessment chips (palette + unknown); `COMPLETENESS_TOOLTIP` copy aligned with checklist docs. */
export const COMPLETENESS_TOOLTIP =
  "Completeness means whether the proposition is understandable on its own or needs source context.";

const KNOWN_COMPLETENESS_STATUSES = new Set(["complete", "context_dependent", "fragmentary"]);

/** Normalize API completeness `status`; unknown or missing values map to `"unknown"` for display. */
export function completenessNormalizedStatus(status: string | undefined): string {
  const raw = String(status ?? "").trim();
  if (!raw) {
    return "unknown";
  }
  const s = raw.toLowerCase().replace(/-/g, "_");
  return KNOWN_COMPLETENESS_STATUSES.has(s) ? s : "unknown";
}

export function completenessChipClass(status: string): string {
  switch (status) {
    case "complete":
      return "border-emerald-800/50 bg-emerald-100 text-emerald-950 dark:border-emerald-600/55 dark:bg-emerald-950/35 dark:text-emerald-50";
    case "context_dependent":
      return "border-amber-800/50 bg-amber-100 text-amber-950 dark:border-amber-600/55 dark:bg-amber-950/35 dark:text-amber-50";
    case "fragmentary":
      return "border-red-800/50 bg-red-100 text-red-950 dark:border-red-600/55 dark:bg-red-950/35 dark:text-red-50";
    case "unknown":
      return "border-border/65 bg-muted text-foreground dark:bg-muted/80 dark:text-foreground";
    case "not_assessed":
      return "border-border/60 bg-muted text-foreground dark:bg-muted/80 dark:text-foreground";
    default:
      return "border-border/70 bg-muted/80 text-foreground dark:text-foreground";
  }
}

export function completenessDisplayLabel(status: string): string {
  switch (status) {
    case "complete":
      return "Complete";
    case "context_dependent":
      return "Needs context";
    case "fragmentary":
      return "Fragmentary";
    case "unknown":
      return "Unknown";
    case "not_assessed":
      return "Not assessed";
    default:
      return "—";
  }
}

const COMPLETENESS_CHIP_LAYOUT =
  "inline-flex min-h-[1.25rem] shrink-0 cursor-help items-center whitespace-nowrap rounded border px-2 py-0.5 text-[11px] font-semibold tabular-nums leading-tight";

export function CompletenessChipBadge({
  pipelineStatus,
  noAssessment,
  className = "",
}: {
  /** Raw `status` from `proposition_completeness_assessments` (may be absent or unrecognized). */
  pipelineStatus?: string;
  /** When true, no assessment row was loaded for this proposition — show explicit not-assessed state. */
  noAssessment?: boolean;
  /** Extra Tailwind/classes for compact row headers. */
  className?: string;
}): JSX.Element {
  if (noAssessment) {
    const label = completenessDisplayLabel("not_assessed");
    return (
      <span
        title={`${COMPLETENESS_TOOLTIP} No completeness assessment row was loaded for this proposition.`}
        className={`${COMPLETENESS_CHIP_LAYOUT} ${completenessChipClass("not_assessed")} ${className}`.trim()}
      >
        {label}
      </span>
    );
  }
  const norm = completenessNormalizedStatus(pipelineStatus);
  const label = completenessDisplayLabel(norm);
  return (
    <span
      title={`${COMPLETENESS_TOOLTIP} Raw status: ${String(pipelineStatus ?? "").trim() || "—"}`}
      className={`${COMPLETENESS_CHIP_LAYOUT} ${completenessChipClass(norm)} ${className}`.trim()}
    >
      {label}
    </span>
  );
}

/** Extraction pipeline confidence — when `low`, we avoid showing heuristic S/R/O splits. */
function isWeakExtractionConfidence(confidence: string | undefined): boolean {
  return String(confidence ?? "")
    .trim()
    .toLowerCase() === "low";
}

export function StructuredPropositionSections({
  mode,
  text,
  oa,
  sourceTitleById,
  suggestedStatement,
  extractionConfidence,
  completenessChipSlot,
  scopeSectionSlot,
  evidenceCollapsible,
  extractionNeedsReview,
}: {
  mode: PropositionDisplayMode;
  text: string;
  oa: UnknownRecord;
  sourceTitleById: ReadonlyMap<string, string>;
  suggestedStatement: string;
  /** Effective extraction trace confidence (`high` / `medium` / `low`). */
  extractionConfidence?: string;
  /** Completeness chip from `proposition_completeness_assessments.status` — shown beside structured-view label. */
  completenessChipSlot?: ReactNode;
  /** Scope taxonomy + extraction confidence — rendered below structured proposition, above collapsible evidence. */
  scopeSectionSlot?: ReactNode;
  /** Raw text + fragment/trace actions (rendered inside default-closed details) */
  evidenceCollapsible?: ReactNode;
  /** Low-trust extraction: heuristic fallback, model uncertainty, or explicit pipeline review flag. */
  extractionNeedsReview?: boolean;
}): JSX.Element | null {
  const sourceCtx = buildSourceContextLine(oa as UnknownRecord, sourceTitleById);
  const parts = deriveStructuredProposition(text);
  const weakExtraction = isWeakExtractionConfidence(extractionConfidence);
  const showOperativeOnly = Boolean(extractionNeedsReview) || weakExtraction || parts.fallbackNoModal;
  const operativeBody = showOperativeOnly ? text.trim() : parts.coreRemainder || text;

  const gapClass = "gap-3";

  const needsReviewBanner =
    extractionNeedsReview || weakExtraction ? (
      <div
        className="rounded-md border-2 border-amber-700/55 bg-amber-950/[0.14] px-3 py-2.5 text-[13px] font-semibold leading-snug text-amber-950 shadow-sm dark:border-amber-500/45 dark:bg-amber-950/25 dark:text-amber-50"
        role="status"
      >
        <span className="font-bold tracking-tight">Needs review</span>
        {" — "}
        {weakExtraction
          ? "low extraction confidence; structured view may not match legal roles reliably."
          : "fallback or uncertain extraction path; verify against the authoritative source."}
      </div>
    ) : null;

  if (!text.trim()) {
    return (
      <>
        {needsReviewBanner}
        {suggestedStatement ? (
          <SuggestedDisplayStatementBlock suggestedStatement={suggestedStatement} />
        ) : null}
        {completenessChipSlot ? (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className={FIELD_LABEL}>Completeness</span>
            {completenessChipSlot}
          </div>
        ) : null}
        {scopeSectionSlot ?? null}
        {evidenceCollapsible ?? null}
      </>
    );
  }

  if (mode === "raw") {
    return (
      <div className={`flex flex-col ${gapClass}`}>
        {needsReviewBanner}
        {suggestedStatement ? (
          <SuggestedDisplayStatementBlock suggestedStatement={suggestedStatement} />
        ) : null}
        <ProvisionTypeBanner provisionType={parts.provisionType} />
        {parts.provisionType === "transitional" ? (
          <div className="rounded-md border border-border/55 bg-muted/[0.18] px-3 py-2">
            <p className={`${FIELD_LABEL} text-primary`}>Transitional provision</p>
            {parts.temporalLabels.length > 0 ? (
              <ul className="mt-1.5 space-y-1">
                {parts.temporalLabels.map((line, i) => (
                  <li key={i} className={`${FIELD_VAL} whitespace-pre-wrap text-foreground`}>
                    {line}
                  </li>
                ))}
              </ul>
            ) : (
              <p className={`mt-1 text-[12.5px] font-semibold leading-snug text-foreground/90`}>
                Time-bound or transitional rule — see raw text for timing detail.
              </p>
            )}
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className={FIELD_LABEL}>Completeness</span>
          {completenessChipSlot ?? (
            <span className="text-[11px] text-muted-foreground">—</span>
          )}
        </div>
        <div>
          <p className={FIELD_LABEL}>Raw proposition text</p>
          <CardDescription className="mt-0.5 whitespace-pre-wrap text-[13px] leading-relaxed text-foreground/95">
            {text}
          </CardDescription>
        </div>
        {scopeSectionSlot ?? null}
        {evidenceCollapsible ?? null}
      </div>
    );
  }

  return (
    <div className={`flex flex-col ${gapClass}`}>
      {suggestedStatement ? (
        <SuggestedDisplayStatementBlock suggestedStatement={suggestedStatement} />
      ) : null}
      {needsReviewBanner}

      <div className="rounded-md border border-border/60 bg-muted/[0.22] px-3 py-2.5">
        <ProvisionTypeBanner provisionType={parts.provisionType} />

        <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-border/40 pt-3">
          <p className={`${FIELD_LABEL} mb-0`} title={COMPLETENESS_TOOLTIP}>
            Structured view (derived from source text)
          </p>
          {completenessChipSlot ?? null}
        </div>

        <div className="mt-2.5 border-t border-border/40 pt-2.5">
          <p className={FIELD_LABEL}>Source</p>
          <p className={`${FIELD_VAL} mt-0.5 break-words`}>{sourceCtx}</p>
        </div>

        {parts.provisionType === "transitional" ? (
          <div className="mt-3 rounded border border-priguidance-discovery/35 bg-priguidance-discovery/[0.06] px-2.5 py-2">
            <p className={`${FIELD_LABEL} text-primary`}>Transitional provision</p>
            {parts.temporalLabels.length > 0 ? (
              <ul className="mt-2 space-y-1.5">
                {parts.temporalLabels.map((line, i) => (
                  <li key={i} className={`${FIELD_VAL} whitespace-pre-wrap text-foreground`}>
                    {line}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-[12.5px] font-semibold leading-snug text-foreground/90">
                Time-bound or transitional rule — see operative text below for timing detail.
              </p>
            )}
          </div>
        ) : null}

        {showOperativeOnly ? (
          <div className="mt-3">
            <p className={FIELD_LABEL}>Operative text</p>
            <p className={`${FIELD_VAL} mt-0.5 whitespace-pre-wrap`}>{operativeBody}</p>
          </div>
        ) : (
          <>
            {parts.subject ? (
              <div className="mt-3">
                <p className={FIELD_LABEL}>Subject</p>
                <p className={`${FIELD_VAL} mt-0.5`}>{parts.subject}</p>
              </div>
            ) : null}
            {parts.rule ? (
              <div className="mt-2">
                <p className={FIELD_LABEL}>Rule</p>
                <p className={`${FIELD_VAL} mt-0.5`}>{parts.rule}</p>
              </div>
            ) : null}
            {parts.object ? (
              <div className="mt-2">
                <p className={FIELD_LABEL}>Object</p>
                <p className={`${FIELD_VAL} mt-0.5 whitespace-pre-wrap`}>{parts.object}</p>
              </div>
            ) : null}
          </>
        )}

        {parts.conditions.length > 0 ? (
          <div className="mt-3 border-t border-border/50 pt-2.5">
            <p className={FIELD_LABEL}>Conditions</p>
            <ul className="mt-1 list-disc space-y-1 pl-4 text-[12.5px] font-semibold leading-snug text-foreground/95">
              {parts.conditions.map((c, i) => (
                <li key={i} className="whitespace-pre-wrap">
                  {c}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      {scopeSectionSlot ?? null}

      {evidenceCollapsible ?? null}
    </div>
  );
}

function SuggestedDisplayStatementBlock({
  suggestedStatement,
}: {
  suggestedStatement: string;
}): JSX.Element {
  if (!suggestedStatement.trim()) {
    return <></>;
  }
  return (
    <div className="rounded border border-priguidance-discovery/28 bg-muted/25 px-3 py-2.5">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        Suggested display statement
      </p>
      <p className="mt-1 text-[13px] leading-relaxed text-foreground">{suggestedStatement}</p>
    </div>
  );
}

export function PropositionEvidenceDetails({
  rawText,
  verbatimEvidenceKnown,
  verbatimEvidenceQuote,
  evidenceMismatchWarning,
  traceButton,
  fragmentSlot,
}: {
  rawText: string;
  /** When true, extractor stamped `evidence_quote` (possibly empty intentionally). */
  verbatimEvidenceKnown?: boolean;
  verbatimEvidenceQuote?: string;
  /** Shown only when verbatim evidence was required but omitted (explain in reason/trace). */
  evidenceMismatchWarning?: string | null;
  traceButton: ReactNode;
  fragmentSlot: ReactNode;
}): JSX.Element {
  const verbatimKnown = verbatimEvidenceKnown === true;

  return (
    <details className="group">
      <summary className="cursor-pointer select-none rounded border border-border/50 bg-muted/20 px-2 py-1.5 text-[11px] font-medium text-muted-foreground hover:bg-muted/35">
        Evidence: legal proposition, verbatim quote (when present), source fragment, extraction trace
      </summary>
      <div className="mt-2 space-y-3 rounded border border-border/40 bg-muted/10 px-2.5 py-2">
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            Legal proposition (normalised wording)
          </p>
          <p className="mt-1 whitespace-pre-wrap text-[12px] leading-relaxed text-muted-foreground">{rawText}</p>
        </div>
        {verbatimKnown && (evidenceMismatchWarning || verbatimEvidenceQuote?.trim()) ? (
          <div className={evidenceMismatchWarning ? "rounded border border-amber-500/55 bg-amber-500/[0.08] px-2 py-1.5" : ""}>
            {evidenceMismatchWarning ? (
              <p className="text-[12px] leading-snug text-amber-950 dark:text-amber-100">{evidenceMismatchWarning}</p>
            ) : null}
            {!evidenceMismatchWarning && verbatimEvidenceQuote?.trim() ? (
              <>
                <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  Verbatim source evidence (exact quote)
                </p>
                <p className="mt-1 whitespace-pre-wrap border-l-2 border-priguidance-discovery/35 pl-2 text-[12px] leading-relaxed text-foreground">
                  {verbatimEvidenceQuote}
                </p>
              </>
            ) : null}
          </div>
        ) : null}
        <div className="flex flex-wrap gap-2 border-t border-border/35 pt-2">
          {fragmentSlot}
          {traceButton}
        </div>
      </div>
    </details>
  );
}
