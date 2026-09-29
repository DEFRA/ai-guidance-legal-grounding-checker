import { describe, expect, it } from "vitest";

import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import type { PropositionRow } from "@/lib/law-statements-index";
import fixture from "@/lib/fixtures/article-49a-source-legal-effects.json";
import {
  buildSourceLegalEffectsView,
  effectCategoryLabel,
  effectHasAffectingInstrumentIds,
  effectHasFragmentLinks,
  effectStatusLabel,
  emptySourceLegalEffectsArtifact,
  findRelevantEffectsForProposition,
  independentConsumptionStatusLabel,
  isLocatorAncestor,
  isPlausibleStructuralParentEdge,
  normalizeOutstandingEffectsStatus,
  outstandingEffectsStatusLabel,
  parseSourceLegalEffectsArtifact,
  type SourceLegalEffectsArtifactRow,
} from "@/lib/source-legal-effects";
import {
  buildSourceVersionProvenance,
  type SourceLegalEffectsKnowledgeInput,
} from "@/lib/source-version-provenance";
import type { SourceRow, SourceSnapshotRow } from "@/lib/law-statements-index";

const artifact: SourceLegalEffectsArtifactRow = {
  schema_version: fixture.schema_version,
  run_id: fixture.run_id,
  effects: fixture.effects,
  effect_links: fixture.effect_links,
  outstanding_effects_status: fixture.outstanding_effects_status,
  diagnostics: fixture.diagnostics,
  metadata: fixture.metadata,
};

const fragments = fixture.source_fragments as SourceFragmentRow[];
const propositions = fixture.propositions as PropositionRow[];
const source = fixture.source_records[0] as SourceRow;
const snapshot = fixture.source_snapshots[0] as SourceSnapshotRow;

function fragmentMap(): Map<string, SourceFragmentRow> {
  return new Map(fragments.map((row) => [String(row.id), row]));
}

function prop(id: string): PropositionRow {
  const row = propositions.find((item) => item.id === id);
  if (!row) {
    throw new Error(`Missing proposition ${id}`);
  }
  return row;
}

describe("source-legal-effects loading and models", () => {
  it("parses API envelope fields once per run", () => {
    const parsed = parseSourceLegalEffectsArtifact(
      {
        run_id: "run-demo",
        artifact_present: true,
        source_legal_effects: artifact,
      },
      "run-demo",
    );
    expect(parsed.effects).toHaveLength(5);
    expect(parsed.effect_links).toHaveLength(5);
    expect(parsed.outstanding_effects_status).toBe("source_status_unknown");
    expect(parsed.effects[1]?.annotation_label).toBe("F2");
    expect(parsed.effect_links[1]?.affected_locator).toBe("article:49a:paragraph:1");
  });

  it("loads older runs without the artifact as empty unknown", () => {
    const empty = emptySourceLegalEffectsArtifact("run-old");
    expect(empty.effects).toEqual([]);
    expect(empty.effect_links).toEqual([]);
    expect(empty.outstanding_effects_status).toBe("source_status_unknown");
    expect(parseSourceLegalEffectsArtifact(null, "run-old").effects).toEqual([]);
    expect(parseSourceLegalEffectsArtifact({}, "run-old").outstanding_effects_status).toBe(
      "source_status_unknown",
    );
  });

  it("scopes effects by run snapshot and does not collide on identical labels", () => {
    const view = buildSourceLegalEffectsView({
      sourceRecordId: "src-demo-1224",
      sourceSnapshotId: "snap-demo-1224-revised",
      propositions: [prop("prop-demo-49a-p1-separate")],
      artifact,
      fragmentById: fragmentMap(),
    });
    expect(view.totalEffectCount).toBe(4);
    expect(view.relevant.map((item) => item.effect.annotation_label)).toEqual(["F1", "F2"]);
    expect(view.relevant.every((item) => item.effect.source_snapshot_id === "snap-demo-1224-revised")).toBe(
      true,
    );
    expect(view.relevant.some((item) => item.effect.id === "sourceeffect:other-snap-f2")).toBe(false);
  });
});

describe("effect-to-proposition relevance matching", () => {
  it("marks an effect directly linked to the selected fragment as relevant", () => {
    const matches = findRelevantEffectsForProposition({
      proposition: prop("prop-demo-49a-p1-separate"),
      artifact,
      fragmentById: fragmentMap(),
    });
    const f2 = matches.find((item) => item.effect.annotation_label === "F2");
    expect(f2?.relevance).toBe("direct");
    expect(f2?.matchedFragmentId).toBe("frag-demo-49a-p1");
  });

  it("identifies article-level F1 as structurally inherited for paragraph descendants", () => {
    const matches = findRelevantEffectsForProposition({
      proposition: prop("prop-demo-49a-p1-separate"),
      artifact,
      fragmentById: fragmentMap(),
    });
    const f1 = matches.find((item) => item.effect.annotation_label === "F1");
    expect(f1?.relevance).toBe("structural");
    expect(f1?.ancestorFragmentId).toBe("frag-demo-49a");
    expect(isLocatorAncestor("article:49a", "article:49a:paragraph:1")).toBe(true);
  });

  it("does not treat sibling paragraph effects as relevant", () => {
    const matches = findRelevantEffectsForProposition({
      proposition: prop("prop-demo-49a-p1-separate"),
      artifact,
      fragmentById: fragmentMap(),
    });
    const labels = matches.map((item) => item.effect.annotation_label);
    expect(labels).toContain("F2");
    expect(labels).not.toContain("F3");
    expect(labels).not.toContain("F4");
  });

  it("excludes effects from another source snapshot", () => {
    const matches = findRelevantEffectsForProposition({
      proposition: prop("prop-demo-49a-p1-separate"),
      artifact,
      fragmentById: fragmentMap(),
    });
    expect(matches.some((item) => item.effect.id === "sourceeffect:other-snap-f2")).toBe(false);
  });

  it("keeps locator-only fallback snapshot-scoped", () => {
    const locatorOnlyArtifact: SourceLegalEffectsArtifactRow = {
      ...artifact,
      effect_links: [
        {
          id: "link-locator-only",
          effect_id: "sourceeffect:f2bbbbbbbbbbbb",
          source_record_id: "src-demo-1224",
          source_snapshot_id: "snap-demo-1224-revised",
          source_fragment_id: null,
          affected_locator: "article:49a:paragraph:1",
          linkage_status: "locator_only",
        },
      ],
      effects: artifact.effects.map((effect) =>
        effect.annotation_label === "F2"
          ? { ...effect, affected_source_fragment_id: null }
          : effect,
      ),
    };
    const matches = findRelevantEffectsForProposition({
      proposition: prop("prop-demo-49a-p1-separate"),
      artifact: locatorOnlyArtifact,
      fragmentById: fragmentMap(),
    });
    expect(matches.some((item) => item.effect.annotation_label === "F2")).toBe(true);
  });

  it("orders relevance deterministically and dedupes duplicate links", () => {
    const duplicated: SourceLegalEffectsArtifactRow = {
      ...artifact,
      effect_links: [
        ...artifact.effect_links,
        {
          id: "sourceeffectlink:f2-p1-dup",
          effect_id: "sourceeffect:f2bbbbbbbbbbbb",
          source_record_id: "src-demo-1224",
          source_snapshot_id: "snap-demo-1224-revised",
          source_fragment_id: "frag-demo-49a-p1",
          affected_locator: "article:49a:paragraph:1",
          linkage_status: "linked",
        },
      ],
    };
    const view = buildSourceLegalEffectsView({
      sourceRecordId: "src-demo-1224",
      sourceSnapshotId: "snap-demo-1224-revised",
      propositions: [
        prop("prop-demo-49a-p1-separate"),
        prop("prop-demo-49a-p1-no-mixing"),
      ],
      artifact: duplicated,
      fragmentById: fragmentMap(),
    });
    expect(view.relevant.map((item) => item.effect.annotation_label)).toEqual(["F1", "F2"]);
    expect(view.relevant.filter((item) => item.effect.annotation_label === "F2")).toHaveLength(1);
  });
});

describe("Article 49a paragraph relevance regression", () => {
  it("paragraph 1 shows F2 direct and F1 structural; not F3/F4", () => {
    const view = buildSourceLegalEffectsView({
      sourceRecordId: "src-demo-1224",
      sourceSnapshotId: "snap-demo-1224-revised",
      propositions: [prop("prop-demo-49a-p1-separate")],
      artifact,
      fragmentById: fragmentMap(),
    });
    expect(view.relevantLabels).toEqual(["F1", "F2"]);
    expect(view.relevant.find((item) => item.effect.annotation_label === "F2")?.relevance).toBe(
      "direct",
    );
    expect(view.relevant.find((item) => item.effect.annotation_label === "F1")?.relevance).toBe(
      "structural",
    );
    expect(view.other.map((item) => item.annotation_label).sort()).toEqual(["F3", "F4"]);
  });

  it("paragraph 2 shows F3 direct plus structural F1", () => {
    const view = buildSourceLegalEffectsView({
      sourceRecordId: "src-demo-1224",
      sourceSnapshotId: "snap-demo-1224-revised",
      propositions: [prop("prop-demo-49a-p2-pelagic")],
      artifact,
      fragmentById: fragmentMap(),
    });
    expect(view.relevantLabels).toEqual(["F1", "F3"]);
    expect(view.relevant.find((item) => item.effect.annotation_label === "F3")?.relevance).toBe(
      "direct",
    );
  });

  it("paragraph 3 shows F4 direct plus structural F1", () => {
    const view = buildSourceLegalEffectsView({
      sourceRecordId: "src-demo-1224",
      sourceSnapshotId: "snap-demo-1224-revised",
      propositions: [prop("prop-demo-49a-p3-monitoring")],
      artifact,
      fragmentById: fragmentMap(),
    });
    expect(view.relevantLabels).toEqual(["F1", "F4"]);
    expect(view.relevant.find((item) => item.effect.annotation_label === "F4")?.relevance).toBe(
      "direct",
    );
  });
});

describe("legacy invalid parentage defence", () => {
  it("rejects sibling article parent edges and keeps container parents", () => {
    const article1: SourceFragmentRow = {
      id: "frag-a1",
      locator: "article:1",
      source_record_id: "src-demo-1224",
      source_snapshot_id: "snap-demo-1224-revised",
      parent_fragment_id: null,
    };
    const article49a: SourceFragmentRow = {
      id: "frag-a49a",
      locator: "article:49a",
      source_record_id: "src-demo-1224",
      source_snapshot_id: "snap-demo-1224-revised",
      parent_fragment_id: "frag-a1",
    };
    const chapter: SourceFragmentRow = {
      id: "frag-ch2",
      locator: "chapter:2",
      source_record_id: "src-demo-1224",
      source_snapshot_id: "snap-demo-1224-revised",
      parent_fragment_id: null,
    };
    expect(isPlausibleStructuralParentEdge(article1, article49a)).toBe(false);
    expect(isPlausibleStructuralParentEdge(chapter, article49a)).toBe(true);
    expect(
      isPlausibleStructuralParentEdge(
        fragments.find((row) => row.id === "frag-demo-49a"),
        fragments.find((row) => row.id === "frag-demo-49a-p1"),
      ),
    ).toBe(true);
  });

  it("does not inherit Article 1 effects via a bogus article:49a→article:1 parent", () => {
    const pollutedFragments: SourceFragmentRow[] = [
      {
        id: "frag-demo-a1",
        locator: "article:1",
        source_record_id: "src-demo-1224",
        source_snapshot_id: "snap-demo-1224-revised",
        parent_fragment_id: null,
      },
      {
        id: "frag-demo-49a",
        locator: "article:49a",
        source_record_id: "src-demo-1224",
        source_snapshot_id: "snap-demo-1224-revised",
        parent_fragment_id: "frag-demo-a1",
      },
      {
        id: "frag-demo-49a-p1",
        locator: "article:49a:paragraph:1",
        source_record_id: "src-demo-1224",
        source_snapshot_id: "snap-demo-1224-revised",
        parent_fragment_id: "frag-demo-49a",
      },
    ];
    const pollutedMap = new Map(pollutedFragments.map((row) => [String(row.id), row]));
    const pollutedArtifact: SourceLegalEffectsArtifactRow = {
      ...artifact,
      effects: [
        {
          id: "sourceeffect:article1-f1",
          source_record_id: "src-demo-1224",
          source_snapshot_id: "snap-demo-1224-revised",
          annotation_label: "F1",
          affected_locator: "article:1",
          affected_source_fragment_id: "frag-demo-a1",
        },
        {
          id: "sourceeffect:f2bbbbbbbbbbbb",
          source_record_id: "src-demo-1224",
          source_snapshot_id: "snap-demo-1224-revised",
          annotation_label: "F2",
          affected_locator: "article:49a:paragraph:1",
          affected_source_fragment_id: "frag-demo-49a-p1",
        },
      ],
      effect_links: [
        {
          id: "link-a1",
          effect_id: "sourceeffect:article1-f1",
          source_record_id: "src-demo-1224",
          source_snapshot_id: "snap-demo-1224-revised",
          source_fragment_id: "frag-demo-a1",
          affected_locator: "article:1",
          linkage_status: "linked",
        },
        {
          id: "link-p1",
          effect_id: "sourceeffect:f2bbbbbbbbbbbb",
          source_record_id: "src-demo-1224",
          source_snapshot_id: "snap-demo-1224-revised",
          source_fragment_id: "frag-demo-49a-p1",
          affected_locator: "article:49a:paragraph:1",
          linkage_status: "linked",
        },
      ],
    };
    const matches = findRelevantEffectsForProposition({
      proposition: prop("prop-demo-49a-p1-separate"),
      artifact: pollutedArtifact,
      fragmentById: pollutedMap,
    });
    expect(matches.map((item) => item.effect.annotation_label)).toEqual(["F2"]);
  });
});

describe("status truthfulness labels", () => {
  it("renders source statuses without claiming Law Proposition Extractor applied effects", () => {
    expect(effectStatusLabel("source_status_unknown")).toBe("Not stated by consumed source");
    expect(effectStatusLabel("source_marks_outstanding")).toMatch(/source marks.*outstanding/i);
    expect(effectStatusLabel("source_marks_applied")).toMatch(/source marks.*applied/i);
    expect(effectStatusLabel("source_marks_applied")).not.toBe("Applied");
    expect(independentConsumptionStatusLabel("not_assessed")).toBe(
      "Independent consumption could not be assessed from the available identifiers",
    );
    expect(independentConsumptionStatusLabel("not_matched")).toBe(
      "No matching independently consumed source was found in this run",
    );
    expect(independentConsumptionStatusLabel("present_in_source_register_but_not_consumed")).toBe(
      "Present in the run's source register, but not independently consumed",
    );
    expect(independentConsumptionStatusLabel("consumed_in_current_run")).toBe(
      "Affecting instrument independently consumed in this run",
    );
    expect(outstandingEffectsStatusLabel("source_status_unknown")).toMatch(/Not established/i);
    expect(outstandingEffectsStatusLabel("source_status_unknown")).not.toMatch(/no outstanding/i);
    expect(normalizeOutstandingEffectsStatus("source_status_unknown")).toBe("source_status_unknown");
    expect(effectCategoryLabel("substitution")).toBe("Substitution");
  });

  it("keeps revised manifestation from inventing outstanding=none in knowledge lists", () => {
    const snapshotEffects = artifact.effects.filter(
      (effect) => effect.source_snapshot_id === "snap-demo-1224-revised",
    );
    const knowledge: SourceLegalEffectsKnowledgeInput = {
      hasEffects: true,
      hasFragmentLinks: effectHasFragmentLinks(snapshotEffects, artifact.effect_links),
      hasAffectingInstrumentIds: effectHasAffectingInstrumentIds(snapshotEffects),
      outstandingEffectsStatus: "source_status_unknown",
      anyAffectingInstrumentConsumed: false,
    };
    const view = buildSourceVersionProvenance({
      source,
      snapshot,
      propositions: [prop("prop-demo-49a-p1-separate")],
      fragmentById: fragmentMap(),
      sourceLegalEffectsKnowledge: knowledge,
    });
    expect(view.manifestationType).toBe("revised");
    expect(view.revisedManifestationDisclaimer).toBeTruthy();
    expect(view.knowledgeRecorded.map((item) => item.id)).toEqual(
      expect.arrayContaining([
        "change_annotations",
        "annotation_fragment_links",
        "affecting_instrument_ids",
      ]),
    );
    expect(view.knowledgeAbsent.find((item) => item.id === "outstanding_effects")?.status).toBe(
      "not_established",
    );
    expect(view.knowledgeAbsent.map((item) => item.id)).toEqual(
      expect.arrayContaining([
        "judit_applied_changes",
        "affecting_instruments_assessed",
        "historical_manifestations",
      ]),
    );
    expect(view.knowledgeRecorded.map((item) => item.id)).not.toContain("affecting_instruments");
  });
});
