import { describe, expect, it } from "vitest";

import {
  buildStatementCompositionSegments,
  computeSegmentPopoverPosition,
  SEGMENT_DETAIL_MAX_HEIGHT_PX,
  SEGMENT_DETAIL_MAX_WIDTH_PX,
  segmentHighlightsContext,
  segmentHighlightsLawFragment,
  segmentHighlightsProposition,
} from "@/lib/statement-composition-highlight";
import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";
import type { LawFragmentView } from "@/lib/review-workbench-views";

const sampleStatement: LawStatementRow = {
  id: "lawstmt:test",
  statement_text:
    "Poultry manure must be incorporated as soon as practicable. Supporting context applies from regulation 9.",
  presentation_role: "guidance_matching_candidate",
  standalone_status: "partially_resolved",
  confidence: "medium",
  source_proposition_ids: ["prop:host"],
  supporting_proposition_ids: ["prop:xref"],
  required_context: [
    {
      locator: "regulation 9",
      resolution_status: "ambiguous",
      proposition_ids: ["prop:host", "prop:other"],
    },
  ],
};

const propositions = new Map<string, PropositionRow>([
  [
    "prop:host",
    {
      id: "prop:host",
      proposition_text: "Poultry manure must be incorporated as soon as practicable.",
      fragment_locator: "regulation 4(1)",
      source_record_id: "lex:test",
      source_fragment_id: "frag:test-001",
    },
  ],
  [
    "prop:xref",
    {
      id: "prop:xref",
      proposition_text: "Cross-reference supporting text.",
      fragment_locator: "regulation 4(2)",
      source_record_id: "lex:test",
    },
  ],
]);

const fragments = new Map<string, SourceFragmentRow>([
  [
    "frag:test-001",
    {
      id: "frag:test-001",
      fragment_text: "Authoritative source fragment text for host proposition.",
      locator: "regulation:4",
    },
  ],
]);

const lawFragments: LawFragmentView[] = [
  {
    id: "law-fragment-0",
    sourceLocator: "regulation 4(1)",
    sourceExcerpt: "Authoritative source fragment text for host proposition.",
    propositionIds: ["prop:host"],
    legislationUrl: null,
  },
];

describe("buildStatementCompositionSegments", () => {
  it("segments the statement and assigns composition sources to matched spans", () => {
    const segments = buildStatementCompositionSegments({
      statement: sampleStatement,
      context: {
        propositionById: propositions,
        sourceById: new Map([["lex:test", { id: "lex:test", title: "Test Reg" }]]),
        fragmentById: fragments,
      },
      lawFragments,
    });

    expect(segments.length).toBeGreaterThanOrEqual(2);
    let cursor = 0;
    for (const segment of segments) {
      expect(segment.start).toBe(cursor);
      expect(sampleStatement.statement_text.slice(segment.start, segment.end)).toBe(segment.text);
      cursor = segment.end;
    }
    expect(cursor).toBe(sampleStatement.statement_text.length);

    const hostSegment = segments.find((segment) => segment.propositionIds.includes("prop:host"));
    expect(hostSegment?.origin).toBe("composition_source");
    expect(hostSegment?.unknown).toBe(false);
    expect(hostSegment?.lawFragmentIds).toContain("law-fragment-0");

    const tailSegment = segments.find((segment) => segment.text.includes("regulation 9"));
    expect(tailSegment).toBeDefined();
    expect(tailSegment?.unknown).toBe(true);
    expect(tailSegment?.origin).toBe("inferred_unknown");
  });

  it("marks unlinked spans as inferred unknown", () => {
    const segments = buildStatementCompositionSegments({
      statement: {
        ...sampleStatement,
        statement_text: "Alpha requirement. Unlinked middle phrase. Beta tail.",
        source_proposition_ids: ["prop:host"],
        supporting_proposition_ids: [],
      },
      context: {
        propositionById: new Map([
          [
            "prop:host",
            {
              id: "prop:host",
              proposition_text: "Alpha requirement.",
            },
          ],
        ]),
        sourceById: new Map(),
        fragmentById: new Map(),
      },
    });

    const unknown = segments.find((segment) => segment.unknown);
    expect(unknown?.origin).toBe("inferred_unknown");
    expect(unknown?.text).toContain("Unlinked");
  });
});

describe("segment highlight helpers", () => {
  it("links selected segments to law fragments, propositions, and context", () => {
    const segments = buildStatementCompositionSegments({
      statement: sampleStatement,
      context: {
        propositionById: propositions,
        sourceById: new Map(),
        fragmentById: fragments,
      },
      lawFragments,
    });
    const hostSegment = segments.find((segment) => segment.propositionIds.includes("prop:host"))!;

    expect(segmentHighlightsProposition(hostSegment, "prop:host")).toBe(true);
    expect(segmentHighlightsLawFragment(hostSegment, lawFragments[0]!)).toBe(true);
    expect(
      segmentHighlightsContext(hostSegment, {
        locator: "regulation 9",
        status: "ambiguous",
        fragments: [],
      }),
    ).toBe(true);
  });
});

describe("computeSegmentPopoverPosition", () => {
  it("keeps the popover inside the viewport when anchored near the bottom edge", () => {
    const position = computeSegmentPopoverPosition({
      anchorRect: { top: 700, bottom: 720, left: 40, right: 180 },
      popoverSize: { width: SEGMENT_DETAIL_MAX_WIDTH_PX, height: SEGMENT_DETAIL_MAX_HEIGHT_PX },
      viewport: { width: 1280, height: 800 },
    });

    expect(position.top + SEGMENT_DETAIL_MAX_HEIGHT_PX).toBeLessThanOrEqual(800 - 8);
    expect(position.left + SEGMENT_DETAIL_MAX_WIDTH_PX).toBeLessThanOrEqual(1280 - 8);
    expect(position.top).toBeGreaterThanOrEqual(8);
    expect(position.left).toBeGreaterThanOrEqual(8);
  });

  it("prefers placing the popover to the right of the anchor", () => {
    const position = computeSegmentPopoverPosition({
      anchorRect: { top: 200, bottom: 220, left: 100, right: 240 },
      popoverSize: { width: 320, height: 240 },
      viewport: { width: 1024, height: 800 },
    });

    expect(position.left).toBeGreaterThanOrEqual(240 + 8);
  });

  it("places the popover to the left when there is no room on the right", () => {
    const position = computeSegmentPopoverPosition({
      anchorRect: { top: 200, bottom: 220, left: 900, right: 1000 },
      popoverSize: { width: 320, height: 240 },
      viewport: { width: 1024, height: 800 },
    });

    expect(position.left + 320).toBeLessThanOrEqual(900 - 8);
  });

  it("clamps vertical position when the popover would overflow the viewport bottom", () => {
    const position = computeSegmentPopoverPosition({
      anchorRect: { top: 760, bottom: 780, left: 100, right: 240 },
      popoverSize: { width: 320, height: 240 },
      viewport: { width: 1024, height: 800 },
    });

    expect(position.top + 240).toBeLessThanOrEqual(800 - 8);
  });
});
