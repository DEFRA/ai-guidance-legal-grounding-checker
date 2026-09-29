import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LegalContextPanel } from "@/components/legal-context-panel";
import {
  AUTHORITIES_EMPTY_STATE,
  AUTHORITIES_IN_PLAY_LABEL,
} from "@/lib/legal-authority-display";
import type { PropositionRow } from "@/lib/law-statements-index";
import {
  INLINE_REFERENCE_PREVIEW_LIMIT,
  type InlineLegalReference,
} from "@/lib/statement-inline-references";

const propositionById = new Map<string, PropositionRow>([
  ["prop:one", { id: "prop:one", proposition_text: "First linked proposition text." }],
  ["prop:two", { id: "prop:two", proposition_text: "Second linked proposition text." }],
  ["prop:three", { id: "prop:three", proposition_text: "Third linked proposition text." }],
  ["prop:four", { id: "prop:four", proposition_text: "Fourth linked proposition text." }],
  ["prop:five", { id: "prop:five", proposition_text: "Fifth linked proposition text." }],
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
    propositionIds: ["prop:one", "prop:two", "prop:three", "prop:four", "prop:five"],
    sourceFragmentIds: ["frag-1", "frag-2"],
    sourceExcerpt: "Schedule 3 excerpt text.",
    resolvedLocator: "schedule 3",
    rawLocators: ["Schedule 3", "schedule:3"],
    resolutionMode: "container",
    ...overrides,
  };
}

describe("LegalContextPanel workspace", () => {
  afterEach(() => {
    cleanup();
  });

  it("shows the empty state without developer details", () => {
    render(
      <LegalContextPanel
        references={[]}
        selectedReferenceId={null}
        propositionById={propositionById}
      />,
    );

    expect(screen.getByTestId("legal-context-panel-empty")).toBeTruthy();
    expect(screen.getByText(AUTHORITIES_IN_PLAY_LABEL)).toBeTruthy();
    expect(screen.getByText(AUTHORITIES_EMPTY_STATE)).toBeTruthy();
    expect(screen.queryByText("Developer details")).toBeNull();
  });

  it("renders sticky workspace chrome with breadcrumb navigation", () => {
    const references = [
      buildReference({}),
      buildReference({
        id: "statement::regulation 36(4)::6",
        locator: "regulation 36(4)",
        label: "regulation 36(4)",
        accent: "resolved",
        status: "resolved",
        resolutionMode: "exact",
        propositionIds: ["prop:one"],
        summary: "Shows the linked proposition for this reference.",
      }),
    ];

    render(
      <LegalContextPanel
        references={references}
        selectedReferenceId={references[1]!.id}
        propositionById={propositionById}
      />,
    );

    const panel = screen.getByTestId("legal-context-panel");
    expect(panel.className).toContain("sticky");
    expect(panel.className).toContain("top-4");
    expect(panel.className).toContain("max-h-[calc(100vh-32px)]");
    expect(panel.className).toContain("overflow-auto");

    const breadcrumbItems = screen.getAllByTestId("legal-context-breadcrumb-item");
    expect(breadcrumbItems.map((item) => item.textContent)).toEqual([
      "Schedule 3",
      "regulation 36(4)",
    ]);
  });

  it("syncs selection when a breadcrumb item is clicked", () => {
    const references = [
      buildReference({}),
      buildReference({
        id: "statement::regulation 36(4)::6",
        locator: "regulation 36(4)",
        label: "regulation 36(4)",
        accent: "resolved",
        status: "resolved",
        resolutionMode: "exact",
        propositionIds: ["prop:one"],
        summary: "Shows the linked proposition for this reference.",
      }),
    ];
    const onSelectReference = vi.fn();

    render(
      <LegalContextPanel
        references={references}
        selectedReferenceId={references[1]!.id}
        onSelectReference={onSelectReference}
        propositionById={propositionById}
      />,
    );

    fireEvent.click(screen.getAllByTestId("legal-context-breadcrumb-item")[0]!);
    expect(onSelectReference).toHaveBeenCalledWith(references[0]!.id);
  });

  it("removes a card from the workspace", () => {
    const references = [buildReference({})];
    const onRemoveReference = vi.fn();

    render(
      <LegalContextPanel
        references={references}
        selectedReferenceId={references[0]!.id}
        onRemoveReference={onRemoveReference}
        propositionById={propositionById}
      />,
    );

    fireEvent.click(screen.getByTestId("legal-context-card-remove"));
    expect(onRemoveReference).toHaveBeenCalledWith(references[0]!.id);
  });

  it("shows human summaries and supporting proposition bullets with show all", () => {
    render(
      <LegalContextPanel
        references={[buildReference({})]}
        selectedReferenceId="statement::Schedule 3::10"
        propositionById={propositionById}
      />,
    );

    expect(screen.getAllByText("First linked proposition text.").length).toBeGreaterThan(0);
    expect(screen.getByText("5 supporting propositions")).toBeTruthy();
    expect(screen.getByText("Why it matters")).toBeTruthy();
    expect(screen.getByText("Constrains statement")).toBeTruthy();
    expect(screen.queryByText("Resolved container")).toBeNull();
    expect(screen.getAllByTestId("legal-context-proposition")).toHaveLength(
      INLINE_REFERENCE_PREVIEW_LIMIT,
    );
    fireEvent.click(screen.getByText("Show all supporting propositions"));
    expect(screen.getAllByTestId("legal-context-proposition")).toHaveLength(5);
  });

  it("hides developer IDs until developer details is opened", () => {
    render(
      <LegalContextPanel
        references={[
          buildReference({
            propositionIds: ["prop:one"],
          }),
        ]}
        selectedReferenceId="statement::Schedule 3::10"
        propositionById={propositionById}
      />,
    );

    const details = screen.getByText("Developer details").closest("details");
    expect(details?.hasAttribute("open")).toBe(false);
    fireEvent.click(screen.getByText("Developer details"));
    expect(details?.hasAttribute("open")).toBe(true);
    expect(screen.getByTestId("legal-context-developer-details").textContent).toContain("prop:one");
  });
});
