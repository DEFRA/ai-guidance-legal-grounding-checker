/** Pure helpers for equine corpus coverage UI — grouping and readiness without changing proposition identity. */

export type CorpusSourceBucket =
  | "included_legal"
  | "pending_legal"
  | "excluded_legal"
  | "developer_fixture";

export const READINESS_STEP_LABELS = [
  "Discovery only",
  "Candidate review",
  "Source ingestion",
  "Proposition extraction",
  "Human review",
  "Guidance-ready",
] as const;

export type ReadinessStepLabel = (typeof READINESS_STEP_LABELS)[number];

export function isDeveloperFixtureSourceId(sourceId: unknown): boolean {
  return typeof sourceId === "string" && sourceId.startsWith("fixture-");
}

export function isDiscoveryCandidateRow(row: Record<string, unknown>): boolean {
  return String(row.inclusion_reason ?? "").includes("Discovery candidate only");
}

export function corpusSourceBucket(row: Record<string, unknown>): CorpusSourceBucket {
  const sid = String(row.source_id ?? "");
  if (isDeveloperFixtureSourceId(sid)) {
    return "developer_fixture";
  }
  if (String(row.extraction_status ?? "") === "excluded") {
    return "excluded_legal";
  }
  if (isDiscoveryCandidateRow(row)) {
    return "pending_legal";
  }
  if (row.included_in_corpus === true) {
    return "included_legal";
  }
  return "pending_legal";
}

export function groupCorpusSourcesByBucket(rows: Record<string, unknown>[]): Record<
  CorpusSourceBucket,
  Record<string, unknown>[]
> {
  const empty: Record<CorpusSourceBucket, Record<string, unknown>[]> = {
    included_legal: [],
    pending_legal: [],
    excluded_legal: [],
    developer_fixture: [],
  };
  for (const row of rows) {
    empty[corpusSourceBucket(row)].push(row);
  }
  return empty;
}

/** Maps bundle extraction pipeline fields to compact corpus-status chips for legal readers. */
export function corpusRowDisplayStatus(row: Record<string, unknown>): string {
  if (isDiscoveryCandidateRow(row)) {
    return "candidate";
  }
  const es = String(row.extraction_status ?? "").trim();
  if (es === "excluded") {
    return "excluded";
  }
  if (es === "reviewed") {
    return "ingested";
  }
  if (es === "extracted") {
    return "extracted";
  }
  if (es === "failed") {
    return "failed";
  }
  if (es === "not_started") {
    return "not started";
  }
  return es || "unknown";
}

export function corpusSourceTitleLine(row: Record<string, unknown>): string {
  const title = typeof row.title === "string" ? row.title.trim() : "";
  if (title) {
    return title;
  }
  const citation = typeof row.citation === "string" ? row.citation.trim() : "";
  if (citation) {
    return citation;
  }
  return String(row.source_id ?? "—");
}

export function corpusSecondaryLocatorLine(row: Record<string, unknown>): string {
  const parts: string[] = [];
  const citation = typeof row.citation === "string" ? row.citation.trim() : "";
  const celex = typeof row.celex === "string" ? row.celex.trim() : "";
  const eli = typeof row.eli === "string" ? row.eli.trim() : "";
  const url = typeof row.url === "string" ? row.url.trim() : "";
  if (citation) {
    parts.push(citation);
  }
  if (celex) {
    parts.push(`CELEX ${celex}`);
  }
  if (eli) {
    parts.push(`ELI ${eli}`);
  }
  if (url) {
    parts.push(url);
  }
  return parts.join(" · ");
}

export function chipOrDash(value: unknown): string {
  if (typeof value === "string") {
    const t = value.trim();
    return t || "—";
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "—";
}

export type CorpusCoverageCounts = {
  includedLegalSources: number;
  pendingLegalCandidates: number;
  excludedLegalCandidates: number;
  developerFixtures: number;
  guidanceReadyPropositions: number;
  propositionsTotal: number;
};

export function corpusCoverageCountsFromPayload(args: {
  summary: Record<string, unknown> | null | undefined;
  sourceRows: Record<string, unknown>[];
  propositionRows: Record<string, unknown>[];
}): CorpusCoverageCounts {
  const { summary, sourceRows, propositionRows } = args;
  const grouped = groupCorpusSourcesByBucket(sourceRows);

  const fromSummary = (key: string): number | undefined => {
    const v = summary?.[key];
    return typeof v === "number" && Number.isFinite(v) ? v : undefined;
  };

  const guidanceReady =
    propositionRows.filter((r) => r.guidance_ready === true).length;

  return {
    includedLegalSources:
      fromSummary("included_legal_sources") ?? grouped.included_legal.length,
    pendingLegalCandidates:
      fromSummary("pending_legal_candidates") ?? grouped.pending_legal.length,
    excludedLegalCandidates:
      fromSummary("excluded_legal_candidates") ?? grouped.excluded_legal.length,
    developerFixtures:
      fromSummary("developer_validation_fixtures") ?? grouped.developer_fixture.length,
    guidanceReadyPropositions:
      fromSummary("guidance_ready_propositions") ?? guidanceReady,
    propositionsTotal:
      fromSummary("propositions_total") ?? propositionRows.length,
  };
}

export function corpusReadinessHighlightIndex(args: {
  pendingLegalCandidates: number;
  includedLegalSources: number;
  propositionsTotal: number;
  propositionsUnreviewed: number;
  guidanceReadyPropositions: number;
}): number {
  const {
    pendingLegalCandidates,
    includedLegalSources,
    propositionsTotal,
    propositionsUnreviewed,
    guidanceReadyPropositions,
  } = args;

  if (guidanceReadyPropositions > 0) {
    return 5;
  }
  if (propositionsTotal > 0 && propositionsUnreviewed > 0) {
    return 4;
  }
  if (propositionsTotal > 0) {
    return 4;
  }
  if (includedLegalSources > 0) {
    return 3;
  }
  if (pendingLegalCandidates > 0) {
    return 1;
  }
  return 0;
}

/** Subset of equine law discovery `family` values emitted on source coverage rows (see equine_corpus_workflow). */
export type EquineLawDiscoveryFamily =
  | "ahl_core"
  | "equine_passport_identification"
  | "eu_exit_amendments"
  | "movement_entry_certification"
  | "official_controls"
  | "uk_context"
  | "";

const EQUINE_PORTFOLIO_LABEL: Record<string, string> = {
  pending_discovery_candidate: "Pending candidate — not auto-analysed",
  included_legal_source: "Included legal source (ingested)",
  excluded_or_out_of_scope: "Excluded / out of corpus scope",
  retained_historical_baseline: "Retained / historical baseline (distinct from current AHL model-doc layer)",
  current_operative_eu_candidate: "Current operative EU layer — register before treating as analysed source",
  "related_fragment:corrigendum_only": "Corrigendum (shown separately from parent instrument)",
  "related_fragment:annex_fragment": "Annex / appendix fragment (explicit ingest — not folded into parent body text)",
  guidance_context_only: "Guidance / explanatory row only (operative effect not claimed)",
};

/** Readable label for workflow `equine_portfolio_status` on coverage rows. */
export function equinePortfolioStatusLabel(status: unknown): string {
  const s = typeof status === "string" ? status.trim() : "";
  if (!s) return "—";
  return EQUINE_PORTFOLIO_LABEL[s] ?? s.replace(/_/g, " ");
}

export function equineLawGroupFromRow(row: Record<string, unknown>): EquineLawDiscoveryFamily {
  const g = typeof row.equine_law_group === "string" ? row.equine_law_group.trim() : "";
  if (
    g === "ahl_core" ||
    g === "equine_passport_identification" ||
    g === "eu_exit_amendments" ||
    g === "movement_entry_certification" ||
    g === "official_controls" ||
    g === "uk_context"
  ) {
    return g;
  }
  return "";
}

export function corpusRowsByEquineLawFamily(
  rows: Record<string, unknown>[],
  family: Exclude<EquineLawDiscoveryFamily, "">,
): Record<string, unknown>[] {
  return rows.filter((r) => equineLawGroupFromRow(r) === family);
}

/** Source universe cluster summary from API `source_universe` payload (see equine_corpus_workflow readiness). */
export type SourceUniverseClusterEntry = { count: number; label: string };

export function sourceUniverseClusterEntries(
  sourceUniverse: Record<string, unknown> | null | undefined,
): { key: string; count: number; label: string }[] {
  const raw = sourceUniverse?.cluster_counts;
  if (!raw || typeof raw !== "object") {
    return [];
  }
  const out: { key: string; count: number; label: string }[] = [];
  for (const [key, val] of Object.entries(raw as Record<string, unknown>)) {
    const rec = val as Record<string, unknown>;
    const count = typeof rec.count === "number" ? rec.count : 0;
    const label = typeof rec.label === "string" ? rec.label : key;
    out.push({ key, count, label });
  }
  return out.sort((a, b) => b.count - a.count);
}

/** Delegated Regulation 2019/2035 + Implementing Regulation 2021/963 as surfaced in discovery (coverage rows). */
export function currentEuEquineIdentificationDownstreamCandidates(
  rows: Record<string, unknown>[],
): Record<string, unknown>[] {
  const want = new Set(["sfc-2019-2035-delegated", "sfc-2021-963-implementing"]);
  return rows.filter((r) => typeof r.source_id === "string" && want.has(r.source_id));
}

