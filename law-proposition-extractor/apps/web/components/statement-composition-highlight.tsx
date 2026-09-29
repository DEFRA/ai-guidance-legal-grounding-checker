"use client";

import { X } from "lucide-react";
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";

import { EXPORT_FIELD_UNAVAILABLE } from "@/lib/law-statements-composition";
import {
  COMPOSITION_ORIGIN_LABEL,
  COMPOSITION_SEGMENT_SELECTED_CLASS,
  COMPOSITION_SEGMENT_SURFACE_CLASS,
  computeSegmentPopoverPosition,
  NARROW_VIEWPORT_MEDIA_QUERY,
  SEGMENT_DETAIL_MAX_HEIGHT_PX,
  SEGMENT_DETAIL_MAX_WIDTH_PX,
  SEGMENT_DETAIL_TRUNCATE_LENGTH,
  type CompositionFragmentOrigin,
  type StatementCompositionSegment,
} from "@/lib/statement-composition-highlight";

export type { StatementCompositionSegment };

const UNAVAILABLE = "not available from current export";
const HOVER_CLOSE_DELAY_MS = 120;

function useNarrowViewport(): boolean {
  const [narrow, setNarrow] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia(NARROW_VIEWPORT_MEDIA_QUERY);
    const sync = (): void => setNarrow(mediaQuery.matches);
    sync();
    mediaQuery.addEventListener("change", sync);
    return () => mediaQuery.removeEventListener("change", sync);
  }, []);

  return narrow;
}

function OriginBadge(props: { origin: CompositionFragmentOrigin; unknown: boolean }): JSX.Element {
  const { origin, unknown } = props;
  return (
    <span className="rounded border border-border/70 bg-muted/50 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
      {unknown ? "Unknown" : COMPOSITION_ORIGIN_LABEL[origin]}
    </span>
  );
}

function TruncatedBlock(props: {
  label: string;
  text: string;
  mono?: boolean;
  muted?: boolean;
  maxLength?: number;
}): JSX.Element {
  const {
    label,
    text,
    mono = false,
    muted = false,
    maxLength = SEGMENT_DETAIL_TRUNCATE_LENGTH,
  } = props;
  const [expanded, setExpanded] = useState(false);
  const needsTruncate = text.length > maxLength;
  const displayText =
    expanded || !needsTruncate ? text : `${text.slice(0, maxLength).trimEnd()}…`;

  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p
        className={`mt-0.5 text-[12px] leading-snug ${mono ? "font-mono text-[11px]" : ""} ${
          muted ? "text-muted-foreground" : ""
        }`}
      >
        {displayText}
      </p>
      {needsTruncate ? (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="mt-0.5 text-[11px] font-medium text-primary hover:underline"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      ) : null}
    </div>
  );
}

function SegmentDetailCard(props: { segment: StatementCompositionSegment }): JSX.Element {
  const { segment } = props;
  return (
    <div className="space-y-2 text-[12px] leading-relaxed">
      <div className="flex flex-wrap items-center gap-2">
        <OriginBadge origin={segment.origin} unknown={segment.unknown} />
        {segment.unknown ? (
          <span className="text-[11px] text-amber-800 dark:text-amber-200">
            No linked proposition or context locator
          </span>
        ) : null}
      </div>
      {segment.propositionIds.length > 0 ? (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Proposition ids
          </p>
          <ul className="mt-0.5 space-y-0.5 font-mono text-[11px] text-primary">
            {segment.propositionIds.map((propositionId) => (
              <li key={propositionId}>{propositionId}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {segment.contextLocators.length > 0 ? (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Context locators
          </p>
          <ul className="mt-0.5 space-y-0.5 font-mono text-[11px]">
            {segment.contextLocators.map((locator) => (
              <li key={locator}>{locator}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {segment.sourceLocator !== UNAVAILABLE && segment.sourceLocator !== EXPORT_FIELD_UNAVAILABLE ? (
        <TruncatedBlock label="Source locator" text={segment.sourceLocator} mono />
      ) : null}
      {segment.propositionText !== UNAVAILABLE && segment.propositionText !== EXPORT_FIELD_UNAVAILABLE ? (
        <TruncatedBlock label="Proposition text" text={segment.propositionText} />
      ) : null}
      {segment.sourceExcerpt !== UNAVAILABLE && segment.sourceExcerpt !== EXPORT_FIELD_UNAVAILABLE ? (
        <TruncatedBlock label="Source excerpt" text={segment.sourceExcerpt} muted />
      ) : null}
    </div>
  );
}

function SegmentDetailPopover(props: {
  segment: StatementCompositionSegment;
  anchorRect: DOMRect;
  anchorElement: HTMLElement;
  onClose: () => void;
  onPointerEnter: () => void;
  onPointerLeave: () => void;
}): JSX.Element | null {
  const { segment, anchorRect, anchorElement, onClose, onPointerEnter, onPointerLeave } = props;
  const popoverRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{ top: number; left: number }>(() =>
    computeSegmentPopoverPosition({
      anchorRect,
      popoverSize: {
        width: SEGMENT_DETAIL_MAX_WIDTH_PX,
        height: SEGMENT_DETAIL_MAX_HEIGHT_PX,
      },
      viewport: {
        width: typeof window !== "undefined" ? window.innerWidth : SEGMENT_DETAIL_MAX_WIDTH_PX,
        height: typeof window !== "undefined" ? window.innerHeight : SEGMENT_DETAIL_MAX_HEIGHT_PX,
      },
    }),
  );

  const updatePosition = useCallback(() => {
    const popoverElement = popoverRef.current;
    if (!popoverElement) {
      return;
    }
    const popoverRect = popoverElement.getBoundingClientRect();
    const nextPosition = computeSegmentPopoverPosition({
      anchorRect: anchorElement.getBoundingClientRect(),
      popoverSize: {
        width: popoverRect.width || SEGMENT_DETAIL_MAX_WIDTH_PX,
        height: popoverRect.height || SEGMENT_DETAIL_MAX_HEIGHT_PX,
      },
      viewport: { width: window.innerWidth, height: window.innerHeight },
    });
    setPosition((current) =>
      current.top === nextPosition.top && current.left === nextPosition.left
        ? current
        : nextPosition,
    );
  }, [anchorElement]);

  useLayoutEffect(() => {
    updatePosition();
  }, [segment.id, anchorRect, updatePosition]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    const handlePointerDown = (event: PointerEvent): void => {
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (popoverRef.current?.contains(target) || anchorElement.contains(target)) {
        return;
      }
      onClose();
    };

    window.addEventListener("keydown", handleKeyDown);
    document.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [anchorElement, onClose, updatePosition]);

  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <div
      ref={popoverRef}
      role="dialog"
      aria-label="Statement segment details"
      data-testid="segment-detail-popover"
      className="fixed z-50 flex flex-col overflow-hidden rounded-lg border border-border/80 bg-card text-card-foreground shadow-lg"
      style={{
        top: position.top,
        left: position.left,
        width: `min(${SEGMENT_DETAIL_MAX_WIDTH_PX}px, calc(100vw - 1rem))`,
        maxWidth: SEGMENT_DETAIL_MAX_WIDTH_PX,
        maxHeight: SEGMENT_DETAIL_MAX_HEIGHT_PX,
      }}
      onMouseEnter={onPointerEnter}
      onMouseLeave={onPointerLeave}
    >
      <div className="flex items-start justify-between gap-2 border-b border-border/60 px-3 py-2">
        <OriginBadge origin={segment.origin} unknown={segment.unknown} />
        <button
          type="button"
          aria-label="Close segment details"
          onClick={onClose}
          className="rounded p-0.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>
      <div
        className="min-h-0 flex-1 overflow-y-auto bg-card px-3 py-2"
        style={{ maxHeight: SEGMENT_DETAIL_MAX_HEIGHT_PX - 44 }}
      >
        <SegmentDetailCard segment={segment} />
      </div>
    </div>,
    document.body,
  );
}

function CompositionSegmentButton(props: {
  segment: StatementCompositionSegment;
  selected: boolean;
  textClassName?: string;
  onHoverStart: () => void;
  onHoverEnd: () => void;
  onToggleSelect: () => void;
  registerAnchor: (segmentId: string, element: HTMLButtonElement | null) => void;
}): JSX.Element {
  const {
    segment,
    selected,
    textClassName = "text-base",
    onHoverStart,
    onHoverEnd,
    onToggleSelect,
    registerAnchor,
  } = props;

  return (
    <button
      ref={(element) => registerAnchor(segment.id, element)}
      type="button"
      aria-pressed={selected}
      onMouseEnter={onHoverStart}
      onMouseLeave={onHoverEnd}
      onFocus={onHoverStart}
      onBlur={onHoverEnd}
      onClick={onToggleSelect}
      data-segment-id={segment.id}
      data-testid={`segment-button-${segment.id}`}
      className={`mx-0.5 inline rounded-md border px-1 py-0.5 text-left transition ${textClassName} leading-relaxed ${COMPOSITION_SEGMENT_SURFACE_CLASS[segment.origin]} ${
        selected ? COMPOSITION_SEGMENT_SELECTED_CLASS : ""
      } ${segment.unknown ? "italic" : ""}`}
    >
      {segment.text}
    </button>
  );
}

export function StatementCompositionHighlight(props: {
  segments: StatementCompositionSegment[];
  selectedSegmentId?: string | null;
  onSelectSegment?: (segmentId: string | null) => void;
  textClassName?: string;
  showLegend?: boolean;
  /** When false, segment detail is not shown (avoids duplicate popovers when the component is mounted twice). */
  showSegmentDetail?: boolean;
}): JSX.Element {
  const {
    segments,
    selectedSegmentId = null,
    onSelectSegment,
    textClassName,
    showLegend = true,
    showSegmentDetail = true,
  } = props;
  const detailRegionId = useId();
  const isNarrowViewport = useNarrowViewport();
  const [hoveredSegmentId, setHoveredSegmentId] = useState<string | null>(null);
  const anchorElements = useRef(new Map<string, HTMLButtonElement>());
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);

  const activeSegmentId = isNarrowViewport ? selectedSegmentId : hoveredSegmentId ?? selectedSegmentId;
  const activeSegment =
    segments.find((segment) => segment.id === activeSegmentId) ?? null;

  const clearLeaveTimer = useCallback(() => {
    if (leaveTimer.current) {
      clearTimeout(leaveTimer.current);
      leaveTimer.current = null;
    }
  }, []);

  const closeDetail = useCallback(() => {
    clearLeaveTimer();
    setHoveredSegmentId(null);
    onSelectSegment?.(null);
  }, [clearLeaveTimer, onSelectSegment]);

  const registerAnchor = useCallback((segmentId: string, element: HTMLButtonElement | null) => {
    if (element) {
      anchorElements.current.set(segmentId, element);
      return;
    }
    anchorElements.current.delete(segmentId);
  }, []);

  const handleHoverStart = useCallback(
    (segmentId: string) => {
      if (isNarrowViewport) {
        return;
      }
      clearLeaveTimer();
      setHoveredSegmentId(segmentId);
    },
    [clearLeaveTimer, isNarrowViewport],
  );

  const handleHoverEnd = useCallback(() => {
    if (isNarrowViewport) {
      return;
    }
    clearLeaveTimer();
    leaveTimer.current = setTimeout(() => {
      setHoveredSegmentId(null);
    }, HOVER_CLOSE_DELAY_MS);
  }, [clearLeaveTimer, isNarrowViewport]);

  const handleToggleSelect = useCallback(
    (segmentId: string) => {
      clearLeaveTimer();
      if (selectedSegmentId === segmentId) {
        onSelectSegment?.(null);
        setHoveredSegmentId(null);
        return;
      }
      onSelectSegment?.(segmentId);
      if (!isNarrowViewport) {
        setHoveredSegmentId(segmentId);
      }
    },
    [clearLeaveTimer, isNarrowViewport, onSelectSegment, selectedSegmentId],
  );

  useLayoutEffect(() => {
    if (!activeSegmentId || isNarrowViewport) {
      setAnchorRect(null);
      return;
    }
    const anchor = anchorElements.current.get(activeSegmentId) ?? null;
    if (!anchor) {
      setAnchorRect(null);
      return;
    }
    setAnchorRect(anchor.getBoundingClientRect());
  }, [activeSegmentId, isNarrowViewport, segments]);

  if (segments.length === 0) {
    return <p className="text-base leading-relaxed text-muted-foreground">No statement text.</p>;
  }

  const showLegendPanel =
    segments.length > 1 ||
    new Set(segments.map((segment) => segment.origin)).size > 1 ||
    segments.some((segment) => segment.unknown);

  const selectedSegment =
    segments.find((segment) => segment.id === selectedSegmentId) ?? null;

  return (
    <div className="space-y-2">
      <p
        className={`leading-relaxed text-foreground ${textClassName ?? "text-base"}`}
        aria-describedby={activeSegment && !isNarrowViewport ? detailRegionId : undefined}
      >
        {segments.map((segment) => (
          <CompositionSegmentButton
            key={segment.id}
            segment={segment}
            selected={selectedSegmentId === segment.id}
            textClassName={textClassName}
            onHoverStart={() => handleHoverStart(segment.id)}
            onHoverEnd={handleHoverEnd}
            onToggleSelect={() => handleToggleSelect(segment.id)}
            registerAnchor={registerAnchor}
          />
        ))}
      </p>

      {showSegmentDetail && isNarrowViewport && selectedSegment ? (
        <div
          id={detailRegionId}
          data-testid="segment-detail-inline"
          className="rounded-lg border border-border/80 bg-muted/20 p-3"
        >
          <div className="mb-2 flex items-start justify-between gap-2">
            <OriginBadge origin={selectedSegment.origin} unknown={selectedSegment.unknown} />
            <button
              type="button"
              aria-label="Close segment details"
              onClick={closeDetail}
              className="rounded p-0.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
          <SegmentDetailCard segment={selectedSegment} />
        </div>
      ) : null}

      {showSegmentDetail && !isNarrowViewport && activeSegment && anchorRect ? (
        <SegmentDetailPopover
          key={activeSegment.id}
          segment={activeSegment}
          anchorRect={anchorRect}
          anchorElement={anchorElements.current.get(activeSegment.id)!}
          onClose={closeDetail}
          onPointerEnter={clearLeaveTimer}
          onPointerLeave={handleHoverEnd}
        />
      ) : null}

      {showLegend && showLegendPanel ? (
        <div className="flex flex-wrap gap-2 text-[10px] text-muted-foreground">
          {(Object.keys(COMPOSITION_ORIGIN_LABEL) as CompositionFragmentOrigin[]).map((origin) => (
            <span key={origin} className="inline-flex items-center gap-1">
              <span
                className={`inline-block h-2.5 w-5 rounded border ${COMPOSITION_SEGMENT_SURFACE_CLASS[origin]}`}
              />
              {COMPOSITION_ORIGIN_LABEL[origin]}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
