"use client";

import { AlertTriangle, ChevronDown, Leaf, Link2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  ACCENT_ARIA_LABEL,
  INLINE_REFERENCE_ACCENT_CLASS,
  referenceAriaLabel,
  referenceById,
  hoverPreviewText,
  type InlineLegalReference,
  type StatementTextPart,
} from "@/lib/statement-inline-references";
import { NARROW_VIEWPORT_MEDIA_QUERY } from "@/lib/statement-composition-highlight";

function useNarrowViewport(): boolean {
  const [narrow, setNarrow] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }
    const mediaQuery = window.matchMedia(NARROW_VIEWPORT_MEDIA_QUERY);
    const sync = (): void => setNarrow(mediaQuery.matches);
    sync();
    mediaQuery.addEventListener("change", sync);
    return () => mediaQuery.removeEventListener("change", sync);
  }, []);

  return narrow;
}

function ReferenceAccentIcon(props: { accent: InlineLegalReference["accent"] }): JSX.Element | null {
  const { accent } = props;
  if (accent === "resolved_container") {
    return <ChevronDown className="mr-0.5 inline h-3 w-3 align-[-2px]" aria-hidden="true" />;
  }
  if (accent === "material") {
    return <Leaf className="mr-0.5 inline h-3 w-3 align-[-2px]" aria-hidden="true" />;
  }
  if (accent === "warning") {
    return <AlertTriangle className="mr-0.5 inline h-3 w-3 align-[-2px]" aria-hidden="true" />;
  }
  return <Link2 className="mr-0.5 inline h-3 w-3 align-[-2px] opacity-70" aria-hidden="true" />;
}

export function StatementInlineReferenceText(props: {
  statementText: string;
  parts: StatementTextPart[];
  references: InlineLegalReference[];
  textClassName?: string;
  selectedReferenceId?: string | null;
  onSelectReference?: (referenceId: string | null) => void;
  accumulateSelection?: boolean;
  mobilePanel?: JSX.Element | null;
  emptyMessage?: string;
}): JSX.Element {
  const {
    statementText,
    parts,
    references,
    textClassName = "text-lg font-medium leading-snug",
    selectedReferenceId = null,
    onSelectReference,
    accumulateSelection = false,
    mobilePanel = null,
    emptyMessage = "No statement text.",
  } = props;
  const [internalSelectedId, setInternalSelectedId] = useState<string | null>(null);
  const [hoveredReferenceId, setHoveredReferenceId] = useState<string | null>(null);
  const referencesById = useMemo(() => referenceById(references), [references]);
  const isControlled = onSelectReference !== undefined;
  const activeReferenceId = isControlled ? (selectedReferenceId ?? null) : internalSelectedId;
  const isNarrow = useNarrowViewport();
  const showMobilePanel =
    isNarrow && activeReferenceId !== null && referencesById.has(activeReferenceId);

  const handleSelect = (referenceId: string): void => {
    const toggleOff = isNarrow || !accumulateSelection;
    const next = toggleOff && activeReferenceId === referenceId ? null : referenceId;
    if (!isControlled) {
      setInternalSelectedId(next);
    }
    onSelectReference?.(next);
  };

  if (!statementText.trim()) {
    return <p className="text-base leading-relaxed text-muted-foreground">{emptyMessage}</p>;
  }

  return (
    <div className="space-y-2">
      <p className={`leading-relaxed text-foreground ${textClassName}`}>
        {parts.map((part) => {
          if (part.kind === "text") {
            return <span key={part.key}>{part.text}</span>;
          }
          const reference = referencesById.get(part.referenceId);
          if (!reference) {
            return <span key={part.key}>{part.text}</span>;
          }
          const selected = activeReferenceId === reference.id;
          const hovered = hoveredReferenceId === reference.id;
          return (
            <span key={part.key} className="relative inline">
              <button
                type="button"
                aria-pressed={selected}
                aria-label={referenceAriaLabel(reference)}
                title={hoverPreviewText(reference)}
                data-testid={`inline-reference-${reference.locator}`}
                onClick={() => handleSelect(reference.id)}
                onMouseEnter={() => setHoveredReferenceId(reference.id)}
                onMouseLeave={() => setHoveredReferenceId(null)}
                onFocus={() => setHoveredReferenceId(reference.id)}
                onBlur={() => setHoveredReferenceId(null)}
                className={`mx-0.5 inline text-left transition hover:opacity-90 ${INLINE_REFERENCE_ACCENT_CLASS[reference.accent]} ${
                  selected ? "ring-2 ring-priguidance-discovery/40" : ""
                }`}
              >
                <ReferenceAccentIcon accent={reference.accent} />
                {part.text}
              </button>
              {hovered ? (
                <span
                  role="tooltip"
                  className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-1 w-max max-w-[16rem] -translate-x-1/2 rounded border border-border/80 bg-background px-2 py-1.5 text-left text-[10px] leading-snug text-foreground shadow-sm"
                  data-testid="inline-reference-hover-preview"
                >
                  <span className="block font-medium">{reference.label}</span>
                  <span className="block text-muted-foreground">
                    {ACCENT_ARIA_LABEL[reference.accent]} ·{" "}
                    {reference.propositionIds.length} linked proposition
                    {reference.propositionIds.length === 1 ? "" : "s"}
                  </span>
                  <span className="block text-muted-foreground">
                    Click to add to Authorities in play
                  </span>
                </span>
              ) : null}
            </span>
          );
        })}
      </p>

      {showMobilePanel ? mobilePanel : null}
    </div>
  );
}
