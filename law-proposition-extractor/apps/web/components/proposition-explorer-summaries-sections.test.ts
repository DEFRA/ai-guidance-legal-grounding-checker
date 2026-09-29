import { describe, expect, it } from "vitest";

import {
  buildSectionsFromPropositionSummaries,
  type PropositionGroupSummary,
} from "./proposition-explorer-helpers";

function dummySummary(i: number, sectionKey: string): PropositionGroupSummary {
  return {
    group_id: `g-${i}`,
    article_key: "art",
    article_heading: "Heading",
    section_cluster_key: sectionKey,
    scope_nav_cluster_key: "scope:equine",
    scope_section_label: "Equine",
    representative_source_record_id: "src-1",
    display_label: `Prop ${i}`,
    proposition_count: 1,
    source_row_count: 1,
    jurisdictions: [],
    primary_scopes: [],
    completeness_status: null,
    review_summary: {},
    wording_status: "single",
    row_ids: [`row-${i}`],
  };
}

describe("buildSectionsFromPropositionSummaries (paginated server list)", () => {
  it("keeps one section entry per input summary (no duplication)", () => {
    const summaries: PropositionGroupSummary[] = [
      ...Array.from({ length: 60 }, (_, i) => dummySummary(i, "sec-a")),
      ...Array.from({ length: 60 }, (_, i) => dummySummary(100 + i, "sec-b")),
    ];
    const sections = buildSectionsFromPropositionSummaries(
      summaries,
      "source_document",
      []
    );
    const total = sections.reduce((n, s) => n + s.summaries.length, 0);
    expect(total).toBe(120);
    expect(sections.length).toBe(2);
  });

  it("buckets by scope mode without losing rows", () => {
    const summaries: PropositionGroupSummary[] = Array.from({ length: 200 }, (_, i) => ({
      ...dummySummary(i, "sec-x"),
      scope_nav_cluster_key: i % 2 === 0 ? "scope:a" : "scope:b",
      scope_section_label: i % 2 === 0 ? "A" : "B",
    }));
    const sections = buildSectionsFromPropositionSummaries(summaries, "by_scope", []);
    const total = sections.reduce((n, s) => n + s.summaries.length, 0);
    expect(total).toBe(200);
    expect(sections.length).toBe(2);
  });
});
