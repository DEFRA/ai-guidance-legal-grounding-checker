"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  AUTHORITIES_EMPTY_STATE,
  AUTHORITIES_IN_PLAY_LABEL,
} from "@/lib/legal-authority-display";
import type { PropositionRow } from "@/lib/law-statements-index";
import type { InlineLegalReference } from "@/lib/statement-inline-references";

import { LegalContextReferenceCard } from "./legal-context-reference-card";

export function LegalContextPanel(props: {
  references: InlineLegalReference[];
  selectedReferenceId: string | null;
  onSelectReference?: (referenceId: string) => void;
  onRemoveReference?: (referenceId: string) => void;
  propositionById: Map<string, PropositionRow>;
  className?: string;
  variant?: "workspace" | "drawer";
}): JSX.Element {
  const {
    references,
    selectedReferenceId,
    onSelectReference,
    onRemoveReference,
    propositionById,
    className = "",
    variant = "workspace",
  } = props;
  const [expandedReferenceId, setExpandedReferenceId] = useState<string | null>(selectedReferenceId);
  const cardRefs = useRef<Map<string, HTMLElement>>(new Map());
  const panelRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (selectedReferenceId) {
      setExpandedReferenceId(selectedReferenceId);
    }
  }, [selectedReferenceId]);

  useEffect(() => {
    if (!selectedReferenceId) {
      return;
    }
    const card = cardRefs.current.get(selectedReferenceId);
    if (typeof card?.scrollIntoView === "function") {
      card.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [selectedReferenceId, references.length]);

  const setCardRef = useCallback((referenceId: string, element: HTMLElement | null) => {
    if (element) {
      cardRefs.current.set(referenceId, element);
      return;
    }
    cardRefs.current.delete(referenceId);
  }, []);

  const panelShellClass =
    variant === "drawer"
      ? "rounded-xl border border-border/70 bg-muted/15 px-3 py-3"
      : "sticky top-4 max-h-[calc(100vh-32px)] overflow-auto rounded-xl border border-border/70 bg-muted/10 px-4 py-4 shadow-sm";

  if (references.length === 0) {
    return (
      <aside
        ref={panelRef}
        className={`${panelShellClass} ${className}`}
        data-testid="legal-context-panel-empty"
        aria-label={AUTHORITIES_IN_PLAY_LABEL}
      >
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {AUTHORITIES_IN_PLAY_LABEL}
        </p>
        <p className="mt-3 text-[12px] leading-relaxed text-muted-foreground">
          {AUTHORITIES_EMPTY_STATE}
        </p>
      </aside>
    );
  }

  const showWorkspaceChrome = variant === "workspace";

  return (
    <aside
      ref={panelRef}
      className={`${panelShellClass} ${className}`}
      data-testid="legal-context-panel"
      aria-label={AUTHORITIES_IN_PLAY_LABEL}
    >
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {AUTHORITIES_IN_PLAY_LABEL}
      </p>

      {showWorkspaceChrome ? (
        <nav className="mt-4" aria-label="Working set" data-testid="legal-context-working-set">
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground/80">
            Working set
          </p>
          <ol className="mt-2 flex flex-wrap items-center gap-1.5 text-[12px]">
            {references.map((reference, index) => (
              <li key={reference.id} className="flex items-center gap-1.5">
                {index > 0 ? (
                  <span className="text-muted-foreground/70" aria-hidden="true">
                    →
                  </span>
                ) : null}
                <button
                  type="button"
                  onClick={() => onSelectReference?.(reference.id)}
                  className={`rounded-md px-1.5 py-0.5 hover:bg-background/80 ${
                    selectedReferenceId === reference.id
                      ? "bg-background font-medium text-foreground shadow-sm"
                      : "text-muted-foreground"
                  }`}
                  data-testid="legal-context-breadcrumb-item"
                >
                  {reference.label}
                </button>
              </li>
            ))}
          </ol>
        </nav>
      ) : null}

      <div className={`space-y-3 ${showWorkspaceChrome ? "mt-4" : "mt-3"}`}>
        {references.map((reference) => (
          <LegalContextReferenceCard
            key={reference.id}
            reference={reference}
            propositionById={propositionById}
            expanded={expandedReferenceId === reference.id}
            selected={selectedReferenceId === reference.id}
            onToggleExpand={() =>
              setExpandedReferenceId((current) =>
                current === reference.id ? null : reference.id,
              )
            }
            onSelect={() => onSelectReference?.(reference.id)}
            onRemove={
              onRemoveReference ? () => onRemoveReference(reference.id) : undefined
            }
            showRemove={showWorkspaceChrome}
            cardRef={(element) => setCardRef(reference.id, element)}
          />
        ))}
      </div>
    </aside>
  );
}
