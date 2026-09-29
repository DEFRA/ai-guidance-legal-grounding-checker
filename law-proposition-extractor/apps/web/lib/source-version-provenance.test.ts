import { describe, expect, it } from "vitest";

import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import type {
  PropositionRow,
  SourceRow,
  SourceSnapshotRow,
} from "@/lib/law-statements-index";
import fixture from "@/lib/fixtures/article-49a-source-version-provenance.json";
import {
  buildSourceVersionProvenance,
  collectSourceVersionProvenanceForStatement,
  detectConsumedFormat,
  indexSnapshotsById,
  isLocalOrFileUri,
  resolveSnapshotForProposition,
  truncateHash,
} from "@/lib/source-version-provenance";

const source = fixture.source_records[0] as SourceRow;
const snapshot = fixture.source_snapshots[0] as SourceSnapshotRow;
const fragment = fixture.source_fragments[0] as SourceFragmentRow;
const proposition = fixture.propositions[0] as PropositionRow;

function fragmentMap(): Map<string, SourceFragmentRow> {
  return new Map([[String(fragment.id), fragment]]);
}

describe("source-version-provenance joins", () => {
  it("preserves SourceRecord provenance fields", () => {
    expect(source.source_url).toBe("https://www.legislation.gov.uk/eur/2009/1224/data.xml");
    expect(source.as_of_date).toBeNull();
    expect(source.version_id).toBe("v1");
    expect(source.current_snapshot_id).toBe("snap-demo-1224-v1");
    expect(source.content_hash).toMatch(/^abc123/);
  });

  it("preserves SourceSnapshot provenance fields", () => {
    expect(snapshot.id).toBe("snap-demo-1224-v1");
    expect(snapshot.parser_name).toBe("legislation_gov_uk_data_xml_v1");
    expect(snapshot.retrieved_at).toBe("2026-07-14T15:42:00Z");
    expect(snapshot.as_of_date).toBeNull();
    expect(snapshot.raw_artifact_uri).toMatch(/^file:\/\//);
  });

  it("joins proposition source_snapshot_id to the correct snapshot and source", () => {
    const snapshotById = indexSnapshotsById([snapshot], "run-a");
    const resolved = resolveSnapshotForProposition(proposition, snapshotById, source);
    expect(resolved?.id).toBe("snap-demo-1224-v1");
    expect(resolved?.source_record_id).toBe(source.id);
  });

  it("does not cross-contaminate snapshot caches across runs with the same ids", () => {
    const runA = indexSnapshotsById(
      [{ ...snapshot, content_hash: "hash-run-a" }],
      "run-a",
    );
    const runB = indexSnapshotsById(
      [{ ...snapshot, content_hash: "hash-run-b" }],
      "run-b",
    );
    expect(runA.get("snap-demo-1224-v1")?.content_hash).toBe("hash-run-a");
    expect(runB.get("snap-demo-1224-v1")?.content_hash).toBe("hash-run-b");
    // Maps are independent — replacing run state replaces the map entirely.
    expect(runA).not.toBe(runB);
  });

  it("handles missing snapshot data without crashing", () => {
    const view = buildSourceVersionProvenance({
      source,
      snapshot: null,
      propositions: [{ ...proposition, source_snapshot_id: undefined }],
      fragmentById: fragmentMap(),
    });
    expect(view.sourceSnapshotId).toBe("snap-demo-1224-v1");
    expect(view.asOfDateLabel).toBe("Not recorded");
    expect(view.manifestationTypeLabel).toBe("Not recorded");
  });

  it("still loads older bundles lacking snapshot metadata", () => {
    const leanSource: SourceRow = {
      id: "src-old",
      title: "Old source",
      source_url: "https://example.com/doc",
    };
    const leanProp: PropositionRow = {
      id: "prop-old",
      source_record_id: "src-old",
      proposition_text: "Older proposition",
    };
    const view = buildSourceVersionProvenance({
      source: leanSource,
      snapshot: null,
      propositions: [leanProp],
      fragmentById: new Map(),
    });
    expect(view.sourceRecordId).toBe("src-old");
    expect(view.sourceSnapshotId).toBeNull();
    expect(view.knowledgeAbsent.some((item) => item.id === "outstanding_effects")).toBe(false);
  });
});

describe("Article 49a provenance truthfulness", () => {
  const view = buildSourceVersionProvenance({
    source,
    snapshot,
    propositions: [proposition],
    fragmentById: fragmentMap(),
  });

  it("identifies legislation.gov.uk data.xml consumption", () => {
    expect(view.authorityLabel).toBe("legislation.gov.uk");
    expect(view.consumedFormat).toBe("data.xml");
    expect(detectConsumedFormat(source.source_url)).toBe("data.xml");
    expect(view.consumedSourceUrl).toBe(
      "https://www.legislation.gov.uk/eur/2009/1224/data.xml",
    );
  });

  it("keeps snapshot identity and truncated hash", () => {
    expect(view.sourceSnapshotId).toBe("snap-demo-1224-v1");
    expect(view.contentHashShort).toBe(truncateHash(view.contentHash));
    expect(view.contentHashShort).not.toBe(view.contentHash);
  });

  it("shows as-of and manifestation as not recorded", () => {
    expect(view.asOfDate).toBeNull();
    expect(view.asOfDateLabel).toBe("Not recorded");
    expect(view.manifestationType).toBeNull();
    expect(view.manifestationTypeLabel).toBe("Not recorded");
  });

  it("does not treat version_id v1 as a legislative manifestation", () => {
    expect(view.versionId).toBe("v1");
    expect(view.versionIdIsLegislativeManifestation).toBe(false);
  });

  it("does not present retrieval timestamp as legal as-of", () => {
    expect(view.retrievedAt).toBe("2026-07-14T15:42:00Z");
    expect(view.retrievedAtLabel).toBeTruthy();
    expect(view.asOfDateLabel).toBe("Not recorded");
    expect(view.retrievedAtLabel).not.toBe(view.asOfDateLabel);
  });

  it("separates consumed URL from live HTML provision URL", () => {
    expect(view.consumedSourceUrl).toContain("/data.xml");
    expect(view.liveHtmlUrl).toBe(
      "https://www.legislation.gov.uk/eur/2009/1224/article/49a/1",
    );
    expect(view.liveHtmlUrl).not.toBe(view.consumedSourceUrl);
  });

  it("never treats temporary file URI as a browser link target", () => {
    expect(isLocalOrFileUri(view.rawArtifactUri)).toBe(true);
    expect(view.rawArtifactIsLocalPath).toBe(true);
  });

  it("falls back to fragment inspection when full snapshot text is unavailable", () => {
    expect(view.hasPersistedSnapshotText).toBe(false);
    expect(view.snapshotInspection).toBe("fragment_only");
    expect(view.fragmentText).toContain("minimum conservation reference size");
  });

  it("records snapshot identity knowledge without claiming amendments", () => {
    const recordedIds = view.knowledgeRecorded.map((item) => item.id);
    const absentIds = view.knowledgeAbsent.map((item) => item.id);
    expect(recordedIds).toContain("snapshot_identity");
    expect(recordedIds).toContain("retrieved_at");
    expect(recordedIds).toContain("content_hash");
    expect(recordedIds).toContain("parser");
    expect(recordedIds).toContain("proposition_snapshot_link");
    expect(absentIds).toContain("as_of_date");
    expect(absentIds).toContain("manifestation_type");
    expect(absentIds).toContain("outstanding_effects");
    expect(absentIds).toContain("affecting_instruments");
    expect(absentIds).toContain("historical_manifestations");
    expect(view.knowledgeAbsent.find((item) => item.id === "outstanding_effects")?.status).toBe(
      "not_assessed",
    );
  });

  it("renders revised manifestation with disclaimer and distinct dates", () => {
    const revisedSnapshot: SourceSnapshotRow = {
      ...snapshot,
      manifestation_type: "revised",
      manifestation_basis: "source_metadata",
      as_of_date: null,
      resolved_as_of_date: null,
      source_revision_date: "2025-02-27",
    };
    const revisedView = buildSourceVersionProvenance({
      source,
      snapshot: revisedSnapshot,
      propositions: [proposition],
      fragmentById: fragmentMap(),
    });
    expect(revisedView.manifestationType).toBe("revised");
    expect(revisedView.manifestationTypeLabel).toBe("Revised text");
    expect(revisedView.manifestationBasisLabel).toMatch(/source metadata/i);
    expect(revisedView.asOfDateLabel).toBe("Not recorded");
    expect(revisedView.retrievedAtLabel).toBeTruthy();
    expect(revisedView.revisedManifestationDisclaimer).toMatch(
      /has not independently verified or applied the amendment history/i,
    );
    expect(revisedView.knowledgeRecorded.map((item) => item.id)).toContain("manifestation_type");
    expect(revisedView.knowledgeAbsent.map((item) => item.id)).toContain("outstanding_effects");
    expect(revisedView.versionId).toBe("v1");
    expect(revisedView.versionIdIsLegislativeManifestation).toBe(false);
  });

  it("renders point-in-time requested and resolved dates distinctly", () => {
    const pitSnapshot: SourceSnapshotRow = {
      ...snapshot,
      manifestation_type: "point_in_time",
      manifestation_basis: "request_and_source_metadata",
      requested_as_of_date: "2020-12-31",
      resolved_as_of_date: "2020-12-31",
      as_of_date: "2020-12-31",
      requested_manifestation: "point_in_time",
      resolved_manifestation: "point_in_time",
    };
    const pitView = buildSourceVersionProvenance({
      source,
      snapshot: pitSnapshot,
      propositions: [proposition],
      fragmentById: fragmentMap(),
    });
    expect(pitView.manifestationTypeLabel).toBe("Point-in-time text");
    expect(pitView.requestedAsOfDateLabel).toMatch(/December.*31.*2020|31.*December.*2020/i);
    expect(pitView.resolvedAsOfDateLabel).toMatch(/December.*31.*2020|31.*December.*2020/i);
    expect(pitView.retrievedAt).toBe("2026-07-14T15:42:00Z");
    expect(pitView.retrievedAtLabel).not.toBe(pitView.resolvedAsOfDateLabel);
  });

  it("collects statement-level provenance via proposition join", () => {
    const views = collectSourceVersionProvenanceForStatement({
      propositionIds: [proposition.id],
      propositionById: new Map([[proposition.id, proposition]]),
      sourceById: new Map([[source.id, source]]),
      snapshotById: indexSnapshotsById([snapshot]),
      fragmentById: fragmentMap(),
    });
    expect(views).toHaveLength(1);
    expect(views[0]?.sourceSnapshotId).toBe("snap-demo-1224-v1");
  });
});
