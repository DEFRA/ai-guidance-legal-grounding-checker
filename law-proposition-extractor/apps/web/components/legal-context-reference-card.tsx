"use client";

import { ChevronDown, ChevronUp, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  authorityHeadlineSummary,
  authorityWhyItMatters,
  supportingPropositionCountLabel,
} from "@/lib/legal-authority-display";
import type { PropositionRow } from "@/lib/law-statements-index";
import {
  INLINE_REFERENCE_PREVIEW_LIMIT,
  propositionReadableText,
  type InlineLegalReference,
} from "@/lib/statement-inline-references";

export function LegalContextReferenceCard(props: {
  reference: InlineLegalReference;
  propositionById: Map<string, PropositionRow>;
  expanded: boolean;
  selected: boolean;
  onToggleExpand: () => void;
  onSelect: () => void;
  onRemove?: () => void;
  showRemove?: boolean;
  cardRef?: (element: HTMLElement | null) => void;
}): JSX.Element {
  const {
    reference,
    propositionById,
    expanded,
    selected,
    onToggleExpand,
    onSelect,
    onRemove,
    showRemove = false,
    cardRef,
  } = props;
  const [showAllPropositions, setShowAllPropositions] = useState(false);

  useEffect(() => {
    setShowAllPropositions(false);
  }, [reference.id]);

  const headline = authorityHeadlineSummary(reference, propositionById);
  const whyItMatters = authorityWhyItMatters(reference);
  const propositionCountLabel = supportingPropositionCountLabel(reference.propositionIds.length);
  const visiblePropositionIds = showAllPropositions
    ? reference.propositionIds
    : reference.propositionIds.slice(0, INLINE_REFERENCE_PREVIEW_LIMIT);
  const hiddenCount = Math.max(
    0,
    reference.propositionIds.length - INLINE_REFERENCE_PREVIEW_LIMIT,
  );

  return (
    <article
      ref={cardRef}
      className={`rounded-xl border bg-card transition ${
        selected
          ? "border-priguidance-discovery/40 shadow-sm ring-1 ring-priguidance-discovery/20"
          : "border-border/60 shadow-sm"
      }`}
      data-testid="legal-context-reference-card"
      data-reference-id={reference.id}
    >
      <div className="flex items-start gap-2 px-4 py-3">
        <button
          type="button"
          onClick={onSelect}
          className="min-w-0 flex-1 text-left"
          data-testid="legal-context-card-select"
        >
          <p className="text-[14px] font-semibold leading-snug text-foreground">{reference.label}</p>
          <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">{headline}</p>
          {!expanded && reference.propositionIds.length > 0 ? (
            <p className="mt-2 text-[11px] text-muted-foreground/80">{propositionCountLabel}</p>
          ) : null}
        </button>
        <div className="flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            onClick={onToggleExpand}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted/50 hover:text-foreground"
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse authority card" : "Expand authority card"}
            data-testid="legal-context-card-toggle"
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          {showRemove && onRemove ? (
            <button
              type="button"
              onClick={onRemove}
              className="rounded-md p-1.5 text-muted-foreground hover:bg-muted/50 hover:text-foreground"
              aria-label={`Remove ${reference.label} from workspace`}
              data-testid="legal-context-card-remove"
            >
              <X className="h-4 w-4" />
            </button>
          ) : null}
        </div>
      </div>

      {expanded ? (
        <div className="space-y-4 border-t border-border/60 px-4 py-4">
          {whyItMatters ? (
            <section>
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Why it matters
              </h4>
              <p className="mt-1.5 text-[13px] leading-relaxed text-foreground">{whyItMatters}</p>
            </section>
          ) : null}

          {reference.propositionIds.length > 0 ? (
            <section>
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Supporting propositions
              </h4>
              <p className="mt-1 text-[12px] text-muted-foreground">{propositionCountLabel}</p>
              <ul className="mt-3 space-y-2">
                {visiblePropositionIds.map((propositionId) => (
                  <li
                    key={propositionId}
                    className="flex gap-2 text-[13px] leading-relaxed text-foreground"
                    data-testid="legal-context-proposition"
                  >
                    <span aria-hidden="true" className="mt-0.5 text-muted-foreground">
                      •
                    </span>
                    <span>{propositionReadableText(propositionId, propositionById)}</span>
                  </li>
                ))}
              </ul>
              {!showAllPropositions && hiddenCount > 0 ? (
                <button
                  type="button"
                  onClick={() => setShowAllPropositions(true)}
                  className="mt-3 text-[12px] font-medium text-primary hover:underline"
                  data-testid="legal-context-show-all"
                >
                  Show all supporting propositions
                </button>
              ) : null}
            </section>
          ) : null}

          <details className="rounded-lg border border-dashed border-border/60 bg-muted/10 px-3 py-2">
            <summary className="cursor-pointer text-[11px] font-medium text-muted-foreground">
              Developer details
            </summary>
            <div
              className="mt-2 space-y-2 font-mono text-[10px] text-muted-foreground"
              data-testid="legal-context-developer-details"
            >
              <p>Locator: {reference.locator}</p>
              <p>Status: {reference.status}</p>
              <p>Material role: {reference.materialRole}</p>
              <p>Summary: {reference.summary || "none"}</p>
              {reference.sourceExcerpt ? <p>Source excerpt: {reference.sourceExcerpt}</p> : null}
              {reference.resolvedLocator ? <p>Resolved to: {reference.resolvedLocator}</p> : null}
              <p>Proposition IDs: {reference.propositionIds.join(", ") || "none"}</p>
              <p>Source fragment IDs: {reference.sourceFragmentIds.join(", ") || "none"}</p>
              <p>Raw locators: {reference.rawLocators.join(", ") || "none"}</p>
            </div>
          </details>
        </div>
      ) : null}
    </article>
  );
}
