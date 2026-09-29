import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LegalContextPanel } from "@/components/legal-context-panel";
import type { PropositionRow } from "@/lib/law-statements-index";
import {
  buildStatementTextParts,
  findLocatorTextSpan,
  type InlineLegalReference,
} from "@/lib/statement-inline-references";

import { StatementInlineReferenceText } from "./statement-inline-reference-text";

const propositionById = new Map<string, PropositionRow>([
  [
    "prop:one",
    { id: "prop:one", proposition_text: "First linked proposition text." },
  ],
  [
    "prop:two",
    { id: "prop:two", proposition_text: "Second linked proposition text." },
  ],
]);

function buildReference(overrides: Partial<InlineLegalReference>): InlineLegalReference {
  return {
    id: "statement::Schedule 3::10",
    sourceId: "statement",
    locator: "Schedule 3",
    label: "Schedule 3",
    start: 10,
    end: 20,
    accent: "resolved_container",
    status: "resolved_container",
    materialRole: "constrains_statement",
    incorporationLabel: "Should split into multiple statements",
    whyThisMatters: "Constrains statement",
    summary: "This expands to 5 propositions / 2 source fragments",
    propositionIds: ["prop:one", "prop:two"],
    sourceFragmentIds: ["frag-1", "frag-2"],
    sourceExcerpt: "Schedule 3 excerpt text.",
    resolvedLocator: "schedule 3",
    rawLocators: ["Schedule 3", "schedule:3"],
    resolutionMode: "container",
    ...overrides,
  };
}

function mockDesktopViewport(): void {
  vi.spyOn(window, "matchMedia").mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

describe("StatementInlineReferenceText", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    mockDesktopViewport();
  });

  it("renders Schedule 3 as a container reference in statement text", () => {
    const statementText = "Records must follow Schedule 3.";
    const span = findLocatorTextSpan(statementText, "Schedule 3");
    expect(span).toBeTruthy();
    const references = [buildReference({ start: span!.start, end: span!.end, label: span!.label })];
    const parts = buildStatementTextParts(statementText, references);

    render(
      <StatementInlineReferenceText
        statementText={statementText}
        parts={parts}
        references={references}
      />,
    );

    const scheduleButton = screen.getByTestId("inline-reference-Schedule 3");
    expect(scheduleButton.textContent).toContain("Schedule 3");
    expect(scheduleButton.className).toContain("rounded-full");
    expect(scheduleButton.getAttribute("aria-label")).toContain("Resolved container legal reference");
  });

  it("shows hover preview without inline expansion", () => {
    const statementText = "Apply regulation 36(4) for nitrogen.";
    const references = [
      buildReference({
        id: "statement::regulation 36(4)::6",
        locator: "regulation 36(4)",
        label: "regulation 36(4)",
        start: 6,
        end: 22,
        accent: "resolved",
        status: "resolved",
        resolutionMode: "exact",
        propositionIds: ["prop:one"],
        sourceFragmentIds: ["frag-reg-36-p4"],
        summary: "Shows the linked proposition for this reference.",
      }),
    ];
    const parts = buildStatementTextParts(statementText, references);

    render(
      <StatementInlineReferenceText
        statementText={statementText}
        parts={parts}
        references={references}
      />,
    );

    fireEvent.mouseEnter(screen.getByTestId("inline-reference-regulation 36(4)"));
    expect(screen.getByTestId("inline-reference-hover-preview").textContent).toContain(
      "regulation 36(4)",
    );
    expect(screen.queryByTestId("inline-reference-expansion")).toBeNull();
  });

  it("accumulates desktop selections instead of toggling them off", () => {
    const statementText = "Records must follow Schedule 3 and regulation 36(4).";
    const scheduleSpan = findLocatorTextSpan(statementText, "Schedule 3");
    const regulationSpan = findLocatorTextSpan(statementText, "regulation 36(4)");
    const references = [
      buildReference({ start: scheduleSpan!.start, end: scheduleSpan!.end }),
      buildReference({
        id: "statement::regulation 36(4)::29",
        locator: "regulation 36(4)",
        label: "regulation 36(4)",
        start: regulationSpan!.start,
        end: regulationSpan!.end,
        accent: "resolved",
        status: "resolved",
        resolutionMode: "exact",
        propositionIds: ["prop:one"],
        summary: "Shows the linked proposition for this reference.",
      }),
    ];
    const parts = buildStatementTextParts(statementText, references);
    const onSelectReference = vi.fn();

    render(
      <StatementInlineReferenceText
        statementText={statementText}
        parts={parts}
        references={references}
        selectedReferenceId={references[0]!.id}
        onSelectReference={onSelectReference}
        accumulateSelection
      />,
    );

    fireEvent.click(screen.getByTestId("inline-reference-Schedule 3"));
    expect(onSelectReference).toHaveBeenLastCalledWith(references[0]!.id);

    fireEvent.click(screen.getByTestId("inline-reference-regulation 36(4)"));
    expect(onSelectReference).toHaveBeenLastCalledWith(references[1]!.id);
  });
});

describe("Legal context mobile drawer", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("falls back to inline drawer on narrow screens", () => {
    vi.spyOn(window, "matchMedia").mockImplementation((query: string) => ({
      matches: query.includes("max-width"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    const statementText = "Records must follow Schedule 3.";
    const span = findLocatorTextSpan(statementText, "Schedule 3");
    const references = [buildReference({ start: span!.start, end: span!.end, label: span!.label })];
    const parts = buildStatementTextParts(statementText, references);
    const panel = (
      <LegalContextPanel
        references={[references[0]!]}
        selectedReferenceId={references[0]!.id}
        propositionById={propositionById}
        variant="drawer"
      />
    );

    render(
      <StatementInlineReferenceText
        statementText={statementText}
        parts={parts}
        references={references}
        selectedReferenceId={references[0]!.id}
        mobilePanel={panel}
      />,
    );

    fireEvent.click(screen.getByTestId("inline-reference-Schedule 3"));
    expect(screen.getByTestId("legal-context-panel")).toBeTruthy();
    expect(screen.getAllByText("First linked proposition text.").length).toBeGreaterThan(0);
    expect(screen.queryByTestId("legal-context-working-set")).toBeNull();
  });

  it("toggles mobile selections off when the same reference is clicked again", () => {
    vi.spyOn(window, "matchMedia").mockImplementation((query: string) => ({
      matches: query.includes("max-width"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    const statementText = "Records must follow Schedule 3.";
    const span = findLocatorTextSpan(statementText, "Schedule 3");
    const references = [buildReference({ start: span!.start, end: span!.end, label: span!.label })];
    const parts = buildStatementTextParts(statementText, references);
    const onSelectReference = vi.fn();

    render(
      <StatementInlineReferenceText
        statementText={statementText}
        parts={parts}
        references={references}
        selectedReferenceId={references[0]!.id}
        onSelectReference={onSelectReference}
        accumulateSelection
        mobilePanel={null}
      />,
    );

    fireEvent.click(screen.getByTestId("inline-reference-Schedule 3"));
    expect(onSelectReference).toHaveBeenLastCalledWith(null);
  });
});
