import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import type {
  ManifestationEvidenceItem,
  PropositionRow,
  SourceManifestationBasis,
  SourceManifestationType,
  SourceRow,
  SourceSnapshotRow,
} from "@/lib/law-statements-index";
import { legislationProvisionUrl } from "@/lib/legislation-gov-uk-url";

export type ProvenanceFieldStatus =
  | "recorded"
  | "not_recorded"
  | "not_assessed"
  | "not_established"
  | "unavailable";

export type ProvenanceKnowledgeItem = {
  id: string;
  label: string;
  status: ProvenanceFieldStatus;
  /** When true, row is legislation.gov.uk-specific and omitted for other authorities. */
  legislationSpecific?: boolean;
};

export type SourceVersionProvenanceStatus =
  | "snapshot_identified"
  | "version_semantics_incomplete"
  | "consumed_snapshot_unavailable";

export type SourceVersionProvenanceView = {
  sourceRecordId: string;
  sourceSnapshotId: string | null;
  propositionIds: string[];
  fragmentLocator: string | null;
  sourceFragmentId: string | null;
  fragmentHash: string | null;
  fragmentText: string | null;
  authorityLabel: string;
  isLegislationGovUk: boolean;
  consumedFormat: string | null;
  consumedSourceUrl: string | null;
  liveHtmlUrl: string | null;
  retrievedAt: string | null;
  retrievedAtLabel: string | null;
  asOfDate: string | null;
  asOfDateLabel: string;
  requestedAsOfDate: string | null;
  requestedAsOfDateLabel: string | null;
  resolvedAsOfDate: string | null;
  resolvedAsOfDateLabel: string | null;
  sourceRevisionDate: string | null;
  sourceRevisionDateLabel: string | null;
  contentHash: string | null;
  contentHashShort: string | null;
  parserName: string | null;
  versionId: string | null;
  /** Never treat intake version_id as a legislative manifestation. */
  versionIdIsLegislativeManifestation: false;
  manifestationType: SourceManifestationType | null;
  manifestationTypeLabel: string;
  manifestationBasis: SourceManifestationBasis | null;
  manifestationBasisLabel: string | null;
  requestedManifestation: SourceManifestationType | null;
  requestedManifestationLabel: string | null;
  resolvedManifestation: SourceManifestationType | null;
  resolvedManifestationLabel: string | null;
  manifestationEvidence: ManifestationEvidenceItem[];
  /** Concise disclaimer when manifestation is revised (authority label only). */
  revisedManifestationDisclaimer: string | null;
  hasPersistedSnapshotText: boolean;
  rawArtifactUri: string | null;
  /** True when raw_artifact_uri looks like a non-servable local path. */
  rawArtifactIsLocalPath: boolean;
  snapshotInspection: "api_available" | "fragment_only" | "unavailable";
  knowledgeRecorded: ProvenanceKnowledgeItem[];
  knowledgeAbsent: ProvenanceKnowledgeItem[];
  statusChips: SourceVersionProvenanceStatus[];
};

const LEGISLATION_HOST = /(^|\.)legislation\.gov\.uk$/i;

const REVISED_DISCLAIMER =
  "This records the manifestation supplied by legislation.gov.uk. Law Proposition Extractor has not independently verified or applied the amendment history.";

function trimOrNull(value: unknown): string | null {
  const text = String(value ?? "").trim();
  return text ? text : null;
}

function asManifestationType(value: unknown): SourceManifestationType | null {
  const text = trimOrNull(value);
  if (
    text === "original" ||
    text === "revised" ||
    text === "point_in_time" ||
    text === "prospective" ||
    text === "unknown"
  ) {
    return text;
  }
  return null;
}

function asManifestationBasis(value: unknown): SourceManifestationBasis | null {
  const text = trimOrNull(value);
  if (
    text === "request_url" ||
    text === "resolved_url" ||
    text === "source_metadata" ||
    text === "request_and_source_metadata" ||
    text === "unavailable"
  ) {
    return text;
  }
  return null;
}

export function manifestationTypeLabel(type: SourceManifestationType | null | undefined): string {
  switch (type) {
    case "original":
      return "Original text";
    case "revised":
      return "Revised text";
    case "point_in_time":
      return "Point-in-time text";
    case "prospective":
      return "Prospective text";
    case "unknown":
      return "Not recorded";
    default:
      return "Not recorded";
  }
}

export function manifestationBasisLabel(
  basis: SourceManifestationBasis | null | undefined,
): string | null {
  switch (basis) {
    case "request_url":
      return "Request URL";
    case "resolved_url":
      return "Resolved URL";
    case "source_metadata":
      return "legislation.gov.uk source metadata";
    case "request_and_source_metadata":
      return "Request URL and source metadata";
    case "unavailable":
      return null;
    default:
      return null;
  }
}

export function isHttpUrl(value: string | null | undefined): boolean {
  const text = String(value ?? "").trim();
  if (!text) {
    return false;
  }
  try {
    const parsed = new URL(text);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function isLocalOrFileUri(value: string | null | undefined): boolean {
  const text = String(value ?? "").trim().toLowerCase();
  if (!text) {
    return false;
  }
  return (
    text.startsWith("file:") ||
    text.startsWith("/private/") ||
    text.startsWith("/var/") ||
    text.startsWith("/tmp/") ||
    /^[a-z]:\\/i.test(text)
  );
}

export function truncateHash(hash: string | null | undefined, head = 6, tail = 4): string | null {
  const value = trimOrNull(hash);
  if (!value) {
    return null;
  }
  if (value.length <= head + tail + 1) {
    return value;
  }
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

export function formatProvenanceDateTime(value: string | null | undefined): string | null {
  const raw = trimOrNull(value);
  if (!raw) {
    return null;
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return raw;
  }
  return parsed.toLocaleString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function formatProvenanceDate(value: string | null | undefined): string | null {
  const raw = trimOrNull(value);
  if (!raw) {
    return null;
  }
  // Date-only strings should not be shifted by timezone.
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    const [year, month, day] = raw.split("-").map(Number);
    const parsed = new Date(Date.UTC(year!, month! - 1, day!));
    return parsed.toLocaleDateString(undefined, {
      day: "numeric",
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    });
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return raw;
  }
  return parsed.toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function detectConsumedFormat(sourceUrl: string | null | undefined): string | null {
  const raw = trimOrNull(sourceUrl);
  if (!raw) {
    return null;
  }
  try {
    const path = new URL(raw).pathname.toLowerCase();
    if (path.endsWith("/data.xml") || path.endsWith("data.xml")) {
      return "data.xml";
    }
    if (path.endsWith(".xml")) {
      return "xml";
    }
    if (path.endsWith(".html") || path.endsWith(".htm")) {
      return "html";
    }
  } catch {
    if (/data\.xml/i.test(raw)) {
      return "data.xml";
    }
  }
  return null;
}

export function authorityLabelForSource(input: {
  sourceUrl?: string | null;
  authority?: string | null;
  jurisdiction?: string | null;
}): string {
  const authority = trimOrNull(input.authority);
  if (authority === "legislation_gov_uk") {
    return "legislation.gov.uk";
  }
  const url = trimOrNull(input.sourceUrl);
  if (url) {
    try {
      const host = new URL(url).hostname.toLowerCase();
      if (LEGISLATION_HOST.test(host)) {
        return "legislation.gov.uk";
      }
      return host;
    } catch {
      /* fall through */
    }
  }
  return trimOrNull(input.jurisdiction) ?? "Unknown authority";
}

export function isLegislationGovUkSource(input: {
  sourceUrl?: string | null;
  authority?: string | null;
}): boolean {
  if (trimOrNull(input.authority) === "legislation_gov_uk") {
    return true;
  }
  const url = trimOrNull(input.sourceUrl);
  if (!url) {
    return false;
  }
  try {
    return LEGISLATION_HOST.test(new URL(url).hostname);
  } catch {
    return /legislation\.gov\.uk/i.test(url);
  }
}

/**
 * Build a run-scoped snapshot map. Key is snapshot id only within one run —
 * callers must replace the map when the run changes (do not merge across runs).
 */
export function indexSnapshotsById(
  snapshots: SourceSnapshotRow[],
  runId?: string | null,
): Map<string, SourceSnapshotRow> {
  const map = new Map<string, SourceSnapshotRow>();
  const scoped = trimOrNull(runId);
  for (const row of snapshots) {
    const id = trimOrNull(row.id);
    if (!id) {
      continue;
    }
    // Guard against accidental cross-run reuse when callers pass tagged ids.
    if (scoped && id.includes("::") && !id.startsWith(`${scoped}::`)) {
      continue;
    }
    map.set(id, row);
  }
  return map;
}

export function resolveSnapshotForProposition(
  proposition: PropositionRow,
  snapshotById: Map<string, SourceSnapshotRow>,
  source?: SourceRow | null,
): SourceSnapshotRow | null {
  const direct = trimOrNull(proposition.source_snapshot_id);
  if (direct && snapshotById.has(direct)) {
    return snapshotById.get(direct) ?? null;
  }
  const fallback = trimOrNull(source?.current_snapshot_id);
  if (fallback && snapshotById.has(fallback)) {
    return snapshotById.get(fallback) ?? null;
  }
  return null;
}

function fragmentForProposition(
  proposition: PropositionRow,
  fragmentById: Map<string, SourceFragmentRow>,
): SourceFragmentRow | null {
  const fragmentId = trimOrNull(proposition.source_fragment_id);
  if (!fragmentId) {
    return null;
  }
  return (
    fragmentById.get(fragmentId) ??
    [...fragmentById.values()].find(
      (row) => trimOrNull(row.fragment_id) === fragmentId || trimOrNull(row.id) === fragmentId,
    ) ??
    null
  );
}

function readManifestationFromSnapshot(snapshot: SourceSnapshotRow | null): {
  type: SourceManifestationType | null;
  basis: SourceManifestationBasis | null;
  requestedAsOf: string | null;
  resolvedAsOf: string | null;
  revisionDate: string | null;
  requested: SourceManifestationType | null;
  resolved: SourceManifestationType | null;
  evidence: ManifestationEvidenceItem[];
} {
  if (!snapshot) {
    return {
      type: null,
      basis: null,
      requestedAsOf: null,
      resolvedAsOf: null,
      revisionDate: null,
      requested: null,
      resolved: null,
      evidence: [],
    };
  }
  const meta =
    snapshot.metadata && typeof snapshot.metadata === "object"
      ? (snapshot.metadata.manifestation as Record<string, unknown> | undefined)
      : undefined;

  const type =
    asManifestationType(snapshot.manifestation_type) ??
    asManifestationType(meta?.type) ??
    null;
  const basis =
    asManifestationBasis(snapshot.manifestation_basis) ??
    asManifestationBasis(meta?.basis) ??
    null;
  const requestedAsOf =
    trimOrNull(snapshot.requested_as_of_date) ?? trimOrNull(meta?.requested_as_of_date);
  const resolvedAsOf =
    trimOrNull(snapshot.resolved_as_of_date) ?? trimOrNull(meta?.resolved_as_of_date);
  const revisionDate =
    trimOrNull(snapshot.source_revision_date) ?? trimOrNull(meta?.source_revision_date);
  const requested =
    asManifestationType(snapshot.requested_manifestation) ??
    asManifestationType(meta?.requested_manifestation);
  const resolved =
    asManifestationType(snapshot.resolved_manifestation) ??
    asManifestationType(meta?.resolved_manifestation);
  const evidenceRaw = snapshot.manifestation_evidence ?? meta?.evidence;
  const evidence = Array.isArray(evidenceRaw)
    ? (evidenceRaw as ManifestationEvidenceItem[])
    : [];

  return {
    type: type === "unknown" ? null : type,
    basis,
    requestedAsOf,
    resolvedAsOf,
    revisionDate,
    requested: requested === "unknown" ? null : requested,
    resolved: resolved === "unknown" ? null : resolved,
    evidence,
  };
}

export type SourceLegalEffectsKnowledgeInput = {
  hasEffects: boolean;
  hasFragmentLinks: boolean;
  hasAffectingInstrumentIds: boolean;
  outstandingEffectsStatus: "source_reports_none" | "source_reports_present" | "source_status_unknown";
  anyAffectingInstrumentConsumed: boolean;
};

function buildKnowledgeLists(input: {
  isLegislationGovUk: boolean;
  hasSnapshotId: boolean;
  hasRetrievedAt: boolean;
  hasContentHash: boolean;
  hasParser: boolean;
  hasPropositionSnapshotLink: boolean;
    hasAsOfDate: boolean;
  hasManifestationType: boolean;
  sourceLegalEffectsKnowledge?: SourceLegalEffectsKnowledgeInput | null;
}): { recorded: ProvenanceKnowledgeItem[]; absent: ProvenanceKnowledgeItem[] } {
  const recorded: ProvenanceKnowledgeItem[] = [];
  const absent: ProvenanceKnowledgeItem[] = [];

  const push = (
    item: ProvenanceKnowledgeItem,
    present: boolean,
    absentStatus: ProvenanceFieldStatus = "not_recorded",
  ) => {
    if (item.legislationSpecific && !input.isLegislationGovUk) {
      return;
    }
    if (present) {
      recorded.push({ ...item, status: "recorded" });
    } else {
      absent.push({ ...item, status: absentStatus });
    }
  };

  push(
    { id: "snapshot_identity", label: "Exact source snapshot identity", status: "recorded" },
    input.hasSnapshotId,
  );
  push(
    { id: "retrieved_at", label: "Retrieval timestamp", status: "recorded" },
    input.hasRetrievedAt,
  );
  push({ id: "content_hash", label: "Content hash", status: "recorded" }, input.hasContentHash);
  push({ id: "parser", label: "Parser used", status: "recorded" }, input.hasParser);
  push(
    {
      id: "proposition_snapshot_link",
      label: "Proposition-to-snapshot link",
      status: "recorded",
    },
    input.hasPropositionSnapshotLink,
  );

  push(
    {
      id: "manifestation_type",
      label: "Consumed manifestation type",
      status: "not_recorded",
      legislationSpecific: true,
    },
    input.hasManifestationType,
  );
  push(
    {
      id: "as_of_date",
      label: "Resolved as-of date",
      status: "not_recorded",
      legislationSpecific: true,
    },
    input.hasAsOfDate,
  );

  const effects = input.sourceLegalEffectsKnowledge;
  if (effects?.hasEffects) {
    push(
      {
        id: "change_annotations",
        label: "Change annotations present in consumed source",
        status: "recorded",
        legislationSpecific: true,
      },
      true,
    );
    push(
      {
        id: "annotation_fragment_links",
        label: "Annotation-to-source-fragment links",
        status: "recorded",
        legislationSpecific: true,
      },
      effects.hasFragmentLinks,
      "not_recorded",
    );
    push(
      {
        id: "affecting_instrument_ids",
        label: "Affecting-instrument identifiers supplied by source",
        status: "recorded",
        legislationSpecific: true,
      },
      effects.hasAffectingInstrumentIds,
      "not_recorded",
    );
  }

  const outstandingKnown =
    effects?.outstandingEffectsStatus === "source_reports_none" ||
    effects?.outstandingEffectsStatus === "source_reports_present";
  push(
    {
      id: "outstanding_effects",
      label: outstandingKnown
        ? "Outstanding amendment effects (source-reported status)"
        : "Outstanding amendment effects",
      status: outstandingKnown ? "recorded" : "not_established",
      legislationSpecific: true,
    },
    Boolean(outstandingKnown),
    effects?.hasEffects ? "not_established" : "not_assessed",
  );
  push(
    {
      id: "affecting_instruments",
      label: "Affecting instruments independently consumed",
      status: "not_assessed",
      legislationSpecific: true,
    },
    Boolean(effects?.anyAffectingInstrumentConsumed),
    "not_assessed",
  );
  push(
    {
      id: "judit_applied_changes",
      label: "Whether Law Proposition Extractor independently applied each change",
      status: "not_assessed",
      legislationSpecific: true,
    },
    false,
    "not_assessed",
  );
  if (effects?.hasEffects) {
    push(
      {
        id: "affecting_instruments_assessed",
        label: "Whether affecting instruments were independently consumed",
        status: "not_assessed",
        legislationSpecific: true,
      },
      Boolean(effects.anyAffectingInstrumentConsumed),
      "not_assessed",
    );
  }
  push(
    {
      id: "historical_manifestations",
      label: effects?.hasEffects
        ? "Completeness of amendment history"
        : "Historical amendment lineage reconstructed",
      status: "not_assessed",
      legislationSpecific: true,
    },
    false,
    "not_assessed",
  );

  return { recorded, absent };
}

export function buildSourceVersionProvenance(input: {
  source: SourceRow;
  snapshot: SourceSnapshotRow | null;
  propositions: PropositionRow[];
  fragmentById: Map<string, SourceFragmentRow>;
  sourceLegalEffectsKnowledge?: SourceLegalEffectsKnowledgeInput | null;
}): SourceVersionProvenanceView {
  const { source, snapshot, propositions, fragmentById } = input;
  const primary = propositions[0];
  const fragment = primary ? fragmentForProposition(primary, fragmentById) : null;

  const sourceSnapshotId =
    trimOrNull(snapshot?.id) ??
    trimOrNull(primary?.source_snapshot_id) ??
    trimOrNull(source.current_snapshot_id);

  const consumedSourceUrl = trimOrNull(source.source_url);
  const locator =
    trimOrNull(primary?.fragment_locator) ??
    trimOrNull(fragment?.locator) ??
    null;
  const liveHtmlUrl = legislationProvisionUrl(consumedSourceUrl, locator);
  const isLegislation = isLegislationGovUkSource({
    sourceUrl: consumedSourceUrl,
    authority: snapshot?.authority,
  });

  const retrievedAt =
    trimOrNull(snapshot?.retrieved_at) ?? trimOrNull(source.retrieved_at);
  const manifestation = readManifestationFromSnapshot(snapshot);
  const resolvedAsOf =
    manifestation.resolvedAsOf ??
    (manifestation.type === "point_in_time"
      ? trimOrNull(snapshot?.as_of_date) ?? trimOrNull(source.as_of_date)
      : null);
  // Display as-of: resolved PIT date only — never retrieval time or revision stamp alone.
  const asOfDate = resolvedAsOf;
  const contentHash =
    trimOrNull(snapshot?.content_hash) ?? trimOrNull(source.content_hash);
  const parserName = trimOrNull(snapshot?.parser_name);
  const versionId =
    trimOrNull(snapshot?.version_id) ?? trimOrNull(source.version_id);
  const rawArtifactUri = trimOrNull(snapshot?.raw_artifact_uri);
  const hasPersistedSnapshotText = Boolean(
    snapshot?.has_authoritative_text || trimOrNull(snapshot?.authoritative_text),
  );
  const fragmentText = trimOrNull(fragment?.fragment_text);
  const fragmentHash =
    trimOrNull(fragment?.fragment_hash) ?? trimOrNull(fragment?.text_hash);

  let snapshotInspection: SourceVersionProvenanceView["snapshotInspection"] = "unavailable";
  if (hasPersistedSnapshotText && sourceSnapshotId) {
    snapshotInspection = "api_available";
  } else if (fragmentText) {
    snapshotInspection = "fragment_only";
  }

  const hasManifestationType = Boolean(manifestation.type);
  const knowledge = buildKnowledgeLists({
    isLegislationGovUk: isLegislation,
    hasSnapshotId: Boolean(sourceSnapshotId),
    hasRetrievedAt: Boolean(retrievedAt),
    hasContentHash: Boolean(contentHash),
    hasParser: Boolean(parserName),
    hasPropositionSnapshotLink: propositions.some((row) =>
      Boolean(trimOrNull(row.source_snapshot_id)),
    ),
    hasAsOfDate: Boolean(asOfDate),
    hasManifestationType,
    sourceLegalEffectsKnowledge: input.sourceLegalEffectsKnowledge ?? null,
  });

  const statusChips: SourceVersionProvenanceStatus[] = [];
  if (sourceSnapshotId && contentHash) {
    statusChips.push("snapshot_identified");
  } else if (sourceSnapshotId) {
    statusChips.push("snapshot_identified");
  }
  if (!asOfDate && !hasManifestationType) {
    statusChips.push("version_semantics_incomplete");
  }
  if (snapshotInspection === "unavailable") {
    statusChips.push("consumed_snapshot_unavailable");
  }

  return {
    sourceRecordId: source.id,
    sourceSnapshotId,
    propositionIds: propositions.map((row) => row.id),
    fragmentLocator: locator,
    sourceFragmentId:
      trimOrNull(primary?.source_fragment_id) ??
      trimOrNull(fragment?.fragment_id) ??
      trimOrNull(fragment?.id),
    fragmentHash,
    fragmentText,
    authorityLabel: authorityLabelForSource({
      sourceUrl: consumedSourceUrl,
      authority: snapshot?.authority,
      jurisdiction: source.jurisdiction,
    }),
    isLegislationGovUk: isLegislation,
    consumedFormat: detectConsumedFormat(consumedSourceUrl),
    consumedSourceUrl,
    liveHtmlUrl,
    retrievedAt,
    retrievedAtLabel: formatProvenanceDateTime(retrievedAt),
    asOfDate,
    asOfDateLabel: formatProvenanceDate(asOfDate) ?? "Not recorded",
    requestedAsOfDate: manifestation.requestedAsOf,
    requestedAsOfDateLabel: formatProvenanceDate(manifestation.requestedAsOf),
    resolvedAsOfDate: resolvedAsOf,
    resolvedAsOfDateLabel: formatProvenanceDate(resolvedAsOf),
    sourceRevisionDate: manifestation.revisionDate,
    sourceRevisionDateLabel: formatProvenanceDate(manifestation.revisionDate),
    contentHash,
    contentHashShort: truncateHash(contentHash),
    parserName,
    versionId,
    versionIdIsLegislativeManifestation: false,
    manifestationType: manifestation.type,
    manifestationTypeLabel: manifestationTypeLabel(manifestation.type),
    manifestationBasis: manifestation.basis,
    manifestationBasisLabel: manifestationBasisLabel(manifestation.basis),
    requestedManifestation: manifestation.requested,
    requestedManifestationLabel: manifestation.requested
      ? manifestationTypeLabel(manifestation.requested)
      : null,
    resolvedManifestation: manifestation.resolved,
    resolvedManifestationLabel: manifestation.resolved
      ? manifestationTypeLabel(manifestation.resolved)
      : null,
    manifestationEvidence: manifestation.evidence,
    revisedManifestationDisclaimer:
      manifestation.type === "revised" ? REVISED_DISCLAIMER : null,
    hasPersistedSnapshotText,
    rawArtifactUri,
    rawArtifactIsLocalPath: isLocalOrFileUri(rawArtifactUri),
    snapshotInspection,
    knowledgeRecorded: knowledge.recorded,
    knowledgeAbsent: knowledge.absent,
    statusChips,
  };
}

/**
 * Collect distinct source-version provenance views for a statement's propositions.
 * Groups by consumed snapshot id (falling back to source record id).
 */
export function collectSourceVersionProvenanceForStatement(input: {
  propositionIds: string[];
  propositionById: Map<string, PropositionRow>;
  sourceById: Map<string, SourceRow>;
  snapshotById: Map<string, SourceSnapshotRow>;
  fragmentById: Map<string, SourceFragmentRow>;
  sourceLegalEffectsKnowledgeBySnapshotId?: Map<string, SourceLegalEffectsKnowledgeInput>;
}): SourceVersionProvenanceView[] {
  const groups = new Map<
    string,
    {
      source: SourceRow;
      snapshot: SourceSnapshotRow | null;
      propositions: PropositionRow[];
    }
  >();

  for (const propositionId of input.propositionIds) {
    const proposition = input.propositionById.get(propositionId);
    if (!proposition) {
      continue;
    }
    const sourceRecordId = trimOrNull(proposition.source_record_id);
    if (!sourceRecordId) {
      continue;
    }
    const source = input.sourceById.get(sourceRecordId);
    if (!source) {
      continue;
    }
    const snapshot = resolveSnapshotForProposition(
      proposition,
      input.snapshotById,
      source,
    );
    const groupKey =
      trimOrNull(snapshot?.id) ??
      trimOrNull(proposition.source_snapshot_id) ??
      sourceRecordId;
    const existing = groups.get(groupKey);
    if (existing) {
      existing.propositions.push(proposition);
    } else {
      groups.set(groupKey, { source, snapshot, propositions: [proposition] });
    }
  }

  return [...groups.values()].map((group) => {
    const snapshotId = trimOrNull(group.snapshot?.id);
    const effectsKnowledge =
      (snapshotId
        ? input.sourceLegalEffectsKnowledgeBySnapshotId?.get(snapshotId)
        : undefined) ?? null;
    return buildSourceVersionProvenance({
      source: group.source,
      snapshot: group.snapshot,
      propositions: group.propositions,
      fragmentById: input.fragmentById,
      sourceLegalEffectsKnowledge: effectsKnowledge,
    });
  });
}

export function statusChipLabel(status: SourceVersionProvenanceStatus): string {
  switch (status) {
    case "snapshot_identified":
      return "Snapshot identified";
    case "version_semantics_incomplete":
      return "Version semantics incomplete";
    case "consumed_snapshot_unavailable":
      return "Consumed snapshot unavailable";
    default:
      return status;
  }
}

export function knowledgeStatusLabel(status: ProvenanceFieldStatus): string {
  switch (status) {
    case "recorded":
      return "Recorded";
    case "not_recorded":
      return "Not recorded";
    case "not_assessed":
      return "Not assessed";
    case "not_established":
      return "Not established";
    case "unavailable":
      return "Unavailable";
    default:
      return status;
  }
}
