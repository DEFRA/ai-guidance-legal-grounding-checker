"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  DEFAULT_EXPLORER_CLASSIFICATION_FILTERS,
  LEGAL_EFFECT_FILTER_OPTIONS,
  PROPOSITION_TIER_FILTER_OPTIONS,
  classificationFiltersActive,
  isScopeRuleProposition,
  matchesExplorerClassificationFilters,
  partitionGroupsByScopeSecondary,
  propositionInformativeLabel,
  PropositionClassificationMeta,
  type ExplorerClassificationFilters,
} from "@/components/proposition-classification-ui";
import {
  FragmentSnippetView,
  SOURCE_JURISDICTION_CHIP_TOOLTIP,
  articleClusterKeyFromRow,
  asRecord,
  baseInstrumentTitleFromSource,
  buildArticleSectionsGrouped,
  buildScopeSectionsGrouped,
  buildSectionsFromPropositionSummaries,
  citationForSourceRecord,
  clientRepairableExtractionHintFromExplorerData,
  compactPropositionSourceSummaryLines,
  compareExplorerSectionClusterKeys,
  diffTokens,
  explorerSectionClusterKeyFromRow,
  formatExplorerSectionHeading,
  formatRepairBannerRetryTokenEstimate,
  REPAIR_BANNER_CREDITS_QUOTA_HELPER_TEXT,
  repairBannerFailureReasonsSentence,
  repairBannerNeedsCreditsQuotaHelper,
  instrumentFamilyFilterLabel,
  jurisdictionForSource,
  groupKeyForPropositionRow,
  mergeSemanticallyDuplicatePropositionGroups,
  partitionPropositionGroupsByArticleCluster,
  propositionDisplayLabel,
  shortInstrumentLabel,
  sourceDocumentFilterLabel,
  sourceDocumentFilterOptionTitle,
  sourceInstrumentFamilyKeyForRow,
  sourceInstrumentFamilyKeyFromSourceRecord,
  jurisdictionBadgeLabel,
  PropositionJurisdictionChip,
  normalizePropositionText,
  hiddenParentListSummaryExplorerNote,
  propositionGroupMetaChipText,
  propositionMatchesPrimaryVisibleScopeFilter,
  propositionSubtitleParts,
  relatedCrossReferenceDisplayLine,
  scopeFilterDisplayLabel,
  shouldSuppressCoarseParentPropositionInDefaultView,
  shouldShowPropositionGroupMergeLocatorDebug,
  stripPropositionSubgroupPartitionSuffix,
  suppressedParentListSummaryCountByArticleCluster,
  type PropositionGroupSummary,
  type UnknownRecord,
  humanReviewNotesForDisplay,
  verbatimEvidenceUiFromProposition,
  wordingFingerprintForPropositionGroupCompare,
} from "@/components/proposition-explorer-helpers";
import {
  PipelineReviewAction,
  PropositionReviewPanel,
  REVIEW_ARTIFACT_PROPOSITION,
} from "@/components/proposition-review-panel";
import {
  CompletenessChipBadge,
  COMPLETENESS_TOOLTIP,
  partitionScopeLinksSorted,
  PropositionEvidenceDetails,
  PropositionScopeLinksSection,
  StructuredPropositionSections,
  type PropositionDisplayMode,
} from "@/components/structured-proposition-ui";
import {
  deriveStructuredProposition,
  type ProvisionType,
} from "@/components/structured-proposition";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PropositionExplorerServerList } from "@/components/proposition-explorer-server-list";
import {
  buildPropositionsPathForJview,
  parseJurisdictionViewMode,
  type JurisdictionViewMode,
} from "@/components/proposition-explorer-jview";

export type { JurisdictionViewMode } from "@/components/proposition-explorer-jview";

const DISPLAY_MODE_STORAGE_KEY = "law-proposition-extractor.propositionDisplayMode";
const EXPLORER_NAV_MODE_KEY = "law-proposition-extractor.explorerNavMode";
const CLASSIFICATION_FILTERS_STORAGE_KEY = "law-proposition-extractor.explorerClassificationFilters";

function parseStoredClassificationFilters(raw: string | null): ExplorerClassificationFilters {
  if (!raw) {
    return { ...DEFAULT_EXPLORER_CLASSIFICATION_FILTERS };
  }
  try {
    const parsed = JSON.parse(raw) as Partial<ExplorerClassificationFilters>;
    return { ...DEFAULT_EXPLORER_CLASSIFICATION_FILTERS, ...parsed };
  } catch {
    return { ...DEFAULT_EXPLORER_CLASSIFICATION_FILTERS };
  }
}

export type ExplorerNavMode = "source_document" | "by_scope" | "compare_versions";

function parseStoredNavMode(v: string | null): ExplorerNavMode | null {
  return v === "source_document" || v === "by_scope" || v === "compare_versions" ? v : null;
}

function parseStoredDisplayMode(v: string | null): PropositionDisplayMode | null {
  return v === "structured" || v === "raw" ? v : null;
}

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_LAW_PROPOSITION_EXTRACTOR_API_BASE_URL ?? "http://127.0.0.1:8010"
).replace(/\/+$/, "");

/** When set, overrides server-side export root resolution for repair POST (local dev only). */
const OPS_EXPORT_DIR = (process.env.NEXT_PUBLIC_LAW_PROPOSITION_EXTRACTOR_OPS_EXPORT_DIR ?? "").trim();

const META_CHIP_CLASS =
  "rounded border border-border/70 bg-muted/80 px-2 py-0.5 font-mono text-[11px] leading-5 text-foreground/85";

/** Explicit hierarchy labels (Article section → Proposition group → Source row → Review layers). */
const HIER_SECTION_LABEL =
  "text-[10px] font-semibold uppercase tracking-wide text-muted-foreground";

const ARTICLE_SECTION_DETAILS_CLASS =
  "rounded-lg border border-border/75 bg-muted/[0.15] open:bg-muted/[0.22]";
const ARTICLE_SECTION_SUMMARY_CLASS =
  "cursor-pointer list-none px-3 py-2.5 text-sm outline-none marker:content-none [&::-webkit-details-marker]:hidden";
const PROPOSITION_DETAILS_CLASS =
  "rounded-lg border border-border/90 bg-card text-card-foreground shadow-sm";
const PROPOSITION_SUMMARY_CLASS =
  "cursor-pointer list-none px-3 py-2.5 text-sm outline-none marker:content-none [&::-webkit-details-marker]:hidden";

const INITIAL_ARTICLE_SECTIONS_OPEN = 3;

/** Preset scope filter tokens (exact match against slug / id / label / synonym on primary scope links). */
const SCOPE_FILTER_PRESETS: ReadonlyArray<{ token: string; label: string }> = [
  { token: "equine", label: "Equine" },
  { token: "bovine", label: "Bovine" },
  { token: "porcine", label: "Porcine" },
  { token: "germinal_products", label: "Germinal products" },
];

/** Same command as checklist `docs/dev/v1-5-readiness-checklist.md`; run against the export dir the API uses. */
const LINT_EXPORT_CLI =
  "uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline lint-export --export-dir dist/static-report";

function extractionNeedsReviewFromArtifacts(
  oa: UnknownRecord,
  traceRow: UnknownRecord | undefined,
): boolean {
  const rs = String(oa.review_status ?? "").toLowerCase();
  if (rs === "needs_review") return true;
  const ev = traceRow ? (asRecord(traceRow.effective_value) ?? {}) : {};
  if (String(ev.confidence ?? "").toLowerCase() === "low") return true;
  const sig = asRecord(ev.signals);
  if (sig?.fallback_used === true) return true;
  return false;
}

function aggregatePrimaryScopeSlugsForRows(
  rows: UnknownRecord[],
  scopeLinkRowsByPropId: Map<string, UnknownRecord[]>,
  scopeById: Map<string, UnknownRecord>
): { primarySlugs: string[]; secondarySlugCount: number } {
  const all: UnknownRecord[] = [];
  for (const row of rows) {
    const oa = asRecord(row.original_artifact) ?? {};
    const pid = String(oa.id ?? "").trim();
    for (const ln of pid ? (scopeLinkRowsByPropId.get(pid) ?? []) : []) {
      all.push(asRecord(ln) ?? {});
    }
  }
  const { primary: primaryScopeLinks, secondary: secondaryScopeLinks } =
    partitionScopeLinksSorted(all);
  const primarySlugs: string[] = [];
  const seenPrimarySlug = new Set<string>();
  for (const ln of primaryScopeLinks) {
    const sco = String((ln as { scope_id?: string }).scope_id ?? "");
    const sc = scopeById.get(sco);
    const slug = String(sc?.slug ?? sco);
    if (!seenPrimarySlug.has(slug)) {
      seenPrimarySlug.add(slug);
      primarySlugs.push(slug);
    }
  }
  const secondaryScopeSlugKeys = new Set<string>();
  for (const ln of secondaryScopeLinks) {
    const sco = String((ln as { scope_id?: string }).scope_id ?? "");
    const sc = scopeById.get(sco);
    secondaryScopeSlugKeys.add(String(sc?.slug ?? sco));
  }
  return { primarySlugs, secondarySlugCount: secondaryScopeSlugKeys.size };
}

function provisionTypeShortLabel(pt: ProvisionType): string {
  switch (pt) {
    case "transitional":
      return "Transitional";
    case "definition":
      return "Definition";
    case "exception":
      return "Exception";
    case "cross_reference":
      return "Cross-ref";
    case "core":
    default:
      return "Core";
  }
}

function reviewRowNeedsAttention(reviewLabel: string): boolean {
  return reviewLabel.trim().toLowerCase() !== "approved";
}

type RunListRow = {
  run_id: string;
  created_at?: string;
  workflow_mode?: string;
  proposition_count?: number | null;
  divergence_assessment_count?: number | null;
  artifact_count?: number | null;
  stage_trace_count?: number | null;
};

function PropositionExplorerInner(): JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [runs, setRuns] = useState<RunListRow[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [effectivePropositions, setEffectivePropositions] = useState<UnknownRecord[]>([]);
  const [links, setLinks] = useState<UnknownRecord[]>([]);
  const [scopes, setScopes] = useState<UnknownRecord[]>([]);
  const [sources, setSources] = useState<UnknownRecord[]>([]);
  const [effectiveTraces, setEffectiveTraces] = useState<UnknownRecord[]>([]);
  const [completenessRows, setCompletenessRows] = useState<UnknownRecord[]>([]);
  const [runQualitySummary, setRunQualitySummary] = useState<UnknownRecord | null>(null);
  const [runQualityRequestFailed, setRunQualityRequestFailed] = useState(false);
  const [runsLoading, setRunsLoading] = useState(true);
  const [runDataLoading, setRunDataLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [repairExtractionMessage, setRepairExtractionMessage] = useState<string | null>(null);
  const [repairExtractionBusy, setRepairExtractionBusy] = useState(false);

  const [filterScopeSlug, setFilterScopeSlug] = useState<string>("");
  const [filterConfidence, setFilterConfidence] = useState<string>("");
  const [filterReview, setFilterReview] = useState<string>("");
  const [filterSourceId, setFilterSourceId] = useState<string>("");
  const [filterInstrumentFamily, setFilterInstrumentFamily] = useState<string>("");

  const [classificationFilters, setClassificationFilters] = useState<ExplorerClassificationFilters>(
    () => {
      if (typeof window === "undefined") {
        return { ...DEFAULT_EXPLORER_CLASSIFICATION_FILTERS };
      }
      return parseStoredClassificationFilters(
        window.sessionStorage.getItem(CLASSIFICATION_FILTERS_STORAGE_KEY)
      );
    }
  );

  const [jurisdictionView, setJurisdictionView] = useState<JurisdictionViewMode>("all");
  const [divergenceAssessments, setDivergenceAssessments] = useState<UnknownRecord[]>([]);
  const [divergenceAssessmentsLoading, setDivergenceAssessmentsLoading] = useState(false);

  const [explorerNavMode, setExplorerNavModeState] = useState<ExplorerNavMode>(() => {
    if (typeof window === "undefined") {
      return "source_document";
    }
    return parseStoredNavMode(window.sessionStorage.getItem(EXPLORER_NAV_MODE_KEY)) ?? "source_document";
  });

  const setExplorerNavMode = useCallback((value: ExplorerNavMode): void => {
    setExplorerNavModeState(value);
    try {
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(EXPLORER_NAV_MODE_KEY, value);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const [reviewerNote, setReviewerNote] = useState<string>(() => {
    if (typeof window === "undefined") {
      return "";
    }
    return window.sessionStorage.getItem("law-proposition-extractor.reviewer") ?? "";
  });

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.sessionStorage.setItem("law-proposition-extractor.reviewer", reviewerNote);
  }, [reviewerNote]);

  useEffect(() => {
    setFilterScopeSlug(searchParams.get("scope")?.trim() ?? "");
  }, [searchParams]);

  useEffect(() => {
    try {
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(
          CLASSIFICATION_FILTERS_STORAGE_KEY,
          JSON.stringify(classificationFilters)
        );
      }
    } catch {
      /* ignore */
    }
  }, [classificationFilters]);

  useEffect(() => {
    const j = parseJurisdictionViewMode(searchParams.get("jview"));
    if (j) {
      setJurisdictionView(j);
    }
  }, [searchParams]);

  const applyScopePreset = useCallback(
    (token: string) => {
      const t = token.trim();
      setFilterScopeSlug(t);
      if (t) {
        router.replace(`/propositions?scope=${encodeURIComponent(t)}`, { scroll: false });
      } else {
        router.replace("/propositions", { scroll: false });
      }
    },
    [router]
  );

  const applyJurisdictionView = useCallback(
    (mode: JurisdictionViewMode) => {
      setJurisdictionView(mode);
      if (mode === "grouped") {
        setShowDuplicatesFlat(false);
      }
      router.replace(buildPropositionsPathForJview(filterScopeSlug, mode), { scroll: false });
    },
    [router, filterScopeSlug]
  );

  const [actionError, setActionError] = useState<string | null>(null);
  /** `${propositionId}|${artifact_type}` while a review POST is in flight for that row/target. */
  const [actionBusyKey, setActionBusyKey] = useState<string | null>(null);
  const [reviewRecordedFlash, setReviewRecordedFlash] = useState<{
    propositionId: string;
    at: number;
  } | null>(null);
  const [pipelineReviewDecisions, setPipelineReviewDecisions] = useState<UnknownRecord[]>([]);

  const GROUP_PAGE_SIZE = 50;
  const [groupSummaries, setGroupSummaries] = useState<PropositionGroupSummary[]>([]);
  const [groupsTotalGroups, setGroupsTotalGroups] = useState(0);
  const [groupsTotalRows, setGroupsTotalRows] = useState(0);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [groupDetailById, setGroupDetailById] = useState<Record<string, UnknownRecord>>({});
  const [groupDetailLoading, setGroupDetailLoading] = useState<Record<string, boolean>>({});
  const [propositionsSearchInput, setPropositionsSearchInput] = useState("");
  const [debouncedPropositionsSearch, setDebouncedPropositionsSearch] = useState("");

  const groupDetailCacheRef = useRef<Record<string, UnknownRecord>>({});
  groupDetailCacheRef.current = groupDetailById;

  const [traceModalPid, setTraceModalPid] = useState<string | null>(null);
  const [fragmentModalOpen, setFragmentModalOpen] = useState(false);
  const [fragmentModalCaption, setFragmentModalCaption] = useState<{
    source_record_id: string;
    fragment_id: string;
  }>({
    source_record_id: "",
    fragment_id: "",
  });
  const [fragmentText, setFragmentText] = useState<string>("");
  const [fragmentBusy, setFragmentBusy] = useState(false);
  const [fragmentHighlightLocator, setFragmentHighlightLocator] = useState<string>("");
  const [fragmentModalContextInjections, setFragmentModalContextInjections] =
    useState<UnknownRecord | null>(null);

  /** When true: one card per proposition (legacy); when false: group by structured locator / proposition_key */
  const [showDuplicatesFlat, setShowDuplicatesFlat] = useState(false);

  const [propositionDisplayMode, setPropositionDisplayModeState] =
    useState<PropositionDisplayMode>("structured");

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      const parsed = parseStoredDisplayMode(
        window.sessionStorage.getItem(DISPLAY_MODE_STORAGE_KEY)
      );
      if (parsed) {
        setPropositionDisplayModeState(parsed);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const setPropositionDisplayMode = useCallback((value: PropositionDisplayMode): void => {
    setPropositionDisplayModeState(value);
    try {
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(DISPLAY_MODE_STORAGE_KEY, value);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const scopeById = useMemo(() => {
    const m = new Map<string, UnknownRecord>();
    for (const s of scopes) {
      const id = String((s as { id?: string }).id ?? "").trim();
      if (id) {
        m.set(id, asRecord(s) ?? {});
      }
    }
    return m;
  }, [scopes]);

  useEffect(() => {
    const t = window.setTimeout(() => {
      setDebouncedPropositionsSearch(propositionsSearchInput.trim());
    }, 320);
    return () => window.clearTimeout(t);
  }, [propositionsSearchInput]);

  const traceByPropId = useMemo(() => {
    const m = new Map<string, UnknownRecord>();
    const list = [...effectiveTraces].sort((a, b) => {
      const ida = String((a as { artifact_id?: string }).artifact_id ?? "");
      const idb = String((b as { artifact_id?: string }).artifact_id ?? "");
      return ida.localeCompare(idb);
    });
    for (const t of list) {
      const oa = asRecord((t as { original_artifact?: unknown }).original_artifact);
      const pid = String(oa?.proposition_id ?? "").trim();
      if (pid && !m.has(pid)) {
        m.set(pid, t);
      }
    }
    return m;
  }, [effectiveTraces]);

  useEffect(() => {
    if (!traceModalPid || !selectedRunId) {
      return;
    }
    const pid = traceModalPid;
    if (traceByPropId.has(pid)) {
      return;
    }
    const controller = new AbortController();
    void (async () => {
      try {
        const r = await fetch(
          `${API_BASE_URL}/ops/effective/proposition-extraction-traces?run_id=${encodeURIComponent(
            selectedRunId
          )}&proposition_id=${encodeURIComponent(pid)}`,
          { signal: controller.signal, headers: { Accept: "application/json" } }
        );
        if (!r.ok) {
          return;
        }
        const j = asRecord(await r.json()) ?? {};
        const raw = j.effective_proposition_extraction_traces;
        const row = Array.isArray(raw) && raw[0] ? (asRecord(raw[0]) ?? null) : null;
        if (!row) {
          return;
        }
        setEffectiveTraces((prev) => {
          const oa = asRecord(row.original_artifact);
          const id = String(oa?.proposition_id ?? "").trim();
          if (
            !id ||
            prev.some(
              (x) => String(asRecord(x.original_artifact)?.proposition_id ?? "").trim() === id
            )
          ) {
            return prev;
          }
          return [...prev, row];
        });
      } catch {
        /* ignore */
      }
    })();
    return () => {
      controller.abort();
    };
  }, [traceModalPid, selectedRunId, traceByPropId]);

  const completenessByPropId = useMemo(() => {
    const m = new Map<string, UnknownRecord>();
    for (const row of completenessRows) {
      const r = asRecord(row) ?? {};
      const pid = String(r.proposition_id ?? "").trim();
      if (pid) {
        m.set(pid, r);
      }
    }
    return m;
  }, [completenessRows]);

  const scopeLinkRowsByPropId = useMemo(() => {
    const m = new Map<string, UnknownRecord[]>();
    for (const ln of links) {
      const row = ln as UnknownRecord;
      const pid = String(row.proposition_id ?? "").trim();
      if (!pid) {
        continue;
      }
      const cur = m.get(pid) ?? [];
      cur.push(row);
      m.set(pid, cur);
    }
    return m;
  }, [links]);

  const sourceTitleById = useMemo(() => {
    const m = new Map<string, string>();
    for (const s of sources) {
      const r = asRecord(s);
      if (!r) {
        continue;
      }
      const id = String(r.id ?? "").trim();
      const title =
        typeof r.title === "string" && r.title.trim().length > 0
          ? r.title.trim()
          : typeof r.summary === "string"
            ? r.summary.trim()
            : id;
      if (id) {
        m.set(id, title);
      }
    }
    return m;
  }, [sources]);

  const loadFullRunArtifacts = useCallback(async (runId: string, signal: AbortSignal) => {
    const qualUrl = `${API_BASE_URL}/ops/run-quality-summary?run_id=${encodeURIComponent(runId)}`;
    const compUrl = `${API_BASE_URL}/ops/proposition-completeness-assessments?run_id=${encodeURIComponent(runId)}`;
    const prdUrl = `${API_BASE_URL}/ops/pipeline-review-decisions?run_id=${encodeURIComponent(runId)}`;
    const [propsRes, linkRes, scopeRes, srcRes, traceRes, qualRes, compRes, prdRes] =
      await Promise.all([
        fetch(`${API_BASE_URL}/ops/effective/propositions?run_id=${encodeURIComponent(runId)}`, {
          headers: { Accept: "application/json" },
          signal,
        }),
        fetch(`${API_BASE_URL}/ops/proposition-scope-links?run_id=${encodeURIComponent(runId)}`, {
          headers: { Accept: "application/json" },
          signal,
        }),
        fetch(`${API_BASE_URL}/ops/legal-scopes?run_id=${encodeURIComponent(runId)}`, {
          headers: { Accept: "application/json" },
          signal,
        }),
        fetch(`${API_BASE_URL}/ops/sources?run_id=${encodeURIComponent(runId)}`, {
          headers: { Accept: "application/json" },
          signal,
        }),
        fetch(
          `${API_BASE_URL}/ops/effective/proposition-extraction-traces?run_id=${encodeURIComponent(runId)}`,
          {
            headers: { Accept: "application/json" },
            signal,
          }
        ),
        fetch(qualUrl, {
          headers: { Accept: "application/json" },
          signal,
        }),
        fetch(compUrl, {
          headers: { Accept: "application/json" },
          signal,
        }),
        fetch(prdUrl, {
          headers: { Accept: "application/json" },
          signal,
        }),
      ]);

    const failed = [propsRes, linkRes, scopeRes, srcRes, traceRes].filter((r) => !r.ok);
    if (failed.length > 0) {
      throw new Error(`Request failed (${failed[0]?.status ?? "?"})`);
    }

    let qualityParsed: UnknownRecord | null = null;
    setRunQualityRequestFailed(!qualRes.ok);
    if (qualRes.ok) {
      try {
        const qualJson: unknown = await qualRes.json();
        const inner = asRecord(qualJson)?.run_quality_summary;
        qualityParsed = inner && typeof inner === "object" ? asRecord(inner) : null;
      } catch {
        qualityParsed = null;
      }
    }

    let completenessParsed: UnknownRecord[] = [];
    if (compRes.ok) {
      try {
        const compJson: unknown = await compRes.json();
        const raw = asRecord(compJson)?.proposition_completeness_assessments;
        completenessParsed = Array.isArray(raw) ? raw.map((x) => asRecord(x) ?? {}) : [];
      } catch {
        completenessParsed = [];
      }
    }

    const propsJson: unknown = await propsRes.json();
    const linkJson: unknown = await linkRes.json();
    const scopeJson: unknown = await scopeRes.json();
    const srcJson: unknown = await srcRes.json();
    const traceJson: unknown = await traceRes.json();

    const propRowsRaw = asRecord(propsJson)?.effective_propositions;
    const propRows = Array.isArray(propRowsRaw) ? propRowsRaw.map((x) => asRecord(x) ?? {}) : [];

    const linkRowsRaw = asRecord(linkJson)?.proposition_scope_links;
    const linkRows = Array.isArray(linkRowsRaw) ? linkRowsRaw.map((x) => asRecord(x) ?? {}) : [];

    const scopeRowsRaw = asRecord(scopeJson)?.legal_scopes;
    const scopeRows = Array.isArray(scopeRowsRaw) ? scopeRowsRaw.map((x) => asRecord(x) ?? {}) : [];

    const srcRowsRaw = asRecord(srcJson)?.source_records;
    const srcRows = Array.isArray(srcRowsRaw) ? srcRowsRaw.map((x) => asRecord(x) ?? {}) : [];

    const traceRowsRaw = asRecord(traceJson)?.effective_proposition_extraction_traces;
    const traceRows = Array.isArray(traceRowsRaw) ? traceRowsRaw.map((x) => asRecord(x) ?? {}) : [];

    let prdRows: UnknownRecord[] = [];
    if (prdRes.ok) {
      try {
        const prdJson: unknown = await prdRes.json();
        const raw = asRecord(prdJson)?.pipeline_review_decisions;
        prdRows = Array.isArray(raw) ? raw.map((x) => asRecord(x) ?? {}) : [];
      } catch {
        prdRows = [];
      }
    }

    propRows.sort((a: UnknownRecord, b: UnknownRecord) => {
      const oa = asRecord(a.original_artifact) ?? {};
      const ob = asRecord(b.original_artifact) ?? {};
      const sa = String(oa.source_record_id ?? "").trim();
      const sb = String(ob.source_record_id ?? "").trim();
      if (sa !== sb) {
        return sa.localeCompare(sb);
      }
      const ia = oa.order_index;
      const ib = ob.order_index;
      if (typeof ia === "number" && typeof ib === "number" && ia !== ib) {
        return ia - ib;
      }
      if (typeof ia === "number" && typeof ib !== "number") {
        return -1;
      }
      if (typeof ia !== "number" && typeof ib === "number") {
        return 1;
      }
      return String(oa.proposition_key ?? oa.id ?? "").localeCompare(
        String(ob.proposition_key ?? ob.id ?? "")
      );
    });

    setEffectivePropositions(propRows);
    setLinks(linkRows);
    setScopes(scopeRows);
    setSources(srcRows);
    setEffectiveTraces(traceRows);
    setCompletenessRows(completenessParsed);
    setRunQualitySummary(qualityParsed);
    setPipelineReviewDecisions(prdRows);
  }, []);

  const fetchPropositionGroupList = useCallback(
    async (signal: AbortSignal, options: { offset: number; append: boolean }) => {
      if (!selectedRunId) {
        return;
      }
      const params = new URLSearchParams();
      params.set("run_id", selectedRunId);
      params.set("limit", String(GROUP_PAGE_SIZE));
      params.set("offset", String(options.offset));
      const scopeTok = filterScopeSlug.trim();
      if (scopeTok) {
        params.set("scope", scopeTok);
      }
      if (filterSourceId.trim()) {
        params.set("source_id", filterSourceId.trim());
      }
      if (filterReview.trim()) {
        params.set("review_status", filterReview.trim());
      }
      if (filterConfidence.trim()) {
        params.set("confidence", filterConfidence.trim());
      }
      if (filterInstrumentFamily.trim()) {
        params.set("instrument_family", filterInstrumentFamily.trim());
      }
      if (debouncedPropositionsSearch.trim()) {
        params.set("search", debouncedPropositionsSearch.trim());
      }
      if (propositionDisplayMode === "raw") {
        params.set("include_coarse_parent_rows", "true");
      }
      const r = await fetch(`${API_BASE_URL}/ops/proposition-groups?${params.toString()}`, {
        signal,
        headers: { Accept: "application/json" },
      });
      if (!r.ok) {
        throw new Error(`proposition-groups failed (${r.status})`);
      }
      const payload = asRecord(await r.json()) ?? {};
      const groupsRaw = payload.groups;
      const groupsParsed: PropositionGroupSummary[] = Array.isArray(groupsRaw)
        ? groupsRaw.map((x) => asRecord(x) as PropositionGroupSummary)
        : [];
      if (options.append) {
        setGroupSummaries((prev) => [...prev, ...groupsParsed]);
      } else {
        setGroupSummaries(groupsParsed);
      }
      setGroupsTotalGroups(typeof payload.total_groups === "number" ? payload.total_groups : 0);
      setGroupsTotalRows(typeof payload.total_rows === "number" ? payload.total_rows : 0);
    },
    [
      selectedRunId,
      filterScopeSlug,
      filterSourceId,
      filterReview,
      filterConfidence,
      filterInstrumentFamily,
      debouncedPropositionsSearch,
      propositionDisplayMode,
    ]
  );

  const buildPropositionGroupDetailQuery = useCallback((): URLSearchParams => {
    const params = new URLSearchParams();
    if (selectedRunId) {
      params.set("run_id", selectedRunId);
    }
    const scopeTok = filterScopeSlug.trim();
    if (scopeTok) {
      params.set("scope", scopeTok);
    }
    if (filterSourceId.trim()) {
      params.set("source_id", filterSourceId.trim());
    }
    if (filterReview.trim()) {
      params.set("review_status", filterReview.trim());
    }
    if (filterConfidence.trim()) {
      params.set("confidence", filterConfidence.trim());
    }
    if (filterInstrumentFamily.trim()) {
      params.set("instrument_family", filterInstrumentFamily.trim());
    }
    if (debouncedPropositionsSearch.trim()) {
      params.set("search", debouncedPropositionsSearch.trim());
    }
    if (propositionDisplayMode === "raw") {
      params.set("include_coarse_parent_rows", "true");
    }
    return params;
  }, [
    selectedRunId,
    filterScopeSlug,
    filterSourceId,
    filterReview,
    filterConfidence,
    filterInstrumentFamily,
    debouncedPropositionsSearch,
    propositionDisplayMode,
  ]);

  const ensureGroupDetailLoaded = useCallback(
    async (groupId: string) => {
      if (!selectedRunId) {
        return;
      }
      if (groupDetailCacheRef.current[groupId]) {
        return;
      }
      setGroupDetailLoading((m) => ({ ...m, [groupId]: true }));
      setActionError(null);
      try {
        const q = buildPropositionGroupDetailQuery();
        const r = await fetch(
          `${API_BASE_URL}/ops/proposition-groups/${encodeURIComponent(groupId)}?${q.toString()}`,
          { headers: { Accept: "application/json" } }
        );
        if (!r.ok) {
          throw new Error(`group detail ${r.status}`);
        }
        const body = asRecord(await r.json()) ?? {};
        setGroupDetailById((m) => ({ ...m, [groupId]: body }));
      } catch (exc) {
        setActionError(exc instanceof Error ? exc.message : "Detail load failed");
      } finally {
        setGroupDetailLoading((m) => ({ ...m, [groupId]: false }));
      }
    },
    [selectedRunId, buildPropositionGroupDetailQuery]
  );

  const loadLightRunArtifacts = useCallback(async (runId: string, signal: AbortSignal) => {
    const qualUrl = `${API_BASE_URL}/ops/run-quality-summary?run_id=${encodeURIComponent(runId)}`;
    const prdUrl = `${API_BASE_URL}/ops/pipeline-review-decisions?run_id=${encodeURIComponent(runId)}`;
    const [linkRes, scopeRes, srcRes, qualRes, prdRes] = await Promise.all([
      fetch(`${API_BASE_URL}/ops/proposition-scope-links?run_id=${encodeURIComponent(runId)}`, {
        headers: { Accept: "application/json" },
        signal,
      }),
      fetch(`${API_BASE_URL}/ops/legal-scopes?run_id=${encodeURIComponent(runId)}`, {
        headers: { Accept: "application/json" },
        signal,
      }),
      fetch(`${API_BASE_URL}/ops/sources?run_id=${encodeURIComponent(runId)}`, {
        headers: { Accept: "application/json" },
        signal,
      }),
      fetch(qualUrl, {
        headers: { Accept: "application/json" },
        signal,
      }),
      fetch(prdUrl, {
        headers: { Accept: "application/json" },
        signal,
      }),
    ]);

    const failed = [linkRes, scopeRes, srcRes].filter((r) => !r.ok);
    if (failed.length > 0) {
      throw new Error(`Request failed (${failed[0]?.status ?? "?"})`);
    }

    let qualityParsed: UnknownRecord | null = null;
    setRunQualityRequestFailed(!qualRes.ok);
    if (qualRes.ok) {
      try {
        const qualJson: unknown = await qualRes.json();
        const inner = asRecord(qualJson)?.run_quality_summary;
        qualityParsed = inner && typeof inner === "object" ? asRecord(inner) : null;
      } catch {
        qualityParsed = null;
      }
    }

    const linkJson: unknown = await linkRes.json();
    const scopeJson: unknown = await scopeRes.json();
    const srcJson: unknown = await srcRes.json();

    const linkRowsRaw = asRecord(linkJson)?.proposition_scope_links;
    const linkRows = Array.isArray(linkRowsRaw) ? linkRowsRaw.map((x) => asRecord(x) ?? {}) : [];

    const scopeRowsRaw = asRecord(scopeJson)?.legal_scopes;
    const scopeRows = Array.isArray(scopeRowsRaw) ? scopeRowsRaw.map((x) => asRecord(x) ?? {}) : [];

    const srcRowsRaw = asRecord(srcJson)?.source_records;
    const srcRows = Array.isArray(srcRowsRaw) ? srcRowsRaw.map((x) => asRecord(x) ?? {}) : [];

    let prdRows: UnknownRecord[] = [];
    if (prdRes.ok) {
      try {
        const prdJson: unknown = await prdRes.json();
        const raw = asRecord(prdJson)?.pipeline_review_decisions;
        prdRows = Array.isArray(raw) ? raw.map((x) => asRecord(x) ?? {}) : [];
      } catch {
        prdRows = [];
      }
    }

    setEffectivePropositions([]);
    setLinks(linkRows);
    setScopes(scopeRows);
    setSources(srcRows);
    setEffectiveTraces([]);
    setCompletenessRows([]);
    setRunQualitySummary(qualityParsed);
    setPipelineReviewDecisions(prdRows);
  }, []);

  const fetchRunsCatalog = useCallback(
    async (signal: AbortSignal, options?: { silent?: boolean }) => {
      if (!options?.silent) {
        setRunsLoading(true);
      }
      setError(null);
      try {
        const r = await fetch(`${API_BASE_URL}/ops/runs`, {
          headers: { Accept: "application/json" },
          signal,
        });
        if (!r.ok) {
          throw new Error(`runs request failed (${r.status})`);
        }
        const j: unknown = await r.json();
        const rs = asRecord(j)?.runs;
        const rows: RunListRow[] = Array.isArray(rs)
          ? rs
              .map((x) => asRecord(x) ?? {})
              .map((x) => ({
                run_id: String(x.run_id ?? ""),
                created_at:
                  typeof x.created_at === "string" ? x.created_at : String(x.created_at ?? ""),
                workflow_mode: typeof x.workflow_mode === "string" ? x.workflow_mode : undefined,
                proposition_count:
                  typeof x.proposition_count === "number" ? x.proposition_count : null,
                divergence_assessment_count:
                  typeof x.divergence_assessment_count === "number"
                    ? x.divergence_assessment_count
                    : null,
                artifact_count: typeof x.artifact_count === "number" ? x.artifact_count : null,
                stage_trace_count:
                  typeof x.stage_trace_count === "number" ? x.stage_trace_count : null,
              }))
              .filter((x) => x.run_id)
          : [];
        setRuns(rows);
        setSelectedRunId((previous) => {
          if (previous && rows.some((item) => item.run_id === previous)) {
            return previous;
          }
          return rows[0]?.run_id ?? null;
        });
      } catch (exc) {
        if (signal.aborted) {
          return;
        }
        const msg = exc instanceof Error ? exc.message : "Unknown error";
        setError(msg);
      } finally {
        if (!signal.aborted && !options?.silent) {
          setRunsLoading(false);
        }
      }
    },
    []
  );

  useEffect(() => {
    const controller = new AbortController();
    void fetchRunsCatalog(controller.signal);
    return () => {
      controller.abort();
    };
  }, [fetchRunsCatalog]);

  useEffect(() => {
    const onFocus = (): void => {
      const controller = new AbortController();
      void fetchRunsCatalog(controller.signal, { silent: true });
    };

    window.addEventListener("focus", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
    };
  }, [fetchRunsCatalog]);

  useEffect(() => {
    if (!selectedRunId) {
      setEffectivePropositions([]);
      setLinks([]);
      setScopes([]);
      setSources([]);
      setEffectiveTraces([]);
      setCompletenessRows([]);
      setRunQualitySummary(null);
      setRunQualityRequestFailed(false);
      setPipelineReviewDecisions([]);
      setGroupSummaries([]);
      setGroupsTotalGroups(0);
      setGroupsTotalRows(0);
      setGroupDetailById({});
      setGroupDetailLoading({});
      return;
    }
    const controller = new AbortController();
    const load = async () => {
      setRunDataLoading(true);
      setError(null);
      try {
        if (showDuplicatesFlat) {
          await loadFullRunArtifacts(selectedRunId, controller.signal);
        } else {
          await loadLightRunArtifacts(selectedRunId, controller.signal);
        }
      } catch (exc) {
        if (controller.signal.aborted) {
          return;
        }
        setError(exc instanceof Error ? exc.message : "Load failed");
      } finally {
        if (!controller.signal.aborted) {
          setRunDataLoading(false);
        }
      }
    };

    void load();
    return () => {
      controller.abort();
    };
  }, [loadFullRunArtifacts, loadLightRunArtifacts, selectedRunId, showDuplicatesFlat]);

  useEffect(() => {
    if (!selectedRunId || jurisdictionView !== "divergences") {
      setDivergenceAssessments([]);
      setDivergenceAssessmentsLoading(false);
      return;
    }
    const meta = runs.find((r) => r.run_id === selectedRunId);
    const hasDataset =
      typeof meta?.divergence_assessment_count === "number" && meta.divergence_assessment_count > 0;
    if (!hasDataset) {
      setDivergenceAssessments([]);
      setDivergenceAssessmentsLoading(false);
      return;
    }
    const controller = new AbortController();
    setDivergenceAssessmentsLoading(true);
    void (async () => {
      try {
        const res = await fetch(
          `${API_BASE_URL}/ops/divergence-assessments?run_id=${encodeURIComponent(selectedRunId)}`,
          { signal: controller.signal, headers: { Accept: "application/json" } }
        );
        if (!res.ok) {
          setDivergenceAssessments([]);
          return;
        }
        const raw = (await res.json()) as UnknownRecord;
        const rows = raw.divergence_assessments;
        setDivergenceAssessments(
          Array.isArray(rows) ? rows.map((x) => asRecord(x) ?? {}) : []
        );
      } catch {
        /* ignore */
      } finally {
        if (!controller.signal.aborted) {
          setDivergenceAssessmentsLoading(false);
        }
      }
    })();
    return () => {
      controller.abort();
    };
  }, [selectedRunId, jurisdictionView, runs]);

  useEffect(() => {
    if (!selectedRunId || showDuplicatesFlat) {
      return;
    }
    const controller = new AbortController();
    void (async () => {
      setGroupsLoading(true);
      setGroupDetailById({});
      setGroupDetailLoading({});
      try {
        await fetchPropositionGroupList(controller.signal, { offset: 0, append: false });
      } catch (exc) {
        if (!controller.signal.aborted) {
          setError(exc instanceof Error ? exc.message : "Group list failed");
        }
      } finally {
        if (!controller.signal.aborted) {
          setGroupsLoading(false);
        }
      }
    })();
    return () => {
      controller.abort();
    };
  }, [selectedRunId, showDuplicatesFlat, fetchPropositionGroupList]);

  const rowsAfterCoreFilters = useMemo(() => {
    const scopeTok = filterScopeSlug.trim();
    return effectivePropositions.filter((row) => {
      const oa = asRecord(row.original_artifact) ?? {};
      const pid = String(oa.id ?? "").trim();

      const tr = pid ? traceByPropId.get(pid) : undefined;
      const ev = asRecord(tr?.effective_value) ?? {};
      const conf = String(ev.confidence ?? "").trim();

      let review = String(row.effective_status ?? "")
        .trim()
        .toLowerCase();
      if (review === "generated") {
        review = "generated";
      }

      if (
        scopeTok &&
        !propositionMatchesPrimaryVisibleScopeFilter(pid, scopeTok, links, scopeById)
      ) {
        return false;
      }
      if (filterConfidence.trim() && conf !== filterConfidence.trim()) {
        return false;
      }
      if (filterReview.trim() && review !== filterReview.trim().toLowerCase()) {
        return false;
      }
      return true;
    });
  }, [
    effectivePropositions,
    filterConfidence,
    filterReview,
    filterScopeSlug,
    links,
    scopeById,
    traceByPropId,
  ]);

  const rowsAfterClassificationFilters = useMemo(() => {
    return rowsAfterCoreFilters.filter((row) => {
      const oa = asRecord(row.original_artifact) ?? {};
      return matchesExplorerClassificationFilters(oa, classificationFilters);
    });
  }, [rowsAfterCoreFilters, classificationFilters]);

  const propositionArtifactById = useMemo(() => {
    const m = new Map<string, UnknownRecord>();
    for (const row of effectivePropositions) {
      const oa = asRecord(row.original_artifact) ?? {};
      const id = String(oa.id ?? "").trim();
      if (id) {
        m.set(id, oa);
      }
    }
    return m;
  }, [effectivePropositions]);

  const rowsAfterJurisdictionView = useMemo(() => {
    if (jurisdictionView === "all" || jurisdictionView === "grouped") {
      return rowsAfterClassificationFilters;
    }
    if (jurisdictionView === "eu") {
      return rowsAfterClassificationFilters.filter((row) => {
        const oa = asRecord(row.original_artifact) ?? {};
        const sid = String(oa.source_record_id ?? "").trim();
        return jurisdictionForSource(sources, sid).toUpperCase() === "EU";
      });
    }
    if (jurisdictionView === "uk") {
      return rowsAfterClassificationFilters.filter((row) => {
        const oa = asRecord(row.original_artifact) ?? {};
        const sid = String(oa.source_record_id ?? "").trim();
        return jurisdictionForSource(sources, sid).toUpperCase() === "UK";
      });
    }
    if (jurisdictionView === "divergences") {
      const meta = runs.find((r) => r.run_id === selectedRunId);
      const hasDataset =
        typeof meta?.divergence_assessment_count === "number" &&
        meta.divergence_assessment_count > 0;
      if (!hasDataset || divergenceAssessmentsLoading) {
        return [];
      }
      const ids = new Set<string>();
      for (const a of divergenceAssessments) {
        const o = asRecord(a) ?? {};
        const p = String(o.proposition_id ?? "").trim();
        const c = String(o.comparator_proposition_id ?? "").trim();
        if (p) {
          ids.add(p);
        }
        if (c) {
          ids.add(c);
        }
      }
      if (ids.size === 0) {
        return [];
      }
      return rowsAfterClassificationFilters.filter((row) => {
        const oa = asRecord(row.original_artifact) ?? {};
        return ids.has(String(oa.id ?? "").trim());
      });
    }
    return rowsAfterClassificationFilters;
  }, [
    divergenceAssessments,
    divergenceAssessmentsLoading,
    jurisdictionView,
    rowsAfterClassificationFilters,
    runs,
    selectedRunId,
    sources,
  ]);

  const rowsAfterInstrumentFamily = useMemo(() => {
    const fam = filterInstrumentFamily.trim();
    if (!fam) {
      return rowsAfterJurisdictionView;
    }
    return rowsAfterJurisdictionView.filter(
      (row) => sourceInstrumentFamilyKeyForRow(row, sources) === fam
    );
  }, [rowsAfterJurisdictionView, filterInstrumentFamily, sources]);

  const rowsMatchingFilters = useMemo(() => {
    const sel = filterSourceId.trim();
    if (!sel) {
      return rowsAfterInstrumentFamily;
    }
    const touch = new Set<string>();
    for (const row of rowsAfterInstrumentFamily) {
      const oa = asRecord(row.original_artifact) ?? {};
      if (String(oa.source_record_id ?? "").trim() === sel) {
        touch.add(groupKeyForPropositionRow(row, sources));
      }
    }
    return rowsAfterInstrumentFamily.filter((row) =>
      touch.has(groupKeyForPropositionRow(row, sources))
    );
  }, [rowsAfterInstrumentFamily, filterSourceId, sources]);

  const parentListSummarySuppressionInactive =
    showDuplicatesFlat || propositionDisplayMode === "raw";

  const suppressedParentCountByArticleCluster = useMemo(
    () =>
      parentListSummarySuppressionInactive
        ? new Map<string, number>()
        : suppressedParentListSummaryCountByArticleCluster(rowsMatchingFilters, sources),
    [parentListSummarySuppressionInactive, rowsMatchingFilters, sources]
  );

  const filteredRows = useMemo(() => {
    if (parentListSummarySuppressionInactive) {
      return rowsMatchingFilters;
    }
    return rowsMatchingFilters.filter(
      (row) => !shouldSuppressCoarseParentPropositionInDefaultView(row, rowsMatchingFilters)
    );
  }, [parentListSummarySuppressionInactive, rowsMatchingFilters]);

  const filteredGroupSummaries = useMemo(() => {
    // Grouped view uses server pagination (loadLightRunArtifacts leaves effectivePropositions
    // empty). Scope/source/review/confidence/search are applied by GET /ops/proposition-groups.
    if (!showDuplicatesFlat && effectivePropositions.length === 0) {
      return groupSummaries;
    }
    const visibleIds = new Set(
      filteredRows.map((row) => String(asRecord(row.original_artifact)?.id ?? "").trim()).filter(Boolean)
    );
    return groupSummaries.filter((sum) => sum.row_ids.some((id) => visibleIds.has(id)));
  }, [groupSummaries, filteredRows, showDuplicatesFlat, effectivePropositions.length]);

  const classificationFiltersActiveFlag = useMemo(
    () => classificationFiltersActive(classificationFilters),
    [classificationFilters]
  );

  const filtersActive = useMemo(
    () =>
      Boolean(
        filterScopeSlug.trim() ||
          filterConfidence.trim() ||
          filterReview.trim() ||
          filterSourceId.trim() ||
          filterInstrumentFamily.trim() ||
          classificationFiltersActiveFlag
      ),
    [
      filterScopeSlug,
      filterConfidence,
      filterReview,
      filterSourceId,
      filterInstrumentFamily,
      classificationFiltersActiveFlag,
    ]
  );

  const scopeFilterTrimmed = filterScopeSlug.trim();
  const scopeFilterExplainerLabel = scopeFilterDisplayLabel(scopeFilterTrimmed);
  const showMultiSpeciesArticleNote = !scopeFilterTrimmed;

  const propositionGroups = useMemo(() => {
    function sortRows(rows: UnknownRecord[]): UnknownRecord[] {
      return [...rows].sort((a, b) => {
        const oa = asRecord(a.original_artifact) ?? {};
        const ob = asRecord(b.original_artifact) ?? {};
        const sa = String(oa.source_record_id ?? "").trim();
        const sb = String(ob.source_record_id ?? "").trim();
        const ja = jurisdictionForSource(sources, sa).toUpperCase();
        const jb = jurisdictionForSource(sources, sb).toUpperCase();
        const ra = ja === "EU" ? 0 : ja === "UK" ? 1 : 2;
        const rb = jb === "EU" ? 0 : jb === "UK" ? 1 : 2;
        if (ra !== rb) {
          return ra - rb;
        }
        return sa.localeCompare(sb);
      });
    }
    const order: string[] = [];
    const map = new Map<string, UnknownRecord[]>();
    for (const row of filteredRows) {
      const gk = groupKeyForPropositionRow(row, sources);
      if (!map.has(gk)) {
        order.push(gk);
        map.set(gk, []);
      }
      map.get(gk)?.push(row);
    }
    return order.map((key) => ({
      key,
      rows: sortRows(map.get(key) ?? []),
    }));
  }, [filteredRows, sources]);

  const propositionGroupsPartitionedByArticle = useMemo(
    () => partitionPropositionGroupsByArticleCluster(propositionGroups),
    [propositionGroups]
  );

  const propositionGroupsDeduped = useMemo(
    () =>
      mergeSemanticallyDuplicatePropositionGroups(
        propositionGroupsPartitionedByArticle,
        sources,
        scopeLinkRowsByPropId,
        scopeById
      ),
    [propositionGroupsPartitionedByArticle, sources, scopeLinkRowsByPropId, scopeById]
  );

  const semanticMergeCollapsedGroupCount = useMemo(() => {
    const b = propositionGroupsPartitionedByArticle.length;
    const a = propositionGroupsDeduped.length;
    return b > a ? b - a : 0;
  }, [propositionGroupsPartitionedByArticle.length, propositionGroupsDeduped.length]);

  const sortedPropositionGroups = useMemo(() => {
    return [...propositionGroupsDeduped].sort((a, b) => {
      const ka = explorerSectionClusterKeyFromRow(a.rows[0], sources);
      const kb = explorerSectionClusterKeyFromRow(b.rows[0], sources);
      if (ka !== kb) {
        return compareExplorerSectionClusterKeys(ka, kb);
      }
      return a.key.localeCompare(b.key);
    });
  }, [propositionGroupsDeduped, sources]);

  const articleSectionsGroupedByInstrument = useMemo(
    () => buildArticleSectionsGrouped(sortedPropositionGroups, sources),
    [sortedPropositionGroups, sources]
  );

  const articleSectionsGroupedByScope = useMemo(
    () => buildScopeSectionsGrouped(sortedPropositionGroups, scopeLinkRowsByPropId, scopeById),
    [sortedPropositionGroups, scopeLinkRowsByPropId, scopeById]
  );

  const articleSectionsGrouped = useMemo(() => {
    if (explorerNavMode === "by_scope") {
    return articleSectionsGroupedByScope.map((sec) => ({
      clusterKey: sec.clusterKey,
      instrumentSectionHeading: null,
      sectionHeadline: sec.scopeSectionLabel,
      sectionHeadlineCompact: sec.scopeSectionLabel,
      sectionSubtitle:
        "Grouped by primary scope links (direct relevance + high confidence).",
      groups: sec.groups,
    }));
    }
    return articleSectionsGroupedByInstrument.map((sec) => {
      const allRows = sec.groups.flatMap((g) => g.rows);
      const h = formatExplorerSectionHeading(sec.clusterKey, sources, allRows);
      return {
        clusterKey: sec.clusterKey,
        instrumentSectionHeading: h,
        sectionHeadline: h.headline,
        sectionHeadlineCompact: h.headlineCompact,
        sectionSubtitle: h.subtitle,
        groups: sec.groups,
      };
    });
  }, [
    articleSectionsGroupedByInstrument,
    articleSectionsGroupedByScope,
    explorerNavMode,
    sources,
  ]);

  const serverGroupedSections = useMemo(
    () => buildSectionsFromPropositionSummaries(filteredGroupSummaries, explorerNavMode, sources),
    [filteredGroupSummaries, explorerNavMode, sources]
  );

  const updateClassificationFilter = useCallback(
    <K extends keyof ExplorerClassificationFilters>(key: K, value: ExplorerClassificationFilters[K]) => {
      setClassificationFilters((prev) => ({ ...prev, [key]: value }));
    },
    []
  );

  const loadMorePropositionGroups = useCallback(async () => {
    if (!selectedRunId || showDuplicatesFlat || groupsLoading) {
      return;
    }
    if (groupSummaries.length >= groupsTotalGroups) {
      return;
    }
    const c = new AbortController();
    setGroupsLoading(true);
    try {
      await fetchPropositionGroupList(c.signal, {
        offset: groupSummaries.length,
        append: true,
      });
    } catch (exc) {
      setActionError(exc instanceof Error ? exc.message : "Load more failed");
    } finally {
      setGroupsLoading(false);
    }
  }, [
    selectedRunId,
    showDuplicatesFlat,
    groupsLoading,
    groupSummaries.length,
    groupsTotalGroups,
    fetchPropositionGroupList,
  ]);

  const selectedSourceDocumentTitle = useMemo(() => {
    const sid = filterSourceId.trim();
    if (!sid) {
      return "";
    }
    let hit: UnknownRecord | undefined;
    for (const s of sources) {
      if (String((s as { id?: string }).id ?? "").trim() === sid) {
        hit = s;
        break;
      }
    }
    const base = shortInstrumentLabel(hit);
    if (base) {
      return base;
    }
    return sourceTitleById.get(sid)?.trim() || sid;
  }, [filterSourceId, sourceTitleById, sources]);

  const flatRowsSorted = useMemo(() => {
    return [...filteredRows].sort((a, b) => {
      const ka = explorerSectionClusterKeyFromRow(a, sources);
      const kb = explorerSectionClusterKeyFromRow(b, sources);
      if (ka !== kb) {
        return compareExplorerSectionClusterKeys(ka, kb);
      }
      const oa = asRecord(a.original_artifact) ?? {};
      const ob = asRecord(b.original_artifact) ?? {};
      const ia = oa.order_index;
      const ib = ob.order_index;
      if (typeof ia === "number" && typeof ib === "number" && ia !== ib) {
        return ia - ib;
      }
      if (typeof ia === "number" && typeof ib !== "number") {
        return -1;
      }
      if (typeof ia !== "number" && typeof ib === "number") {
        return 1;
      }
      return String(oa.id ?? "").localeCompare(String(ob.id ?? ""));
    });
  }, [filteredRows, sources]);

  const flatArticleSections = useMemo(() => {
    const order: string[] = [];
    const m = new Map<string, UnknownRecord[]>();
    for (const row of flatRowsSorted) {
      const ck = explorerSectionClusterKeyFromRow(row, sources);
      if (!m.has(ck)) {
        order.push(ck);
        m.set(ck, []);
      }
      m.get(ck)!.push(row);
    }
    return order.map((clusterKey) => ({ clusterKey, rows: m.get(clusterKey)! }));
  }, [flatRowsSorted, sources]);

  const traceModalPayload = useMemo(() => {
    if (!traceModalPid) {
      return null;
    }
    return traceByPropId.get(traceModalPid) ?? null;
  }, [traceByPropId, traceModalPid]);

  const openFragmentModal = async (
    sourceRecordId: string,
    fragmentId: string,
    options?: { highlightLocator?: string; contextInjections?: UnknownRecord | null }
  ) => {
    if (!selectedRunId) {
      return;
    }
    setFragmentModalOpen(true);
    setFragmentModalCaption({ source_record_id: sourceRecordId, fragment_id: fragmentId });
    setFragmentHighlightLocator((options?.highlightLocator ?? "").trim());
    const inj = options?.contextInjections;
    setFragmentModalContextInjections(inj && typeof inj === "object" ? inj : null);
    setFragmentBusy(true);
    setFragmentText("");
    setActionError(null);
    try {
      const url = `${API_BASE_URL}/ops/source-fragments?run_id=${encodeURIComponent(selectedRunId)}&source_record_id=${encodeURIComponent(sourceRecordId)}`;
      const r = await fetch(url, { headers: { Accept: "application/json" } });
      if (!r.ok) {
        throw new Error(`fragments ${r.status}`);
      }
      const j: unknown = await r.json();
      const fragRows = asRecord(j)?.source_fragments;
      const rows = Array.isArray(fragRows) ? fragRows : [];
      const hit = rows.find((x) => {
        const rr = x as UnknownRecord;
        return String(rr.id ?? "") === fragmentId || String(rr.fragment_id ?? "") === fragmentId;
      }) as UnknownRecord | undefined;
      const text =
        typeof hit?.fragment_text === "string" ? hit.fragment_text : JSON.stringify(hit, null, 2);
      setFragmentText(text);
    } catch (exc) {
      setActionError(exc instanceof Error ? exc.message : "Fragment load failed");
    } finally {
      setFragmentBusy(false);
    }
  };

  const closeFragmentModal = (): void => {
    setFragmentModalOpen(false);
    setFragmentModalContextInjections(null);
  };

  const appendPipelineReviewDecision = async (
    propositionId: string,
    artifactType: string,
    artifactId: string,
    decision: PipelineReviewAction
  ) => {
    if (!selectedRunId) {
      return;
    }
    setActionBusyKey(`${propositionId}|${artifactType}`);
    setActionError(null);
    try {
      const r = await fetch(
        `${API_BASE_URL}/ops/runs/${encodeURIComponent(selectedRunId)}/pipeline-review-decisions`,
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            artifact_type: artifactType,
            artifact_id: artifactId,
            decision,
            reviewer: reviewerNote.trim().length > 0 ? reviewerNote.trim().slice(0, 240) : null,
            reason: "",
          }),
        }
      );
      if (!r.ok) {
        const detail = await r.text().catch(() => "");
        throw new Error(detail ? `${r.status}: ${detail}` : `HTTP ${r.status}`);
      }
      const ac = new AbortController();
      if (showDuplicatesFlat) {
        await loadFullRunArtifacts(selectedRunId, ac.signal);
      } else {
        await loadLightRunArtifacts(selectedRunId, ac.signal);
        setGroupDetailById({});
        setGroupDetailLoading({});
        await fetchPropositionGroupList(ac.signal, { offset: 0, append: false });
      }
      setReviewRecordedFlash({ propositionId, at: Date.now() });
    } catch (exc) {
      setActionError(exc instanceof Error ? exc.message : "Decision failed");
    } finally {
      setActionBusyKey(null);
    }
  };

  const uniqueSources = useMemo(() => {
    const ids = new Set<string>();
    for (const row of sources) {
      const sid = String((row as UnknownRecord).id ?? "").trim();
      if (sid) {
        ids.add(sid);
      }
    }
    return [...ids].sort((a, b) => a.localeCompare(b));
  }, [sources]);

  const uniqueInstrumentFamilies = useMemo(() => {
    const keys = new Set<string>();
    for (const s of sources) {
      keys.add(sourceInstrumentFamilyKeyFromSourceRecord(s));
    }
    return [...keys].sort((a, b) => a.localeCompare(b));
  }, [sources]);

  const selectedRunMeta = useMemo(
    () => runs.find((r) => r.run_id === selectedRunId),
    [runs, selectedRunId]
  );

  const divergencesChipDisabled =
    !selectedRunId ||
    !selectedRunMeta ||
    !(
      typeof selectedRunMeta.divergence_assessment_count === "number" &&
      selectedRunMeta.divergence_assessment_count > 0
    );

  const opsRunLinks = useMemo(() => {
    if (!selectedRunId) {
      return null;
    }
    const q = `run_id=${encodeURIComponent(selectedRunId)}`;
    return {
      fragments: `${API_BASE_URL}/ops/source-fragments?${q}`,
      traces: `${API_BASE_URL}/ops/effective/proposition-extraction-traces?${q}`,
      quality: `${API_BASE_URL}/ops/run-quality-summary?${q}`,
    };
  }, [selectedRunId]);

  const bannerSourceCount =
    typeof runQualitySummary?.source_count === "number"
      ? (runQualitySummary.source_count as number)
      : sources.length;
  const bannerPropCount =
    typeof runQualitySummary?.proposition_count === "number"
      ? (runQualitySummary.proposition_count as number)
      : typeof selectedRunMeta?.proposition_count === "number"
        ? selectedRunMeta.proposition_count
        : effectivePropositions.length;
  const bannerErr =
    typeof runQualitySummary?.error_count === "number"
      ? (runQualitySummary.error_count as number)
      : null;
  const bannerWarn =
    typeof runQualitySummary?.warning_count === "number"
      ? (runQualitySummary.warning_count as number)
      : null;
  const bannerQuality =
    typeof runQualitySummary?.status === "string" ? (runQualitySummary.status as string) : null;

  const metricsObj = runQualitySummary ? asRecord(runQualitySummary.metrics) : null;
  const repairMetricsPresent =
    metricsObj != null && Object.prototype.hasOwnProperty.call(metricsObj, "repairable_extraction");
  const repairScan = metricsObj ? asRecord(metricsObj.repairable_extraction) : null;
  const apiSaysRepair = Boolean(repairScan?.has_repairable_failures);
  const clientRepairHint = useMemo(
    () => clientRepairableExtractionHintFromExplorerData(effectiveTraces, effectivePropositions),
    [effectiveTraces, effectivePropositions]
  );
  const extractionRepairSuggested = apiSaysRepair || clientRepairHint;
  const repairBannerReasonsLine = repairBannerFailureReasonsSentence(repairScan?.failure_reasons);
  const repairBannerCreditsQuotaHelperLine = repairBannerNeedsCreditsQuotaHelper(
    repairScan?.failure_reasons,
  );
  const showRepairStatusDiagnostic =
    Boolean(selectedRunId) &&
    !runDataLoading &&
    !extractionRepairSuggested &&
    (runQualityRequestFailed || !repairMetricsPresent);

  const scopeSection = useCallback(
    (propositionId: string, scopeRows: UnknownRecord[], extractionConfidence: string) => (
      <div className="space-y-3 text-sm">
        <PropositionScopeLinksSection
          propositionId={propositionId}
          scopeRows={scopeRows}
          scopeById={scopeById}
        />
        <div className="border-t border-border/45 pt-2">
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Structured extraction confidence
          </p>
          <p className="mt-1 text-xs leading-snug text-foreground/85">
            <span className="font-mono">{extractionConfidence}</span>
            <span className="block text-muted-foreground">
              From the extraction trace artifact (effective value). Separate from pipeline review in
              the panel below.
            </span>
          </p>
        </div>
      </div>
    ),
    [scopeById]
  );

  return (
    <div className="space-y-4">
      {actionError ? (
        <p className="rounded border border-destructive/40 bg-destructive/[0.08] px-3 py-2 text-sm text-destructive">
          {actionError}
        </p>
      ) : null}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">Runs & reviewers</CardTitle>
          <CardDescription>
            Defaults to latest run. Pipeline review writes append governance rows on the exported
            bundle served by this API.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-4 text-sm">
          <label className="flex min-w-[12rem] flex-col gap-1">
            <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Pipeline run
            </span>
            <select
              value={selectedRunId ?? ""}
              onChange={(e) => setSelectedRunId(e.target.value.trim() ? e.target.value : null)}
              className="rounded border border-border/80 bg-background px-2 py-1 font-mono text-xs outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
              disabled={runsLoading && runs.length === 0}
            >
              {runs.map((rn) => (
                <option key={rn.run_id} value={rn.run_id}>
                  {rn.run_id}
                  {rn.created_at ? ` · ${rn.created_at}` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-w-[12rem] flex-col gap-1">
            <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Reviewer (optional)
            </span>
            <input
              value={reviewerNote}
              onChange={(e) => setReviewerNote(e.target.value)}
              placeholder="stored in browser session only"
              className="rounded border border-border/80 bg-background px-2 py-1 text-xs outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
            />
          </label>
        </CardContent>
      </Card>

      {!runsLoading && runs.length > 0 && selectedRunId ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Selected run snapshot</CardTitle>
            <CardDescription>Counts from manifest / run-quality where available.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-x-5 gap-y-2 text-[11px] text-foreground/90">
            <span>
              <span className="text-muted-foreground">run id:</span>{" "}
              <span className="font-mono text-xs">{selectedRunId}</span>
            </span>
            <span>
              <span className="text-muted-foreground">sources:</span> {bannerSourceCount}
            </span>
            <span>
              <span className="text-muted-foreground">propositions:</span> {bannerPropCount}
            </span>
            <span>
              <span className="text-muted-foreground">errors / warnings:</span>{" "}
              {bannerErr !== null ? bannerErr : "—"}
              {" / "}
              {bannerWarn !== null ? bannerWarn : "—"}
            </span>
            <span>
              <span className="text-muted-foreground">quality:</span> {bannerQuality ?? "—"}
            </span>
            {extractionRepairSuggested ? (
              <div className="mt-2 w-full rounded border border-amber-500/40 bg-amber-500/[0.08] px-3 py-2 text-[11px] leading-snug text-foreground/95">
                <p className="font-medium text-amber-950 dark:text-amber-50">
                  This run has repairable extraction failures (credits/quota/context/JSON infra).
                </p>
                {repairBannerReasonsLine ? (
                  <p className="mt-1 text-muted-foreground">{repairBannerReasonsLine}</p>
                ) : null}
                {repairBannerCreditsQuotaHelperLine ? (
                  <p className="mt-1 text-muted-foreground">
                    {REPAIR_BANNER_CREDITS_QUOTA_HELPER_TEXT}
                  </p>
                ) : null}
                <ul className="mt-1 list-disc pl-4 text-muted-foreground">
                  <li>
                    failed chunks:{" "}
                    <span className="font-mono text-foreground/90">
                      {typeof repairScan?.repairable_chunk_count === "number"
                        ? repairScan.repairable_chunk_count
                        : "—"}
                    </span>
                  </li>
                  <li>
                    affected propositions:{" "}
                    <span className="font-mono text-foreground/90">
                      {typeof repairScan?.affected_proposition_count === "number"
                        ? repairScan.affected_proposition_count
                        : "—"}
                    </span>
                  </li>
                  <li>
                    est. retry tokens:{" "}
                    <span className="font-mono text-foreground/90">
                      {formatRepairBannerRetryTokenEstimate(repairScan)}
                    </span>
                  </li>
                </ul>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    disabled={repairExtractionBusy || !selectedRunId}
                    className="rounded border border-border/90 bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent/70 disabled:cursor-not-allowed disabled:opacity-50"
                    onClick={async () => {
                      if (!selectedRunId) return;
                      setRepairExtractionBusy(true);
                      setRepairExtractionMessage(null);
                      try {
                        const body: Record<string, unknown> = {
                          retry_failed_llm: true,
                        };
                        if (OPS_EXPORT_DIR) {
                          body.export_dir = OPS_EXPORT_DIR;
                        } else {
                          body.run_id = selectedRunId;
                        }
                        const res = await fetch(
                          `${API_BASE_URL}/ops/run-jobs/repair-extraction`,
                          {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify(body),
                          }
                        );
                        const resBody = await res.json().catch(() => ({}));
                        if (!res.ok) {
                          setRepairExtractionMessage(
                            typeof resBody?.detail === "string"
                              ? resBody.detail
                              : `Repair failed (${res.status})`
                          );
                          return;
                        }
                        setRepairExtractionMessage(
                          `Repaired bundle written (${String(resBody.output_dir ?? "")}); new run ${String(resBody.run_id ?? "")}.`
                        );
                        const ctl = new AbortController();
                        void fetchRunsCatalog(ctl.signal, { silent: true });
                      } finally {
                        setRepairExtractionBusy(false);
                      }
                    }}
                  >
                    {repairExtractionBusy ? "Repairing…" : "Repair failed extraction chunks"}
                  </button>
                  {OPS_EXPORT_DIR ? (
                    <span className="text-muted-foreground">
                      Dev override: repairing via{" "}
                      <code className="font-mono text-[10px]">NEXT_PUBLIC_LAW_PROPOSITION_EXTRACTOR_OPS_EXPORT_DIR</code>.
                    </span>
                  ) : null}
                </div>
                {repairExtractionMessage ? (
                  <p className="mt-2 text-[11px] text-muted-foreground">{repairExtractionMessage}</p>
                ) : null}
              </div>
            ) : null}
            {showRepairStatusDiagnostic ? (
              <p className="mt-2 w-full text-[11px] text-muted-foreground">
                Repair status could not be computed for this run.
              </p>
            ) : null}
            {opsRunLinks ? (
              <div className="mt-3 w-full space-y-2 border-t border-border/40 pt-3">
                <p className="text-[11px] font-medium text-foreground/90">
                  Trust & inspection (opens JSON in a new tab)
                </p>
                <div className="flex flex-wrap gap-2">
                  <a
                    href={opsRunLinks.quality}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded border border-border/80 bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent/60"
                  >
                    View run quality summary (JSON)
                  </a>
                  <a
                    href={opsRunLinks.traces}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded border border-border/80 bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent/60"
                  >
                    View proposition extraction traces (JSON)
                  </a>
                  <a
                    href={opsRunLinks.fragments}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded border border-border/80 bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent/60"
                  >
                    View source fragments (JSON)
                  </a>
                </div>
                <p className="max-w-prose text-[11px] leading-snug text-muted-foreground">
                  Full export lint is not exposed as an API — run{" "}
                  <code className="rounded bg-muted/80 px-1 py-px font-mono text-[10px] text-foreground/90">
                    {LINT_EXPORT_CLI}
                  </code>{" "}
                  against the same directory as the running API; the run quality JSON above includes
                  the bundled summary from the export when present.
                </p>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">Filters</CardTitle>
          <CardDescription>
            Narrow the list client-side. Scope matches{" "}
            <strong>primary</strong> taxonomy links only (direct relevance + high confidence — same
            chips as the default collapsed scope list per proposition).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-8">
          <div className="space-y-4">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
              A. Find propositions
            </h3>
            <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
              <label className="flex min-w-0 flex-col gap-1 text-xs">
                <span className="uppercase tracking-wide text-muted-foreground">Scope filter</span>
                <input
                  value={filterScopeSlug}
                  onChange={(e) => setFilterScopeSlug(e.target.value)}
                  placeholder="slug, id, label, or synonym (exact)"
                  className="min-w-[12rem] max-w-xl rounded border border-border/80 px-2 py-1 font-mono outline-none focus:border-primary"
                />
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Presets
              </span>
              {SCOPE_FILTER_PRESETS.map((p) => {
                const active = filterScopeSlug.trim().toLowerCase() === p.token.toLowerCase();
                return (
                  <button
                    key={p.token}
                    type="button"
                    title={`Filter by ${p.token} (primary scope links)`}
                    className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                      active
                        ? "border-primary bg-priguidance-discovery/15 text-foreground"
                        : "border-border/80 bg-muted/40 text-foreground/90 hover:bg-muted/70"
                    }`}
                    onClick={() => applyScopePreset(p.token)}
                  >
                    {p.label}
                  </button>
                );
              })}
              <button
                type="button"
                className="rounded border border-dashed border-border/80 px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-muted/50"
                onClick={() => applyScopePreset("")}
              >
                Clear scope
              </button>
            </div>
            <div className="flex flex-col gap-2 border-t border-border/50 pt-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  View existing results
                </span>
                {(
                  [
                    ["all", null, "All results"],
                    ["eu", "🇪🇺", "EU only"],
                    ["uk", "🇬🇧", "UK only"],
                    ["grouped", null, "Grouped EU/UK"],
                    ["divergences", null, "Divergences"],
                  ] as const
                ).map(([key, emoji, label]) => {
                  const disabled = key === "divergences" && divergencesChipDisabled;
                  const visuallyActive = jurisdictionView === key && !disabled;
                  const title =
                    disabled && key === "divergences"
                      ? "No comparison run available for this dataset"
                      : "Display-only filter — does not rerun analysis or call a model";
                  return (
                    <button
                      key={key}
                      type="button"
                      disabled={disabled}
                      title={title}
                      aria-pressed={visuallyActive}
                      className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                        disabled
                          ? "cursor-not-allowed border-border/50 bg-muted/20 text-muted-foreground opacity-70"
                          : visuallyActive
                            ? "border-primary bg-priguidance-discovery/15 text-foreground"
                            : "border-border/80 bg-muted/40 text-foreground/90 hover:bg-muted/70"
                      }`}
                      onClick={() => {
                        if (!disabled) {
                          applyJurisdictionView(key);
                        }
                      }}
                    >
                      {emoji ? (
                        <>
                          <span aria-hidden="true">{emoji}</span>
                          <span className="pl-1">{label}</span>
                        </>
                      ) : (
                        label
                      )}
                    </button>
                  );
                })}
              </div>
              <p className="max-w-prose text-[10px] leading-snug text-muted-foreground">
                Changing view does not rerun analysis or call a model.
              </p>
              {jurisdictionView === "grouped" ? (
                <p className="max-w-prose text-[10px] leading-snug text-muted-foreground">
                  Grouped EU/UK view shows source rows from multiple jurisdictional source versions
                  when they share a canonical proposition lineage.
                </p>
              ) : null}
            </div>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-[minmax(20rem,3fr)_minmax(11rem,1.4fr)] xl:items-end">
              <label className="flex min-w-0 flex-col gap-1 text-xs">
                <span className="uppercase tracking-wide text-muted-foreground">Source document</span>
                <select
                  value={filterSourceId}
                  onChange={(e) => setFilterSourceId(e.target.value)}
                  className="w-full min-w-0 rounded border border-border/80 px-2 py-1.5 text-[11px] outline-none focus:border-primary"
                >
                  <option value="">(any)</option>
                  {uniqueSources.map((sid) => (
                    <option
                      key={sid}
                      value={sid}
                      title={sourceDocumentFilterOptionTitle(sid, sources, sourceTitleById)}
                    >
                      {sourceDocumentFilterLabel(sid, sources, sourceTitleById)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex min-w-0 flex-col gap-1 text-xs">
                <span className="uppercase tracking-wide text-muted-foreground">
                  Instrument family
                </span>
                <select
                  value={filterInstrumentFamily}
                  onChange={(e) => setFilterInstrumentFamily(e.target.value)}
                  className="w-full min-w-0 rounded border border-border/80 px-2 py-1.5 text-[11px] outline-none focus:border-primary"
                >
                  <option value="">(any)</option>
                  {uniqueInstrumentFamilies.map((fam) => (
                    <option key={fam} value={fam}>
                      {instrumentFamilyFilterLabel(fam)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          <div className="space-y-4 border-t border-border/60 pt-6">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
              B. Proposition classification
            </h3>
            <p className="max-w-prose text-[11px] leading-snug text-muted-foreground">
              Default view emphasises substantive, procedural, definitional, and scope rules. Citation
              and commencement are hidden unless you enable instrument metadata. Scope/application
              rules can appear in a collapsed section per article.
            </p>
            <div className="flex flex-wrap gap-4">
              <label className="flex cursor-pointer items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={classificationFilters.showInstrumentMetadata}
                  onChange={(e) =>
                    updateClassificationFilter("showInstrumentMetadata", e.target.checked)
                  }
                  className="rounded border-border accent-primary"
                />
                Show instrument metadata
              </label>
              <label className="flex cursor-pointer items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={classificationFilters.complianceRelevantOnly}
                  onChange={(e) =>
                    updateClassificationFilter("complianceRelevantOnly", e.target.checked)
                  }
                  className="rounded border-border accent-primary"
                />
                Compliance-relevant only
              </label>
              <label className="flex cursor-pointer items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={classificationFilters.comparisonAnchorsOnly}
                  onChange={(e) =>
                    updateClassificationFilter("comparisonAnchorsOnly", e.target.checked)
                  }
                  className="rounded border-border accent-primary"
                />
                Comparison anchors only
              </label>
              <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={classificationFilters.collapseScopeRules}
                  onChange={(e) =>
                    updateClassificationFilter("collapseScopeRules", e.target.checked)
                  }
                  className="rounded border-border accent-primary"
                />
                Collapse scope/application section
              </label>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <label className="flex flex-col gap-1 text-xs">
                <span className="uppercase tracking-wide text-muted-foreground">Proposition tier</span>
                <select
                  value={classificationFilters.filterPropositionTier}
                  onChange={(e) =>
                    updateClassificationFilter("filterPropositionTier", e.target.value)
                  }
                  className="w-full rounded border border-border/80 px-2 py-1 outline-none focus:border-primary"
                >
                  {PROPOSITION_TIER_FILTER_OPTIONS.map((o) => (
                    <option key={o.value || "any"} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs">
                <span className="uppercase tracking-wide text-muted-foreground">Legal effect type</span>
                <select
                  value={classificationFilters.filterLegalEffectType}
                  onChange={(e) =>
                    updateClassificationFilter("filterLegalEffectType", e.target.value)
                  }
                  className="w-full rounded border border-border/80 px-2 py-1 outline-none focus:border-primary"
                >
                  {LEGAL_EFFECT_FILTER_OPTIONS.map((o) => (
                    <option key={o.value || "any"} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs">
                <span className="uppercase tracking-wide text-muted-foreground">
                  Territorial application
                </span>
                <input
                  value={classificationFilters.filterTerritorialApplication}
                  onChange={(e) =>
                    updateClassificationFilter("filterTerritorialApplication", e.target.value)
                  }
                  placeholder="e.g. England"
                  className="w-full rounded border border-border/80 px-2 py-1 outline-none focus:border-primary"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs">
                <span className="uppercase tracking-wide text-muted-foreground">Extent</span>
                <input
                  value={classificationFilters.filterExtent}
                  onChange={(e) => updateClassificationFilter("filterExtent", e.target.value)}
                  placeholder="e.g. Wales"
                  className="w-full rounded border border-border/80 px-2 py-1 outline-none focus:border-primary"
                />
              </label>
            </div>
          </div>

          <div className="space-y-4 border-t border-border/60 pt-6">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
              C. Review filters
            </h3>
            <div className="grid gap-4 sm:grid-cols-2 sm:max-w-2xl">
              <label className="flex flex-col gap-1 text-xs">
                <span className="uppercase tracking-wide text-muted-foreground">Confidence</span>
                <select
                  value={filterConfidence}
                  onChange={(e) => setFilterConfidence(e.target.value)}
                  className="w-full rounded border border-border/80 px-2 py-1 outline-none focus:border-primary"
                >
                  <option value="">(any)</option>
                  <option value="high">high</option>
                  <option value="medium">medium</option>
                  <option value="low">low</option>
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs">
                <span className="uppercase tracking-wide text-muted-foreground">
                  Raw extraction review status
                </span>
                <select
                  value={filterReview}
                  onChange={(e) => setFilterReview(e.target.value)}
                  className="w-full rounded border border-border/80 px-2 py-1 outline-none focus:border-primary"
                >
                  <option value="">(any)</option>
                  <option value="generated">generated</option>
                  <option value="approved">approved</option>
                  <option value="rejected">rejected</option>
                  <option value="needs_review">needs_review</option>
                  <option value="overridden">overridden</option>
                  <option value="deferred">deferred</option>
                </select>
              </label>
            </div>
            <div className="grid gap-4 sm:grid-cols-1 sm:max-w-2xl">
              <label className="flex flex-col gap-1 text-xs">
                <span className="uppercase tracking-wide text-muted-foreground">
                  Search propositions (server-side)
                </span>
                <input
                  type="search"
                  value={propositionsSearchInput}
                  onChange={(e) => setPropositionsSearchInput(e.target.value)}
                  placeholder="Substring match on text, label, locator, keys…"
                  className="w-full rounded border border-border/80 px-2 py-1.5 text-[12px] outline-none focus:border-primary"
                />
              </label>
            </div>
          </div>

          <div className="space-y-4 border-t border-border/60 pt-6">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
              D. Display
            </h3>
            {propositionDisplayMode === "raw" && !showDuplicatesFlat ? (
              <p className="max-w-prose rounded-md border border-amber-700/30 bg-amber-950/10 px-3 py-2 text-[11px] leading-snug text-amber-950 dark:text-amber-100">
                Raw debug mode can be slow for large runs. Filters and pagination still apply; source
                fragments and full extraction traces load only when you use those actions.
              </p>
            ) : null}
            <div className="flex flex-col gap-4 lg:flex-row lg:flex-wrap lg:items-end lg:gap-8">
              <label className="flex flex-col gap-1 text-xs lg:min-w-[14rem]">
                <span className="uppercase tracking-wide text-muted-foreground">Corpus view</span>
                <select
                  value={explorerNavMode}
                  onChange={(e) => setExplorerNavMode(e.target.value as ExplorerNavMode)}
                  className="w-full rounded border border-border/80 px-2 py-1 outline-none focus:border-primary lg:min-w-[13rem]"
                >
                  <option value="source_document">By source document</option>
                  <option value="by_scope">By scope</option>
                  <option value="compare_versions">Compare source versions</option>
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs lg:min-w-[12rem]">
                <span className="uppercase tracking-wide text-muted-foreground">Structured / raw view</span>
                <select
                  value={propositionDisplayMode}
                  onChange={(e) =>
                    setPropositionDisplayMode(e.target.value as PropositionDisplayMode)
                  }
                  className="w-full rounded border border-border/80 px-2 py-1 outline-none focus:border-primary lg:min-w-[11rem]"
                >
                  <option value="structured">Structured view (default)</option>
                  <option value="raw">Raw proposition view (debug)</option>
                </select>
              </label>
              <label className="flex cursor-pointer flex-row items-center gap-2 rounded border border-dashed border-border/80 px-2 py-1.5 text-xs text-muted-foreground lg:inline-flex lg:py-2">
                <input
                  type="checkbox"
                  checked={showDuplicatesFlat}
                  onChange={(e) => setShowDuplicatesFlat(e.target.checked)}
                  className="rounded border-border accent-primary"
                />
                <span>
                  Show duplicate rows <span className="text-[10px]">(flat list · debug)</span>
                </span>
              </label>
              {propositionDisplayMode === "raw" && semanticMergeCollapsedGroupCount > 0 ? (
                <p className="max-w-xl text-[11px] leading-snug text-muted-foreground">
                  Semantic merge collapsed {semanticMergeCollapsedGroupCount} duplicate proposition
                  group
                  {semanticMergeCollapsedGroupCount === 1 ? "" : "s"}; card source-row counts
                  include every merged row.
                </p>
              ) : null}
            </div>
          </div>
        </CardContent>
      </Card>

      {runsLoading || runDataLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : null}

      {!runsLoading && runs.length === 0 && !error ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">No analysis runs yet</CardTitle>
            <CardDescription>
              Go to{" "}
              <Link
                href="/ops"
                className="font-medium text-primary underline-offset-2 hover:underline"
              >
                Operations / Registry
              </Link>
              , select sources, and run analysis. The API writes each run into the export directory;
              this page refreshes when the window regains focus.
            </CardDescription>
            <CardDescription className="border-t border-border/60 pt-3 text-xs leading-relaxed">
              <span className="font-medium text-foreground">Dev/demo:</span> load the Article 109
              equine pilot into the API export directory, then reload this page or refocus the
              window:
              <code className="mt-1 block whitespace-pre-wrap rounded bg-muted/80 px-2 py-1.5 font-mono text-[11px] text-foreground/90">
                just run-art109-equine-pilot
              </code>
              <span className="block pt-1 text-muted-foreground">
                Uses <span className="font-mono">OPERATIONS_EXPORT_DIR</span> (default{" "}
                <span className="font-mono">dist/static-report</span>) — must match the running API.
                Opens{" "}
                <Link
                  href="/propositions?scope=equine"
                  className="font-medium text-primary underline-offset-2 hover:underline"
                >
                  /propositions?scope=equine
                </Link>{" "}
                after export.
              </span>
            </CardDescription>
          </CardHeader>
        </Card>
      ) : null}

      {!runsLoading && !runDataLoading && error ? (
        <Card className="border-destructive/40">
          <CardHeader>
            <CardTitle className="text-base text-destructive">
              Unable to reach operations API
            </CardTitle>
            <CardDescription>
              Confirm the FastAPI backend is running and export dir has runs.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <code className="text-sm text-destructive">{error}</code>
          </CardContent>
        </Card>
      ) : null}

      {!runsLoading && !runDataLoading && !error ? (
        <div className="space-y-3">
          {jurisdictionView === "divergences" && divergencesChipDisabled && selectedRunId ? (
            <p className="rounded-md border border-border/55 bg-muted/[0.08] px-3 py-2 text-[11px] leading-snug text-muted-foreground">
              No divergence comparison has been run for this selection.
            </p>
          ) : null}
          <p className="rounded-md border border-border/60 bg-muted/[0.12] px-3 py-2 text-[12px] leading-snug text-foreground/90">
            <span className="font-medium text-foreground">How to read this page:</span> Each card is
            a <span className="font-medium text-foreground">proposition group</span> (one legal
            proposition). Source rows inside the card are extracts from specific sources;{" "}
            <span className="font-medium text-foreground">EU</span> /{" "}
            <span className="font-medium text-foreground">UK</span> chips mark jurisdictional
            versions, not a divergence finding.
          </p>
          <p className="rounded-md border border-border/55 bg-background px-3 py-2 text-[12px] leading-snug text-foreground/90">
            {scopeFilterTrimmed && filterSourceId.trim() ? (
              <>
                Showing propositions with primary scope matching{" "}
                <span className="font-semibold text-foreground">{scopeFilterExplainerLabel}</span>,
                extracted from{" "}
                <span className="font-semibold text-foreground">
                  {selectedSourceDocumentTitle}
                </span>
                .
              </>
            ) : scopeFilterTrimmed ? (
              <>
                Showing propositions with primary scope matching:{" "}
                <span className="font-semibold text-foreground">{scopeFilterExplainerLabel}</span>.
              </>
            ) : filterSourceId.trim() ? (
              <>
                Showing propositions extracted from:{" "}
                <span className="font-semibold text-foreground">
                  {selectedSourceDocumentTitle}
                </span>
                .
              </>
            ) : (
              <>
                Showing all extracted propositions across the selected corpus. Article sections are
                grouped by source document and provision.
              </>
            )}
          </p>
          {explorerNavMode === "compare_versions" ? (
            <p className="rounded-md border border-border/50 bg-muted/[0.1] px-3 py-2 text-[11px] leading-snug text-muted-foreground">
              <span className="font-medium text-foreground/85">Compare source versions:</span>{" "}
              same layout as <span className="font-medium text-foreground/90">By source document</span>
              ; expand proposition groups to review EU/UK (and other) rows together.
            </p>
          ) : null}
          <p className="rounded-md border border-dashed border-border/50 bg-muted/[0.08] px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
            <span className="font-medium text-foreground/80">Legend.</span> Proposition group = one
            legal proposition, possibly extracted from multiple source versions. Source row = one
            extracted version from a specific source/jurisdiction.
          </p>
          <p className="text-[11px] text-muted-foreground">
            {showDuplicatesFlat ? (
              <>
                Showing {filteredRows.length} of {effectivePropositions.length} propositions (flat)
              </>
            ) : (
              <>
                Showing {groupSummaries.length} of {groupsTotalGroups} proposition groups (
                <span title="underlying source-specific rows">{groupsTotalRows} rows</span>)
                {groupsLoading ? " · updating…" : ""}
              </>
            )}
            {selectedRunId ? (
              <>
                {" "}
                for run <span className="font-mono text-foreground/80">{selectedRunId}</span>
              </>
            ) : null}
          </p>

          {(showDuplicatesFlat ? filteredRows.length > 0 : groupSummaries.length > 0 || groupsLoading) ? (
            <>
              {!showDuplicatesFlat ? (
                <>
                  <PropositionExplorerServerList
                  sections={serverGroupedSections}
                  sources={sources}
                  scopeById={scopeById}
                  scopeLinkRowsByPropId={scopeLinkRowsByPropId}
                  sourceTitleById={sourceTitleById}
                  propositionDisplayMode={propositionDisplayMode}
                  groupDetailById={groupDetailById}
                  groupDetailLoading={groupDetailLoading}
                  ensureGroupDetailLoaded={ensureGroupDetailLoaded}
                  pipelineReviewDecisions={pipelineReviewDecisions}
                  actionBusyKey={actionBusyKey}
                  reviewRecordedFlash={reviewRecordedFlash}
                  appendPipelineReviewDecision={appendPipelineReviewDecision}
                  openFragmentModal={openFragmentModal}
                  setTraceModalPid={setTraceModalPid}
                  traceByPropId={traceByPropId}
                  initialArticleSectionsOpen={INITIAL_ARTICLE_SECTIONS_OPEN}
                  filtersActive={filtersActive}
                  classificationFilters={classificationFilters}
                  propositionArtifactById={propositionArtifactById}
                />
                  {groupSummaries.length < groupsTotalGroups ? (
                    <div className="flex justify-center py-4">
                      <button
                        type="button"
                        disabled={groupsLoading}
                        className="rounded border border-border/80 bg-muted/30 px-4 py-2 text-[12px] font-medium hover:bg-muted/50 disabled:opacity-50"
                        onClick={() => void loadMorePropositionGroups()}
                      >
                        {groupsLoading
                          ? "Loading…"
                          : `Load more groups (${groupSummaries.length} / ${groupsTotalGroups})`}
                      </button>
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="space-y-4">
                  {flatArticleSections.map(({ clusterKey, rows }, secIdx) => {
                    const fh = formatExplorerSectionHeading(clusterKey, sources, rows);
                    const rowCount = rows.length;
                    const { primarySlugs, secondarySlugCount } = aggregatePrimaryScopeSlugsForRows(
                      rows,
                      scopeLinkRowsByPropId,
                      scopeById
                    );
                    const scopeBannerHasLinks = primarySlugs.length > 0 || secondarySlugCount > 0;
                    const articleSectionOpen =
                      filtersActive || secIdx < INITIAL_ARTICLE_SECTIONS_OPEN;
                    return (
                      <details
                        key={clusterKey}
                        className={ARTICLE_SECTION_DETAILS_CLASS}
                        open={articleSectionOpen}
                      >
                        <summary className={ARTICLE_SECTION_SUMMARY_CLASS}>
                          <p className={`${HIER_SECTION_LABEL} mb-1`}>
                            Article section · flat / debug
                          </p>
                          <div className="space-y-0.5">
                            <div
                              className="space-y-1"
                              title={
                                fh.fullTitleTooltip || fh.fullOfficialInstrumentTitle
                              }
                            >
                              <div className="hidden sm:flex sm:flex-col sm:gap-0.5">
                                <span className="text-[15px] font-semibold leading-snug text-foreground">
                                  {fh.primaryInstrumentLine}
                                </span>
                                <span className="text-[14px] font-medium leading-snug text-foreground/90">
                                  {fh.provisionLine}
                                </span>
                              </div>
                              <span className="text-[14px] font-semibold leading-snug text-foreground sm:hidden">
                                {fh.headlineCompact}
                              </span>
                              <p className="text-[11px] leading-snug text-muted-foreground">
                                {fh.metadataLine}
                              </p>
                              <details className="mt-1 rounded-md border border-dashed border-border/60 bg-muted/[0.08] px-2 py-1">
                                <summary className="cursor-pointer select-none text-[11px] font-medium text-muted-foreground hover:text-foreground">
                                  Full source title
                                </summary>
                                <div className="border-t border-border/40 pb-2 pl-2 pr-3 pt-2 text-[11px] leading-snug">
                                  <p className="whitespace-pre-wrap text-foreground/90">
                                    {fh.fullOfficialInstrumentTitle}
                                  </p>
                                  {fh.representativeCitation.trim() ? (
                                    <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                                      {fh.representativeCitation}
                                    </p>
                                  ) : null}
                                </div>
                              </details>
                            </div>
                          </div>
                          <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-foreground/85">
                            <span className={META_CHIP_CLASS}>
                              {rowCount} row{rowCount === 1 ? "" : "s"} (flat)
                            </span>
                            {scopeBannerHasLinks ? (
                              <span
                                className={META_CHIP_CLASS}
                                title="Primary scopes only (direct + high confidence)"
                              >
                                scope:{" "}
                                {primarySlugs.length > 0 ? (
                                  <>{primarySlugs.join(", ")}</>
                                ) : (
                                  <span className="text-muted-foreground">
                                    ({secondarySlugCount} non-primary)
                                  </span>
                                )}
                              </span>
                            ) : null}
                          </div>
                          {showMultiSpeciesArticleNote ? (
                            <p className="mt-2 max-w-prose text-[11px] leading-snug text-muted-foreground">
                              Article sections may include propositions for several species when no
                              scope filter is active.
                            </p>
                          ) : null}
                        </summary>
                        <div className="space-y-4 border-t border-border/50 px-2 pb-3 pt-3">
                          {(() => {
                            const rowGroups = rows.map((row) => ({ rows: [row] }));
                            const { primary: primaryRowGroups, scopeSecondary: scopeSecondaryRowGroups } =
                              partitionGroupsByScopeSecondary(
                                rowGroups,
                                classificationFilters.collapseScopeRules
                              );
                            const primaryFlatRows = primaryRowGroups.flatMap((g) => g.rows);
                            const scopeSecondaryFlatRows = scopeSecondaryRowGroups.flatMap(
                              (g) => g.rows
                            );

                            const renderFlatRow = (row: UnknownRecord) => {
                            const oa = asRecord(row.original_artifact) ?? {};
                            const pid = String(oa.id ?? "").trim();
                            const txt =
                              typeof oa.proposition_text === "string" ? oa.proposition_text : "";
                            const displayFlat = propositionInformativeLabel(oa);
                            const crossRefFlat = relatedCrossReferenceDisplayLine(oa);
                            const rawStoredFlat =
                              propositionDisplayMode === "raw" &&
                              typeof oa.label === "string" &&
                              oa.label.trim().length > 0
                                ? oa.label.trim()
                                : null;

                            const tr = pid ? traceByPropId.get(pid) : undefined;
                            const evTr = tr ? asRecord(tr.effective_value) : null;
                            const conf =
                              typeof evTr?.confidence === "string" ? evTr.confidence : "—";

                            const rv = String(row.effective_status ?? "").trim();
                            const reviewLabel = rv.toLowerCase() === "generated" ? "generated" : rv;

                            const scopeRows = pid ? (scopeLinkRowsByPropId.get(pid) ?? []) : [];
                            const sid =
                              typeof oa.source_record_id === "string" ? oa.source_record_id : "";
                            const fid =
                              typeof oa.source_fragment_id === "string"
                                ? oa.source_fragment_id
                                : "";
                            const hl =
                              typeof oa.fragment_locator === "string"
                                ? oa.fragment_locator.trim()
                                : "";

                            const jlFlat = jurisdictionForSource(sources, sid);

                            const compRow = pid ? completenessByPropId.get(pid) : undefined;
                            const cStatus =
                              typeof compRow?.status === "string" ? compRow.status : "";
                            const suggStmt =
                              typeof compRow?.suggested_display_statement === "string"
                                ? compRow.suggested_display_statement.trim()
                                : "";
                            const ctxInj =
                              compRow &&
                              compRow.context_injections &&
                              typeof compRow.context_injections === "object"
                                ? (compRow.context_injections as UnknownRecord)
                                : null;

                            const fullPropText = normalizePropositionText(txt);
                            const rawTextForUi = txt;

                            const evidUiFlat = verbatimEvidenceUiFromProposition(oa);
                            const reviewNotesFlat = humanReviewNotesForDisplay(oa);

                            const fragmentSlot = fid ? (
                              <button
                                type="button"
                                className="rounded border border-border/80 px-2 py-0.5 text-[11px] hover:bg-accent/70"
                                onClick={() =>
                                  void openFragmentModal(sid, fid, {
                                    highlightLocator: hl,
                                    contextInjections: ctxInj,
                                  })
                                }
                              >
                                view source fragment
                              </button>
                            ) : (
                              <span className="text-xs text-muted-foreground">
                                No fragment id recorded.
                              </span>
                            );

                            const traceButtonEl = (
                              <button
                                type="button"
                                className="rounded border border-border/80 px-2 py-0.5 text-[11px] hover:bg-accent/70"
                                onClick={() => (pid ? setTraceModalPid(pid) : undefined)}
                              >
                                view extraction trace
                              </button>
                            );

                            const evidenceFlat = (
                              <>
                                {reviewNotesFlat ? (
                                  <p className="mb-2 text-[12px] leading-relaxed text-muted-foreground">
                                    <span className="font-medium text-foreground">Review note: </span>
                                    {reviewNotesFlat}
                                  </p>
                                ) : null}
                                <PropositionEvidenceDetails
                                  rawText={fullPropText || rawTextForUi}
                                  verbatimEvidenceKnown={evidUiFlat.known}
                                  verbatimEvidenceQuote={evidUiFlat.quoteText}
                                  evidenceMismatchWarning={
                                    evidUiFlat.showTraceabilityWarning
                                      ? "Evidence quote could not be matched exactly to source text."
                                      : null
                                  }
                                  fragmentSlot={fragmentSlot}
                                  traceButton={traceButtonEl}
                                />
                              </>
                            );

                            const completenessArtifactIdFlat =
                              (compRow && String(compRow.id ?? "").trim()) || pid;

                            const reviewPanelFlat = pid ? (
                              <PropositionReviewPanel
                                propositionId={pid}
                                completenessArtifactId={completenessArtifactIdFlat}
                                decisions={pipelineReviewDecisions}
                                busyKey={actionBusyKey}
                                disabled={actionBusyKey !== null}
                                recordedFlashAt={
                                  reviewRecordedFlash?.propositionId === pid
                                    ? reviewRecordedFlash.at
                                    : null
                                }
                                onDecision={(artifactType, artifactId, dec) =>
                                  void appendPipelineReviewDecision(
                                    pid,
                                    artifactType,
                                    artifactId,
                                    dec
                                  )
                                }
                              />
                            ) : null;

                            const recordingBusyFlat = Boolean(
                              actionBusyKey && pid && actionBusyKey.startsWith(`${pid}|`)
                            );

                            const flatSourceLines = compactPropositionSourceSummaryLines(
                              [row],
                              sources
                            );

                            return (
                              <Card key={pid || displayFlat}>
                                <CardHeader className="pb-2">
                                  <div className="flex flex-wrap items-start justify-between gap-2">
                                    <div className="min-w-0 space-y-2">
                                      <p className={HIER_SECTION_LABEL}>Proposition group</p>
                                      {crossRefFlat ? (
                                        <p className="text-[11px] font-medium leading-snug text-sky-700/90 dark:text-sky-400/90">
                                          {crossRefFlat}
                                        </p>
                                      ) : null}
                                      <CardTitle className="text-base font-medium leading-snug">
                                        {displayFlat}
                                      </CardTitle>
                                      <div className="rounded-md border border-border/50 bg-muted/[0.12] px-2.5 py-2">
                                        <PropositionClassificationMeta
                                          oa={oa}
                                          compact
                                          showExtractionDebug={propositionDisplayMode === "raw"}
                                        />
                                      </div>
                                      {flatSourceLines.length > 0 ? (
                                        <div className="space-y-0.5 text-[11px] leading-snug text-foreground/88">
                                          {flatSourceLines.map((line, li) => (
                                            <p key={`flat-src-${li}`}>{line}</p>
                                          ))}
                                        </div>
                                      ) : null}
                                      {rawStoredFlat && rawStoredFlat !== displayFlat ? (
                                        <p
                                          className="font-mono text-[10px] leading-snug text-muted-foreground"
                                          title={rawStoredFlat}
                                        >
                                          Stored extraction label ·{" "}
                                          {rawStoredFlat.length > 140
                                            ? `${rawStoredFlat.slice(0, 136)}…`
                                            : rawStoredFlat}
                                        </p>
                                      ) : null}
                                      <div className="space-y-1.5 border-t border-border/45 pt-2">
                                        <p className={HIER_SECTION_LABEL}>Source document</p>
                                        <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-foreground/80">
                                          <PropositionJurisdictionChip
                                            jurisdiction={jlFlat}
                                            sourceId={sid}
                                          />
                                          <span className={META_CHIP_CLASS}>
                                            source id: {sid || "—"}
                                          </span>
                                          <span
                                            className={META_CHIP_CLASS}
                                            title="Pipeline review on extracted proposition text"
                                          >
                                            Raw extraction review: {reviewLabel || "—"}
                                          </span>
                                          <span
                                            className={META_CHIP_CLASS}
                                            title="Effective extraction trace confidence"
                                          >
                                            Extraction confidence: {conf}
                                          </span>
                                          <span
                                            className="flex flex-wrap items-center gap-1.5"
                                            title={COMPLETENESS_TOOLTIP}
                                          >
                                            <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                                              Completeness
                                            </span>
                                            <CompletenessChipBadge
                                              pipelineStatus={cStatus}
                                              noAssessment={!compRow}
                                            />
                                          </span>
                                          <span
                                            className={`${META_CHIP_CLASS} text-muted-foreground`}
                                          >
                                            pid: {pid}
                                          </span>
                                        </div>
                                      </div>
                                    </div>

                                    <div className="flex shrink-0 flex-col items-end gap-1">
                                      <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                                        Raw extraction review
                                      </span>
                                      <div className="flex flex-wrap justify-end gap-1">
                                        <button
                                          type="button"
                                          className="rounded border border-green-900/35 bg-green-900/[0.1] px-2 py-0.5 text-[11px] font-medium hover:bg-green-900/[0.18] disabled:opacity-45"
                                          disabled={actionBusyKey !== null || !pid}
                                          onClick={() =>
                                            void appendPipelineReviewDecision(
                                              pid,
                                              REVIEW_ARTIFACT_PROPOSITION,
                                              pid,
                                              "approved"
                                            )
                                          }
                                        >
                                          approve
                                        </button>
                                        <button
                                          type="button"
                                          className="rounded border border-red-900/35 bg-red-900/[0.09] px-2 py-0.5 text-[11px] font-medium hover:bg-red-900/[0.16] disabled:opacity-45"
                                          disabled={actionBusyKey !== null || !pid}
                                          onClick={() =>
                                            void appendPipelineReviewDecision(
                                              pid,
                                              REVIEW_ARTIFACT_PROPOSITION,
                                              pid,
                                              "rejected"
                                            )
                                          }
                                        >
                                          reject
                                        </button>
                                        <button
                                          type="button"
                                          className="rounded border border-border/70 bg-muted/40 px-2 py-0.5 text-[11px] font-medium hover:bg-muted/65 disabled:opacity-45"
                                          disabled={actionBusyKey !== null || !pid}
                                          onClick={() =>
                                            void appendPipelineReviewDecision(
                                              pid,
                                              REVIEW_ARTIFACT_PROPOSITION,
                                              pid,
                                              "needs_review"
                                            )
                                          }
                                        >
                                          needs_review
                                        </button>
                                      </div>
                                    </div>
                                  </div>
                                </CardHeader>
                                <CardContent className="space-y-2 pt-0 text-sm">
                                  <StructuredPropositionSections
                                    mode={propositionDisplayMode}
                                    text={
                                      propositionDisplayMode === "raw" ? rawTextForUi : fullPropText
                                    }
                                    oa={oa}
                                    sourceTitleById={sourceTitleById}
                                    suggestedStatement={suggStmt}
                                    extractionConfidence={conf === "—" ? undefined : conf}
                                    extractionNeedsReview={extractionNeedsReviewFromArtifacts(oa, tr)}
                                    completenessChipSlot={
                                      <CompletenessChipBadge
                                        pipelineStatus={cStatus}
                                        noAssessment={!compRow}
                                      />
                                    }
                                    scopeSectionSlot={scopeSection(pid, scopeRows, conf)}
                                    evidenceCollapsible={evidenceFlat}
                                  />
                                  {reviewPanelFlat}
                                  {recordingBusyFlat ? (
                                    <p className="text-[11px] text-muted-foreground">
                                      Recording decision…
                                    </p>
                                  ) : null}
                                </CardContent>
                              </Card>
                            );
                            };

                            return (
                              <>
                                {primaryFlatRows.map(renderFlatRow)}
                                {scopeSecondaryFlatRows.length > 0 ? (
                                  <details className="rounded-lg border border-dashed border-border/60 bg-muted/[0.08] px-2 py-2 open:bg-muted/[0.14]">
                                    <summary className="cursor-pointer list-none px-1 py-1.5 text-[12px] font-medium text-muted-foreground marker:content-none [&::-webkit-details-marker]:hidden">
                                      Scope &amp; application ({scopeSecondaryFlatRows.length})
                                    </summary>
                                    <div className="mt-2 space-y-4 border-t border-border/40 pt-3">
                                      {scopeSecondaryFlatRows.map(renderFlatRow)}
                                    </div>
                                  </details>
                                ) : null}
                              </>
                            );
                          })()}
                        </div>
                      </details>
                    );
                  })}
                </div>
              )}
            </>
          ) : (showDuplicatesFlat && effectivePropositions.length === 0) ||
            (!showDuplicatesFlat && groupsTotalGroups === 0 && !groupsLoading) ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Run completed but no propositions were extracted
                </CardTitle>
                <CardDescription>
                  The pipeline finished for this run, but the effective propositions list is empty.
                  Inspect raw artifacts or quality output.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {opsRunLinks ? (
                  <>
                    <a
                      href={opsRunLinks.fragments}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded border border-border/80 bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent/60"
                    >
                      View source fragments (JSON)
                    </a>
                    <a
                      href={opsRunLinks.traces}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded border border-border/80 bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent/60"
                    >
                      View extraction traces (JSON)
                    </a>
                    <a
                      href={opsRunLinks.quality}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded border border-border/80 bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent/60"
                    >
                      View run quality summary (JSON)
                    </a>
                  </>
                ) : null}
              </CardContent>
            </Card>
          ) : (
            <p className="text-sm text-muted-foreground">
              Nothing matches the current filters. Clear filters to see all{" "}
              {showDuplicatesFlat ? effectivePropositions.length : groupsTotalRows} rows.
            </p>
          )}
        </div>
      ) : null}

      {traceModalPid ? (
        <div
          role="presentation"
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/55 p-3 sm:items-center"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) {
              setTraceModalPid(null);
            }
          }}
        >
          <div className="max-h-[min(90vh,40rem)] w-full max-w-3xl overflow-hidden rounded-lg border border-border bg-background shadow-lg">
            <div className="flex items-center justify-between border-b border-border px-3 py-2">
              <p className="text-sm font-medium">Extraction trace (effective)</p>
              <button
                type="button"
                className="rounded border border-border px-2 py-0.5 text-xs"
                onClick={() => setTraceModalPid(null)}
              >
                Close
              </button>
            </div>
            <pre className="max-h-[min(86vh,36rem)] overflow-auto whitespace-pre-wrap p-3 font-mono text-[11px] leading-relaxed">
              {traceModalPayload
                ? JSON.stringify(traceModalPayload, null, 2)
                : "No extraction trace row for this proposition (check export)."}
            </pre>
          </div>
        </div>
      ) : null}

      {fragmentModalOpen ? (
        <div
          role="presentation"
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/55 p-3 sm:items-center"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) {
              closeFragmentModal();
            }
          }}
        >
          <div className="max-h-[min(90vh,40rem)] w-full max-w-3xl overflow-hidden rounded-lg border border-border bg-background shadow-lg">
            <div className="flex items-center justify-between border-b border-border px-3 py-2">
              <p className="text-sm font-medium">
                Source fragment{" "}
                <span className="font-mono text-[11px] text-muted-foreground">
                  {fragmentModalCaption.fragment_id}
                </span>
              </p>
              <button
                type="button"
                className="rounded border border-border px-2 py-0.5 text-xs"
                onClick={closeFragmentModal}
              >
                Close
              </button>
            </div>
            <FragmentSnippetView
              fullText={fragmentText}
              highlightLocator={fragmentHighlightLocator}
              busy={fragmentBusy}
              contextInjections={fragmentModalContextInjections}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function PropositionExplorer(): JSX.Element {
  return (
    <Suspense
      fallback={
        <div className="space-y-4">
          <Card>
            <CardContent className="py-6">
              <p className="text-sm text-muted-foreground">Loading propositions…</p>
            </CardContent>
          </Card>
        </div>
      }
    >
      <PropositionExplorerInner />
    </Suspense>
  );
}
