import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  SEGMENT_DETAIL_MAX_HEIGHT_PX,
  SEGMENT_DETAIL_MAX_WIDTH_PX,
  type StatementCompositionSegment,
} from "@/lib/statement-composition-highlight";

import { StatementCompositionHighlight } from "./statement-composition-highlight";

const longText = `${"A".repeat(220)} end`;

const sampleSegments: StatementCompositionSegment[] = [
  {
    id: "seg-host",
    text: "Poultry manure must be incorporated",
    start: 0,
    end: 37,
    propositionIds: ["prop:host"],
    contextLocators: [],
    origin: "composition_source",
    sourceLocator: "regulation 4(1)",
    propositionText: longText,
    sourceExcerpt: longText,
    recipeRowIds: [],
    lawFragmentIds: ["law-fragment-0"],
    statementFragmentId: null,
    unknown: false,
  },
  {
    id: "seg-unknown",
    text: "regulation 9",
    start: 38,
    end: 50,
    propositionIds: [],
    contextLocators: ["regulation 9"],
    origin: "inferred_unknown",
    sourceLocator: "not available from current export",
    propositionText: "not available from current export",
    sourceExcerpt: "not available from current export",
    recipeRowIds: [],
    lawFragmentIds: [],
    statementFragmentId: null,
    unknown: true,
  },
];

function mockMatchMedia(matches: boolean): void {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

function mockAnchorRect(): void {
  Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
    configurable: true,
    value: () =>
      ({
        top: 120,
        bottom: 148,
        left: 64,
        right: 280,
        width: 216,
        height: 28,
        x: 64,
        y: 120,
        toJSON: () => ({}),
      }) satisfies DOMRect,
  });
}

describe("StatementCompositionHighlight popover layout", () => {
  beforeEach(() => {
    mockMatchMedia(false);
    mockAnchorRect();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders a bounded desktop popover instead of an unbounded overlay", () => {
    render(
      <StatementCompositionHighlight
        segments={sampleSegments}
        selectedSegmentId="seg-host"
        onSelectSegment={() => undefined}
      />,
    );

    const popover = screen.getByTestId("segment-detail-popover");
    expect(popover).toBeTruthy();
    expect(popover.className).toContain("bg-card");
    expect(popover.style.maxWidth).toBe(`${SEGMENT_DETAIL_MAX_WIDTH_PX}px`);
    expect(popover.style.maxHeight).toBe(`${SEGMENT_DETAIL_MAX_HEIGHT_PX}px`);
    expect(screen.queryByTestId("segment-detail-inline")).toBeNull();
  });

  it("closes the popover on Escape and clears selection", () => {
    function ControlledHighlight(): JSX.Element {
      const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>("seg-host");
      return (
        <StatementCompositionHighlight
          segments={sampleSegments}
          selectedSegmentId={selectedSegmentId}
          onSelectSegment={setSelectedSegmentId}
        />
      );
    }

    render(<ControlledHighlight />);
    expect(screen.getByTestId("segment-detail-popover")).toBeTruthy();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("segment-detail-popover")).toBeNull();
    expect(screen.getByTestId("segment-button-seg-host").getAttribute("aria-pressed")).toBe(
      "false",
    );
  });

  it("keeps selected segment highlighting on the clicked segment", () => {
    render(
      <StatementCompositionHighlight
        segments={sampleSegments}
        selectedSegmentId="seg-host"
        onSelectSegment={() => undefined}
      />,
    );

    const selectedButton = screen.getByTestId("segment-button-seg-host");
    expect(selectedButton.getAttribute("aria-pressed")).toBe("true");
  });

  it("truncates long proposition text with show more", () => {
    render(
      <StatementCompositionHighlight
        segments={sampleSegments}
        selectedSegmentId="seg-host"
        onSelectSegment={() => undefined}
      />,
    );

    expect(screen.getAllByRole("button", { name: "Show more" }).length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(new RegExp(`${"A".repeat(180)}…`)).length,
    ).toBeGreaterThan(0);
  });

  it("skips segment detail when showSegmentDetail is false", () => {
    render(
      <StatementCompositionHighlight
        segments={sampleSegments}
        selectedSegmentId="seg-host"
        onSelectSegment={() => undefined}
        showSegmentDetail={false}
      />,
    );

    expect(screen.queryByTestId("segment-detail-popover")).toBeNull();
    expect(screen.queryByTestId("segment-detail-inline")).toBeNull();
  });

  it("renders inline detail below the statement on narrow viewports", async () => {
    mockMatchMedia(true);
    render(
      <StatementCompositionHighlight
        segments={sampleSegments}
        selectedSegmentId="seg-host"
        onSelectSegment={() => undefined}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("segment-detail-inline")).toBeTruthy();
    });
    expect(screen.queryByTestId("segment-detail-popover")).toBeNull();
  });
});
