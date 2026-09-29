"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import Link from "next/link";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

import { EquineCorpusCoveragePanel } from "@/components/equine-corpus-coverage-panel";
import {
  RegistryRunProgressPanel,
  type RegistryRunJobSummary,
} from "@/components/registry-run-progress-panel";
import {
  CONCEPTUAL_FAMILY_HELP,
  classifyFamilyCandidate,
  classificationRegisterEligible,
  describeBlockReasons,
  isConceptualGroupingCandidate,
  primaryBadgeLabel,
  sourceMembershipKey,
  type ClassifiedFamilyCandidate,
  type FamilyCandidateFields,
  type SourceFamilyCandidateDecision,
} from "@/components/source-family-candidate-utils";

type RunSummary = {
  run_id: string;
  workflow_mode?: string;
  proposition_count?: number;
  divergence_assessment_count?: number;
  artifact_count?: number;
  stage_trace_count?: number;
  created_at?: string;
};

type RunDetailPayload = {
  run: Record<string, unknown>;
  manifest: Record<string, unknown>;
  trace_manifest: Record<string, unknown>;
};

type TracePayload = {
  order?: number;
  stage_name?: string;
  storage_uri?: string;
  trace?: Record<string, unknown>;
};

type SourceRecord = {
  id: string;
  title?: string;
  jurisdiction?: string;
  citation?: string;
  review_status?: string;
};

type SourceDetailPayload = {
  partial?: boolean;
  source_record: Record<string, unknown>;
  current_snapshot?: Record<string, unknown> | null;
  source_snapshots?: Record<string, unknown>[];
  source_fragments?: Record<string, unknown>[];
  source_parse_traces?: Record<string, unknown>[];
  source_fetch_attempts?: Record<string, unknown>[];
};

type SnapshotTimelineMetadataDiffEntry = {
  field?: string;
  previous?: unknown;
  current?: unknown;
};

type SnapshotTimelineComparison = {
  has_previous?: boolean;
  baseline_event_id?: string | null;
  baseline_snapshot_id?: string | null;
  text_changed?: boolean;
  metadata_changed?: boolean;
  change_kind?: string;
  metadata_diff?: SnapshotTimelineMetadataDiffEntry[];
  text_diff?: string;
};

type SnapshotTimelineTimepoint = {
  event_id: string;
  position?: number;
  source_record_id?: string;
  snapshot_id?: string;
  version_id?: string;
  content_hash?: string;
  retrieved_at?: string;
  as_of_date?: string;
  provenance?: string;
  authoritative_locator?: string;
  snapshot?: Record<string, unknown>;
  comparison?: SnapshotTimelineComparison;
  origins?: Record<string, unknown>[];
};

type SourceSnapshotTimelinePayload = {
  source_id: string;
  timepoint_count: number;
  timepoints: SnapshotTimelineTimepoint[];
};

type SourceFragmentPayload = {
  source_fragments: Record<string, unknown>[];
};

type ReviewDecisionPayload = {
  review_decisions: Record<string, unknown>[];
};

type RegistryEntry = {
  registry_id: string;
  created_at?: string;
  updated_at?: string;
  reference?: Record<string, unknown>;
  current_state?: Record<string, unknown> | null;
  refresh_history?: Record<string, unknown>[];
};

type RegistryListPayload = {
  sources: RegistryEntry[];
};

type SourceRecordsPayload = {
  source_records?: SourceRecord[];
};

type PropositionRecord = {
  id?: string;
  proposition_key?: string;
  proposition_version_id?: string;
  source_record_id?: string;
  source_snapshot_id?: string;
  observed_in_run_id?: string;
  article_reference?: string;
  fragment_locator?: string;
  legal_subject?: string;
  action?: string;
  proposition_text?: string;
};

type PropositionHistoryObservation = {
  proposition_id?: string;
  proposition_key?: string;
  proposition_version_id?: string;
  source_record_id?: string;
  source_snapshot_id?: string;
  observed_in_run_id?: string;
  observed_at?: string;
  article_reference?: string;
  fragment_locator?: string;
  legal_subject?: string;
  action?: string;
  proposition_text?: string;
  previous_version_signal?: string;
  previous_version_comparison?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};

type PropositionVersionsByRun = {
  observed_in_run_id?: string;
  observed_version_count?: number;
  observed_versions?: PropositionHistoryObservation[];
};

type PropositionVersionsBySnapshot = {
  source_snapshot_id?: string;
  observed_version_count?: number;
  observed_versions?: PropositionHistoryObservation[];
};

type PropositionHistoryPayload = {
  proposition_key: string;
  scope?: string;
  include_runs?: boolean;
  run_ids_scanned?: string[];
  observed_version_count?: number;
  observed_versions?: PropositionHistoryObservation[];
  versions_by_run?: PropositionVersionsByRun[];
  versions_by_snapshot?: PropositionVersionsBySnapshot[];
};

type DivergenceAssessmentRecord = {
  id?: string;
  finding_id?: string;
  proposition_id?: string;
  comparator_proposition_id?: string;
  divergence_type?: string;
  confidence?: string;
  review_status?: string;
  rationale?: string;
  operational_impact?: string;
  source_snapshot_ids?: string[];
};

type DivergenceHistoryObservation = {
  finding_id?: string;
  observation_id?: string;
  version_identity?: string;
  source_record_ids?: string[];
  source_snapshot_ids?: string[];
  observed_in_run_id?: string;
  observed_at?: string;
  divergence_type?: string;
  confidence?: string;
  review_status?: string;
  rationale?: string;
  operational_impact?: string;
  previous_version_signal?: string;
  previous_version_comparison?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};

type DivergenceVersionsByRun = {
  observed_in_run_id?: string;
  observed_version_count?: number;
  observed_versions?: DivergenceHistoryObservation[];
};

type DivergenceVersionsBySnapshot = {
  source_snapshot_id?: string;
  observed_version_count?: number;
  observed_versions?: DivergenceHistoryObservation[];
};

type DivergenceHistoryPayload = {
  finding_id: string;
  scope?: string;
  include_runs?: boolean;
  run_ids_scanned?: string[];
  observed_version_count?: number;
  observed_versions?: DivergenceHistoryObservation[];
  versions_by_run?: DivergenceVersionsByRun[];
  versions_by_snapshot?: DivergenceVersionsBySnapshot[];
};

type SourceSearchCandidate = {
  title: string;
  citation: string;
  source_identifier: string;
  authority_source_id: string;
  jurisdiction: string;
  authority: string;
  canonical_source_url: string;
  provenance: string;
};

type SourceFamilyCandidateRow = FamilyCandidateFields;

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_LAW_PROPOSITION_EXTRACTOR_API_BASE_URL ?? "http://127.0.0.1:8010"
).replace(/\/+$/, "");

const META_CHIP_CLASS =
  "rounded border border-border/70 bg-muted/80 px-2 py-0.5 font-mono text-[11px] leading-5 text-foreground/85";

function toText(value: unknown, fallback = "—"): string {
  if (typeof value === "string") {
    return value.trim() || fallback;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

function splitCommaValues(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

/** Comma-separated focus scopes default when topic/tags look like equine corpus work. */
function equineFocusScopesDefaultText(topicName: string, subjectTagsComma: string): string {
  const blob = `${topicName} ${subjectTagsComma}`.toLowerCase();
  if (/\b(equine|equidae|equid|horse)\b/.test(blob)) {
    return "equine, equidae, equid, horse";
  }
  return "";
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function asArrayRecords(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => asRecord(item))
    .filter((item): item is Record<string, unknown> => item !== null);
}

function formatDateTime(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) {
    return "—";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function normalizeLower(value: unknown): string {
  return toText(value, "").toLowerCase();
}

function matchesQuery(value: unknown, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  return normalizeLower(value).includes(needle);
}

function sourceIdFromAuthoritySourceId(authoritySourceId: string): string {
  const normalized = authoritySourceId
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `src-${normalized || "source"}`;
}

function divergenceFindingId(assessment: DivergenceAssessmentRecord): string {
  const explicitFindingId = toText(assessment.finding_id, "").trim();
  if (explicitFindingId) {
    return explicitFindingId;
  }
  const propositionId = toText(assessment.proposition_id, "").trim();
  const comparatorPropositionId = toText(assessment.comparator_proposition_id, "").trim();
  if (propositionId && comparatorPropositionId) {
    return `finding-${propositionId}-${comparatorPropositionId}`;
  }
  return "";
}

function runSourceRecordIds(runRecord: Record<string, unknown>): unknown[] {
  const canonical = runRecord.source_record_ids;
  if (Array.isArray(canonical)) {
    return canonical;
  }
  // Deprecated migration shim: read legacy run payloads exported before source_record_ids rename.
  const legacy = runRecord.source_document_ids;
  if (Array.isArray(legacy)) {
    return legacy;
  }
  return [];
}

function latestRefreshedAt(entry: RegistryEntry): string {
  const currentState = asRecord(entry.current_state) ?? {};
  if (typeof currentState.refreshed_at === "string" && currentState.refreshed_at.trim()) {
    return currentState.refreshed_at;
  }
  const history = Array.isArray(entry.refresh_history) ? entry.refresh_history : [];
  const latest = history[history.length - 1];
  const latestRecord = asRecord(latest) ?? {};
  return typeof latestRecord.refreshed_at === "string" ? latestRecord.refreshed_at : "";
}

function FieldRow({ label, value }: { label: string; value: unknown }): JSX.Element {
  return (
    <div className="rounded border border-border/70 bg-muted/20 p-2">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 break-all font-mono text-[12px]">{toText(value)}</p>
    </div>
  );
}

function JsonBlock({ payload }: { payload: unknown }): JSX.Element {
  return (
    <pre className="max-h-80 overflow-auto rounded-md border border-border/80 bg-muted/20 p-2 text-[11px] leading-5">
      {JSON.stringify(payload, null, 2)}
    </pre>
  );
}

function AuditPanelCollapsible({
  title,
  description,
  className = "",
  children,
}: {
  title: string;
  description: ReactNode;
  className?: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <details
      open={false}
      className={`rounded-lg border border-border/75 bg-card text-card-foreground shadow-sm ${className}`.trim()}
    >
      <summary className="cursor-pointer list-none px-6 py-4 outline-none marker:content-none hover:bg-muted/20 [&::-webkit-details-marker]:hidden">
        <div className="flex flex-col gap-1">
          <p className="text-lg font-semibold leading-none tracking-tight">{title}</p>
          <p className="text-sm text-muted-foreground">{description}</p>
          <p className="mt-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground/90">
            Audit detail · click to expand
          </p>
        </div>
      </summary>
      <div className="space-y-2 border-t border-border/60 px-6 pb-6 pt-4">{children}</div>
    </details>
  );
}

const OPERATIONS_WORKFLOW_STEPS = [
  "Find source",
  "Register source",
  "Discover related sources",
  "Select sources & analysis scope",
  "Run analysis (proposition dataset)",
  "Compare datasets / review",
] as const;

/** Shared admin clear controls — token-aligned focus/hover for WCAG-friendly contrast. */
const DEV_CLEAR_CONFIRM_INPUT_CLASS =
  "w-full rounded-md border border-input bg-background px-2 py-1.5 font-mono text-[12px] text-foreground placeholder:text-muted-foreground shadow-sm transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/90 focus-visible:ring-offset-2 focus-visible:ring-offset-background";

const DEV_CLEAR_DRY_RUN_BUTTON_CLASS =
  "inline-flex items-center justify-center rounded-md border border-input bg-background px-2.5 py-1.5 text-[11px] font-medium text-foreground shadow-sm transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background active:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-background";

function DevClearSuccessMessage({ message }: { message: string }): JSX.Element {
  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-md border border-emerald-700/50 bg-emerald-600/[0.12] px-2.5 py-2 text-[11px] font-semibold leading-snug text-emerald-950 shadow-sm dark:border-emerald-400/45 dark:bg-emerald-500/[0.16] dark:text-emerald-50"
    >
      <svg
        className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-800 dark:text-emerald-300"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden
      >
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
          clipRule="evenodd"
        />
      </svg>
      <span className="min-w-0 flex-1">{message}</span>
    </div>
  );
}

export function OperationsInspector(): JSX.Element {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [isRunsLoading, setIsRunsLoading] = useState(true);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const [runDetail, setRunDetail] = useState<RunDetailPayload | null>(null);
  const [runDetailError, setRunDetailError] = useState<string | null>(null);
  const [isRunDetailLoading, setIsRunDetailLoading] = useState(false);

  const [traces, setTraces] = useState<TracePayload[]>([]);
  const [tracesError, setTracesError] = useState<string | null>(null);
  const [isTracesLoading, setIsTracesLoading] = useState(false);

  const [reviewDecisions, setReviewDecisions] = useState<Record<string, unknown>[]>([]);
  const [reviewDecisionsError, setReviewDecisionsError] = useState<string | null>(null);
  const [isReviewDecisionsLoading, setIsReviewDecisionsLoading] = useState(false);

  const [sourceRecords, setSourceRecords] = useState<SourceRecord[]>([]);
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [isSourcesLoading, setIsSourcesLoading] = useState(false);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);

  const [sourceDetail, setSourceDetail] = useState<SourceDetailPayload | null>(null);
  const [sourceDetailError, setSourceDetailError] = useState<string | null>(null);
  const [sourceDetailSummaryFallback, setSourceDetailSummaryFallback] = useState(false);
  const [isSourceDetailLoading, setIsSourceDetailLoading] = useState(false);

  const [sourceSnapshotTimeline, setSourceSnapshotTimeline] = useState<SnapshotTimelineTimepoint[]>(
    []
  );
  const [sourceSnapshotTimelineError, setSourceSnapshotTimelineError] = useState<string | null>(
    null
  );
  const [isSourceSnapshotTimelineLoading, setIsSourceSnapshotTimelineLoading] = useState(false);
  const [selectedSnapshotEventId, setSelectedSnapshotEventId] = useState<string | null>(null);
  const [useAggregatedSourceHistory, setUseAggregatedSourceHistory] = useState(false);

  const [sourceFragments, setSourceFragments] = useState<Record<string, unknown>[]>([]);
  const [sourceFragmentsError, setSourceFragmentsError] = useState<string | null>(null);
  const [isSourceFragmentsLoading, setIsSourceFragmentsLoading] = useState(false);

  const [runPropositions, setRunPropositions] = useState<PropositionRecord[]>([]);
  const [runPropositionsError, setRunPropositionsError] = useState<string | null>(null);
  const [isRunPropositionsLoading, setIsRunPropositionsLoading] = useState(false);
  const [selectedPropositionKey, setSelectedPropositionKey] = useState("");
  const [propositionSearch, setPropositionSearch] = useState("");
  const [propositionVersionSearch, setPropositionVersionSearch] = useState("");
  const [propositionHistory, setPropositionHistory] = useState<PropositionHistoryPayload | null>(
    null
  );
  const [propositionHistoryError, setPropositionHistoryError] = useState<string | null>(null);
  const [isPropositionHistoryLoading, setIsPropositionHistoryLoading] = useState(false);

  const [runDivergenceAssessments, setRunDivergenceAssessments] = useState<
    DivergenceAssessmentRecord[]
  >([]);
  const [runDivergenceAssessmentsError, setRunDivergenceAssessmentsError] = useState<string | null>(
    null
  );
  const [isRunDivergenceAssessmentsLoading, setIsRunDivergenceAssessmentsLoading] = useState(false);
  const [selectedFindingId, setSelectedFindingId] = useState("");
  const [divergenceSearch, setDivergenceSearch] = useState("");
  const [divergenceVersionSearch, setDivergenceVersionSearch] = useState("");
  const [divergenceHistory, setDivergenceHistory] = useState<DivergenceHistoryPayload | null>(null);
  const [divergenceHistoryError, setDivergenceHistoryError] = useState<string | null>(null);
  const [isDivergenceHistoryLoading, setIsDivergenceHistoryLoading] = useState(false);

  const [runSearch, setRunSearch] = useState("");
  const [traceSearch, setTraceSearch] = useState("");
  const [decisionSearch, setDecisionSearch] = useState("");
  const [sourceSearch, setSourceSearch] = useState("");
  const [snapshotSearch, setSnapshotSearch] = useState("");
  const [fragmentSearch, setFragmentSearch] = useState("");
  const [registrySearch, setRegistrySearch] = useState("");

  const [registryEntries, setRegistryEntries] = useState<RegistryEntry[]>([]);
  const [registryError, setRegistryError] = useState<string | null>(null);
  const [isRegistryLoading, setIsRegistryLoading] = useState(true);
  const [selectedRegistryId, setSelectedRegistryId] = useState<string | null>(null);
  const [selectedRegistryIdsForRun, setSelectedRegistryIdsForRun] = useState<string[]>([]);
  const [sourceRunUsageCountBySourceId, setSourceRunUsageCountBySourceId] = useState<
    Record<string, number>
  >({});
  const [isRunUsageLoading, setIsRunUsageLoading] = useState(false);
  const [runUsageError, setRunUsageError] = useState<string | null>(null);

  const [registerPayload, setRegisterPayload] = useState(`{
  "authority": "case_file",
  "authority_source_id": "eu-source-001",
  "id": "src-eu-001",
  "title": "Example EU instrument",
  "jurisdiction": "EU",
  "citation": "EU-EXAMPLE-001",
  "kind": "regulation",
  "text": "Article 10. Operators must maintain a movement register before dispatch.",
  "authoritative_locator": "article:10",
  "version_id": "v1"
}`);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [registerSuccess, setRegisterSuccess] = useState<string | null>(null);
  const [isRegistering, setIsRegistering] = useState(false);
  const [sourceSearchQuery, setSourceSearchQuery] = useState("2016/429");
  const [sourceSearchResults, setSourceSearchResults] = useState<SourceSearchCandidate[]>([]);
  const [sourceSearchError, setSourceSearchError] = useState<string | null>(null);
  const [sourceSearchSuccess, setSourceSearchSuccess] = useState<string | null>(null);
  const [isSourceSearchLoading, setIsSourceSearchLoading] = useState(false);
  const [hasSourceSearchAttempted, setHasSourceSearchAttempted] = useState(false);
  const [addingCandidateId, setAddingCandidateId] = useState<string | null>(null);
  const [optimisticRegisteredResultKeys, setOptimisticRegisteredResultKeys] = useState<Set<string>>(
    new Set()
  );

  const [isRefreshingRegistryEntry, setIsRefreshingRegistryEntry] = useState(false);
  const [registryRefreshError, setRegistryRefreshError] = useState<string | null>(null);
  const [registryRefreshSuccess, setRegistryRefreshSuccess] = useState<string | null>(null);

  const [runFromRegistryTopicName, setRunFromRegistryTopicName] = useState("Registry analysis run");
  const [runFromRegistryClusterName, setRunFromRegistryClusterName] = useState("");
  const [runFromRegistryAnalysisMode, setRunFromRegistryAnalysisMode] = useState("auto");
  const [runFromRegistryAnalysisScope, setRunFromRegistryAnalysisScope] =
    useState("selected_sources");
  const [runFromRegistrySubjectTags, setRunFromRegistrySubjectTags] = useState("");
  const [runFromRegistryQualityRun, setRunFromRegistryQualityRun] = useState(false);
  const [runFromRegistryExtractionMode, setRunFromRegistryExtractionMode] = useState("");
  const [runFromRegistryExtractionExecutionMode, setRunFromRegistryExtractionExecutionMode] =
    useState("");
  const [runFromRegistryExtractionFallback, setRunFromRegistryExtractionFallback] = useState("");
  const [runFromRegistryDivergenceReasoning, setRunFromRegistryDivergenceReasoning] =
    useState("");
  const [runFromRegistryFocusScopesText, setRunFromRegistryFocusScopesText] = useState("");
  const [runFromRegistryMaxPropositions, setRunFromRegistryMaxPropositions] = useState("");
  const [runFromRegistryError, setRunFromRegistryError] = useState<string | null>(null);
  const [runFromRegistrySuccess, setRunFromRegistrySuccess] = useState<string | null>(null);
  const [isRunningFromRegistry, setIsRunningFromRegistry] = useState(false);
  const [registryRunJobId, setRegistryRunJobId] = useState<string | null>(null);
  const [registryRunJob, setRegistryRunJob] = useState<RegistryRunJobSummary | null>(null);
  const [registryRunJobEvents, setRegistryRunJobEvents] = useState<Record<string, unknown>[]>([]);
  const [registryRunJobPollError, setRegistryRunJobPollError] = useState<string | null>(null);

  const [devClearRunsPhrase, setDevClearRunsPhrase] = useState("");
  const [devClearAllPhrase, setDevClearAllPhrase] = useState("");
  const [devClearRunsStatus, setDevClearRunsStatus] = useState<string | null>(null);
  const [devClearAllStatus, setDevClearAllStatus] = useState<string | null>(null);
  const [devClearError, setDevClearError] = useState<string | null>(null);
  const [isDevClearRunsDryRunning, setIsDevClearRunsDryRunning] = useState(false);
  const [isDevClearRunsDestructiveRunning, setIsDevClearRunsDestructiveRunning] = useState(false);
  const [isDevClearAllDryRunning, setIsDevClearAllDryRunning] = useState(false);
  const [isDevClearAllDestructiveRunning, setIsDevClearAllDestructiveRunning] = useState(false);

  const [familyDiscovery, setFamilyDiscovery] = useState<{
    registry_id: string;
    target_authority_source_id?: string;
    candidates: SourceFamilyCandidateRow[];
  } | null>(null);
  const [contextFamilyCandidateIds, setContextFamilyCandidateIds] = useState<string[]>([]);
  const [registerFamilyCandidateIds, setRegisterFamilyCandidateIds] = useState<string[]>([]);
  const [familyCandidatesRegisteredSession, setFamilyCandidatesRegisteredSession] = useState<
    Record<string, string>
  >({});
  const [isFamilyDiscoveryLoading, setIsFamilyDiscoveryLoading] = useState(false);
  const [familyDiscoveryError, setFamilyDiscoveryError] = useState<string | null>(null);
  const [isRegisteringFamilyCandidates, setIsRegisteringFamilyCandidates] = useState(false);
  const [familyRegisterMessage, setFamilyRegisterMessage] = useState<string | null>(null);
  const [familyRegisterError, setFamilyRegisterError] = useState<string | null>(null);
  const [familyCandidateDecisions, setFamilyCandidateDecisions] = useState<
    Record<string, SourceFamilyCandidateDecision>
  >({});

  const [equineCorpusCoverage, setEquineCorpusCoverage] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [equineCorpusCoverageError, setEquineCorpusCoverageError] = useState<string | null>(null);

  const [equineCorpusRunJobId, setEquineCorpusRunJobId] = useState<string | null>(null);
  const [equineCorpusRunJob, setEquineCorpusRunJob] = useState<RegistryRunJobSummary | null>(null);
  const [equineCorpusRunJobEvents, setEquineCorpusRunJobEvents] = useState<
    Record<string, unknown>[]
  >([]);
  const [equineCorpusRunJobPollError, setEquineCorpusRunJobPollError] = useState<string | null>(null);
  const [equineCorpusRunError, setEquineCorpusRunError] = useState<string | null>(null);
  const [equineCorpusRunSuccess, setEquineCorpusRunSuccess] = useState<string | null>(null);
  const [isRunningEquineCorpus, setIsRunningEquineCorpus] = useState(false);
  const [equineCorpusExtractionExecutionMode, setEquineCorpusExtractionExecutionMode] =
    useState("interactive");

  const runDetailEndpoint = selectedRunId
    ? `${API_BASE_URL}/ops/runs/${encodeURIComponent(selectedRunId)}`
    : null;
  const tracesEndpoint = selectedRunId
    ? `${API_BASE_URL}/ops/runs/${encodeURIComponent(selectedRunId)}/traces`
    : null;
  const reviewDecisionsEndpoint = selectedRunId
    ? `${API_BASE_URL}/ops/runs/${encodeURIComponent(selectedRunId)}/review-decisions`
    : null;
  const sourcesEndpoint = selectedRunId
    ? `${API_BASE_URL}/ops/sources?run_id=${encodeURIComponent(selectedRunId)}`
    : null;
  const propositionsEndpoint = selectedRunId
    ? `${API_BASE_URL}/ops/propositions?run_id=${encodeURIComponent(selectedRunId)}`
    : null;
  const propositionHistoryEndpoint = selectedPropositionKey.trim()
    ? `${API_BASE_URL}/ops/propositions/${encodeURIComponent(
        selectedPropositionKey.trim()
      )}/history?include_runs=true`
    : null;
  const divergenceAssessmentsEndpoint = selectedRunId
    ? `${API_BASE_URL}/ops/divergence-assessments?run_id=${encodeURIComponent(selectedRunId)}`
    : null;
  const divergenceHistoryEndpoint = selectedFindingId.trim()
    ? `${API_BASE_URL}/ops/divergence-findings/${encodeURIComponent(selectedFindingId.trim())}/history?include_runs=true`
    : null;

  const sourceDetailEndpoint = useMemo(() => {
    if (!selectedRunId || !selectedSourceId) {
      return null;
    }
    const sourceId = encodeURIComponent(selectedSourceId);
    const runId = encodeURIComponent(selectedRunId);
    return `${API_BASE_URL}/ops/sources/${sourceId}?run_id=${runId}`;
  }, [selectedRunId, selectedSourceId]);

  const sourceFragmentsEndpoint = useMemo(() => {
    if (!selectedRunId || !selectedSourceId) {
      return null;
    }
    const sourceId = encodeURIComponent(selectedSourceId);
    const runId = encodeURIComponent(selectedRunId);
    return `${API_BASE_URL}/ops/sources/${sourceId}/fragments?run_id=${runId}`;
  }, [selectedRunId, selectedSourceId]);

  const sourceTimelineEndpoint = useMemo(() => {
    if (!selectedSourceId) {
      return null;
    }
    const sourceId = encodeURIComponent(selectedSourceId);
    if (useAggregatedSourceHistory) {
      return `${API_BASE_URL}/ops/sources/${sourceId}/history?include_runs=true&include_registry=true`;
    }
    if (!selectedRunId) {
      return null;
    }
    const runId = encodeURIComponent(selectedRunId);
    return `${API_BASE_URL}/ops/sources/${sourceId}/timeline?run_id=${runId}`;
  }, [selectedRunId, selectedSourceId, useAggregatedSourceHistory]);

  const loadRuns = async (signal: AbortSignal): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/ops/runs`, {
      signal,
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`Request failed (${response.status})`);
    }
    const payload = (await response.json()) as { runs?: RunSummary[] };
    const list = Array.isArray(payload.runs) ? payload.runs : [];
    setRuns(list);
    setSelectedRunId((current) => current ?? list[0]?.run_id ?? null);
  };

  const loadRegistryEntries = async (signal: AbortSignal): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/ops/source-registry`, {
      signal,
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`Request failed (${response.status})`);
    }
    const payload = (await response.json()) as RegistryListPayload;
    const entries = Array.isArray(payload.sources) ? payload.sources : [];
    setRegistryEntries(entries);
    setSelectedRegistryId((current) => {
      if (current && entries.some((entry) => entry.registry_id === current)) {
        return current;
      }
      return entries[0]?.registry_id ?? null;
    });
    setSelectedRegistryIdsForRun((current) => {
      const available = new Set(entries.map((entry) => entry.registry_id));
      const sanitized = current.filter((registryId) => available.has(registryId));
      if (sanitized.length > 0) {
        return sanitized;
      }
      return entries.slice(0, 2).map((item) => item.registry_id);
    });
  };

  const refreshEquineCorpusCoverage = useCallback(async (signal?: AbortSignal): Promise<void> => {
    try {
      const response = await fetch(`${API_BASE_URL}/ops/corpus-coverage/equine`, {
        signal,
        headers: { Accept: "application/json" },
      });
      if (response.status === 404) {
        setEquineCorpusCoverage(null);
        setEquineCorpusCoverageError(null);
        return;
      }
      if (!response.ok) {
        throw new Error(`Request failed (${response.status})`);
      }
      const payload = (await response.json()) as Record<string, unknown>;
      setEquineCorpusCoverage(payload);
      setEquineCorpusCoverageError(null);
    } catch (error) {
      if (signal?.aborted) {
        return;
      }
      setEquineCorpusCoverage(null);
      setEquineCorpusCoverageError(
        error instanceof Error ? error.message : "Unknown fetch error"
      );
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    const loadRunsEffect = async () => {
      setIsRunsLoading(true);
      setRunsError(null);
      try {
        await loadRuns(controller.signal);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setRunsError(error instanceof Error ? error.message : "Unknown fetch error");
      } finally {
        if (!controller.signal.aborted) {
          setIsRunsLoading(false);
        }
      }
    };

    void loadRunsEffect();

    return () => {
      controller.abort();
    };
  }, []);

  useEffect(() => {
    if (!registryRunJobId) {
      return undefined;
    }
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | undefined;

    const refreshRunList = async (): Promise<void> => {
      const response = await fetch(`${API_BASE_URL}/ops/runs`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        return;
      }
      const payload = (await response.json()) as { runs?: RunSummary[] };
      const list = Array.isArray(payload.runs) ? payload.runs : [];
      setRuns(list);
    };

    const tick = async (): Promise<void> => {
      try {
        const [jobRes, evRes] = await Promise.all([
          fetch(`${API_BASE_URL}/ops/run-jobs/${encodeURIComponent(registryRunJobId)}`, {
            headers: { Accept: "application/json" },
          }),
          fetch(`${API_BASE_URL}/ops/run-jobs/${encodeURIComponent(registryRunJobId)}/events`, {
            headers: { Accept: "application/json" },
          }),
        ]);
        if (!jobRes.ok || !evRes.ok) {
          throw new Error(`poll failed (${jobRes.status} / ${evRes.status})`);
        }
        if (cancelled) {
          return;
        }
        setRegistryRunJobPollError(null);
        const jobPayload = (await jobRes.json()) as { job?: RegistryRunJobSummary };
        const evPayload = (await evRes.json()) as { events?: unknown[] };
        const nextJob = jobPayload.job ?? null;
        setRegistryRunJob(nextJob);
        const rawEv = evPayload.events;
        setRegistryRunJobEvents(Array.isArray(rawEv) ? (rawEv as Record<string, unknown>[]) : []);
        const st = String(nextJob?.status || "").toLowerCase();
        if (st === "pass" || st === "warning" || st === "fail" || st === "cancelled") {
          if (intervalId) {
            clearInterval(intervalId);
            intervalId = undefined;
          }
          await refreshRunList();
          const rid = nextJob?.run_id;
          if (rid) {
            setSelectedRunId(String(rid));
            setRunSearch(String(rid));
            setTraceSearch("");
            setSourceSearch("");
            setDecisionSearch("");
          }
          if (st === "fail") {
            setRunFromRegistryError("Run job failed — see progress panel for details.");
            setRunFromRegistrySuccess(null);
          } else {
            setRunFromRegistryError(null);
            setRunFromRegistrySuccess(
              rid ? `Run ${String(rid)} completed.` : "Run completed."
            );
          }
        }
      } catch (error) {
        if (!cancelled) {
          setRegistryRunJobPollError(
            error instanceof Error ? error.message : "Unknown poll error"
          );
        }
      }
    };

    void tick();
    intervalId = setInterval(() => void tick(), 1500);
    return () => {
      cancelled = true;
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [registryRunJobId]);

  useEffect(() => {
    const controller = new AbortController();
    void refreshEquineCorpusCoverage(controller.signal);
    return () => {
      controller.abort();
    };
  }, [refreshEquineCorpusCoverage]);

  useEffect(() => {
    if (!equineCorpusRunJobId) {
      return undefined;
    }
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | undefined;

    const refreshRunList = async (): Promise<void> => {
      const response = await fetch(`${API_BASE_URL}/ops/runs`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        return;
      }
      const payload = (await response.json()) as { runs?: RunSummary[] };
      const list = Array.isArray(payload.runs) ? payload.runs : [];
      setRuns(list);
    };

    const tick = async (): Promise<void> => {
      try {
        const [jobRes, evRes] = await Promise.all([
          fetch(`${API_BASE_URL}/ops/run-jobs/${encodeURIComponent(equineCorpusRunJobId)}`, {
            headers: { Accept: "application/json" },
          }),
          fetch(`${API_BASE_URL}/ops/run-jobs/${encodeURIComponent(equineCorpusRunJobId)}/events`, {
            headers: { Accept: "application/json" },
          }),
        ]);
        if (!jobRes.ok || !evRes.ok) {
          throw new Error(`poll failed (${jobRes.status} / ${evRes.status})`);
        }
        if (cancelled) {
          return;
        }
        setEquineCorpusRunJobPollError(null);
        const jobPayload = (await jobRes.json()) as { job?: RegistryRunJobSummary };
        const evPayload = (await evRes.json()) as { events?: unknown[] };
        const nextJob = jobPayload.job ?? null;
        setEquineCorpusRunJob(nextJob);
        const rawEv = evPayload.events;
        setEquineCorpusRunJobEvents(Array.isArray(rawEv) ? (rawEv as Record<string, unknown>[]) : []);
        const st = String(nextJob?.status || "").toLowerCase();
        if (st === "pass" || st === "warning" || st === "fail" || st === "cancelled") {
          if (intervalId) {
            clearInterval(intervalId);
            intervalId = undefined;
          }
          await refreshRunList();
          await refreshEquineCorpusCoverage(undefined);
          const rid = nextJob?.run_id;
          if (rid) {
            setSelectedRunId(String(rid));
            setRunSearch(String(rid));
            setTraceSearch("");
            setSourceSearch("");
            setDecisionSearch("");
          }
          if (st === "fail") {
            setEquineCorpusRunError("Equine corpus job failed — see progress for details.");
            setEquineCorpusRunSuccess(null);
          } else {
            setEquineCorpusRunError(null);
            setEquineCorpusRunSuccess(
              rid ? `Corpus run ${String(rid)} completed.` : "Corpus run completed.",
            );
          }
        }
      } catch (error) {
        if (!cancelled) {
          setEquineCorpusRunJobPollError(
            error instanceof Error ? error.message : "Unknown poll error",
          );
        }
      }
    };

    void tick();
    intervalId = setInterval(() => void tick(), 1500);
    return () => {
      cancelled = true;
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [equineCorpusRunJobId, refreshEquineCorpusCoverage]);

  useEffect(() => {
    setFamilyDiscovery(null);
    setContextFamilyCandidateIds([]);
    setRegisterFamilyCandidateIds([]);
    setFamilyCandidatesRegisteredSession({});
    setFamilyDiscoveryError(null);
    setFamilyRegisterMessage(null);
    setFamilyRegisterError(null);
  }, [selectedRegistryId]);

  useEffect(() => {
    const controller = new AbortController();
    if (runs.length === 0) {
      setSourceRunUsageCountBySourceId({});
      setRunUsageError(null);
      setIsRunUsageLoading(false);
      return () => controller.abort();
    }

    const loadRunUsage = async () => {
      setIsRunUsageLoading(true);
      setRunUsageError(null);
      try {
        const runSourceLists = await Promise.all(
          runs.map(async (run) => {
            const response = await fetch(
              `${API_BASE_URL}/ops/sources?run_id=${encodeURIComponent(run.run_id)}`,
              {
                signal: controller.signal,
                headers: { Accept: "application/json" },
              }
            );
            if (!response.ok) {
              throw new Error(`run ${run.run_id} (${response.status})`);
            }
            const payload = (await response.json()) as SourceRecordsPayload;
            const records = Array.isArray(payload.source_records) ? payload.source_records : [];
            return {
              runId: run.run_id,
              sourceIds: records
                .map((record) => toText(record.id, ""))
                .filter((id) => id.length > 0),
            };
          })
        );

        const sourceToRunIds = new Map<string, Set<string>>();
        for (const runSourceList of runSourceLists) {
          for (const sourceId of runSourceList.sourceIds) {
            const knownRunIds = sourceToRunIds.get(sourceId) ?? new Set<string>();
            knownRunIds.add(runSourceList.runId);
            sourceToRunIds.set(sourceId, knownRunIds);
          }
        }

        const usageCountBySourceId: Record<string, number> = {};
        sourceToRunIds.forEach((runIds, sourceId) => {
          usageCountBySourceId[sourceId] = runIds.size;
        });
        setSourceRunUsageCountBySourceId(usageCountBySourceId);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setSourceRunUsageCountBySourceId({});
        setRunUsageError(
          error instanceof Error ? error.message : "Unknown source usage fetch error"
        );
      } finally {
        if (!controller.signal.aborted) {
          setIsRunUsageLoading(false);
        }
      }
    };

    void loadRunUsage();

    return () => {
      controller.abort();
    };
  }, [runs]);

  useEffect(() => {
    const controller = new AbortController();

    const loadRegistry = async () => {
      setIsRegistryLoading(true);
      setRegistryError(null);
      try {
        await loadRegistryEntries(controller.signal);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setRegistryError(error instanceof Error ? error.message : "Unknown fetch error");
      } finally {
        if (!controller.signal.aborted) {
          setIsRegistryLoading(false);
        }
      }
    };

    void loadRegistry();

    return () => {
      controller.abort();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    if (!runDetailEndpoint) {
      setRunDetail(null);
      return () => controller.abort();
    }

    const loadRunDetail = async () => {
      setIsRunDetailLoading(true);
      setRunDetailError(null);
      try {
        const response = await fetch(runDetailEndpoint, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Request failed (${response.status})`);
        }
        setRunDetail((await response.json()) as RunDetailPayload);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setRunDetailError(error instanceof Error ? error.message : "Unknown fetch error");
      } finally {
        if (!controller.signal.aborted) {
          setIsRunDetailLoading(false);
        }
      }
    };

    void loadRunDetail();

    return () => {
      controller.abort();
    };
  }, [runDetailEndpoint]);

  useEffect(() => {
    const controller = new AbortController();
    if (!tracesEndpoint) {
      setTraces([]);
      return () => controller.abort();
    }

    const loadTraces = async () => {
      setIsTracesLoading(true);
      setTracesError(null);
      try {
        const response = await fetch(tracesEndpoint, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Request failed (${response.status})`);
        }
        const payload = (await response.json()) as { traces?: TracePayload[] };
        setTraces(Array.isArray(payload.traces) ? payload.traces : []);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setTracesError(error instanceof Error ? error.message : "Unknown fetch error");
      } finally {
        if (!controller.signal.aborted) {
          setIsTracesLoading(false);
        }
      }
    };

    void loadTraces();

    return () => {
      controller.abort();
    };
  }, [tracesEndpoint]);

  useEffect(() => {
    const controller = new AbortController();
    if (!reviewDecisionsEndpoint) {
      setReviewDecisions([]);
      return () => controller.abort();
    }

    const loadReviewDecisions = async () => {
      setIsReviewDecisionsLoading(true);
      setReviewDecisionsError(null);
      try {
        const response = await fetch(reviewDecisionsEndpoint, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Request failed (${response.status})`);
        }
        const payload = (await response.json()) as ReviewDecisionPayload;
        setReviewDecisions(Array.isArray(payload.review_decisions) ? payload.review_decisions : []);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setReviewDecisionsError(error instanceof Error ? error.message : "Unknown fetch error");
      } finally {
        if (!controller.signal.aborted) {
          setIsReviewDecisionsLoading(false);
        }
      }
    };

    void loadReviewDecisions();

    return () => {
      controller.abort();
    };
  }, [reviewDecisionsEndpoint]);

  useEffect(() => {
    const controller = new AbortController();
    if (!propositionsEndpoint) {
      setRunPropositions([]);
      setSelectedPropositionKey("");
      return () => controller.abort();
    }

    const loadPropositions = async () => {
      setIsRunPropositionsLoading(true);
      setRunPropositionsError(null);
      try {
        const response = await fetch(propositionsEndpoint, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Request failed (${response.status})`);
        }
        const payload = (await response.json()) as { propositions?: PropositionRecord[] };
        const propositions = Array.isArray(payload.propositions) ? payload.propositions : [];
        setRunPropositions(propositions);
        setSelectedPropositionKey((current) => {
          const trimmedCurrent = current.trim();
          if (
            trimmedCurrent &&
            propositions.some((item) => toText(item.proposition_key, "").trim() === trimmedCurrent)
          ) {
            return trimmedCurrent;
          }
          return toText(propositions[0]?.proposition_key, "");
        });
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setRunPropositions([]);
        setSelectedPropositionKey("");
        setRunPropositionsError(error instanceof Error ? error.message : "Unknown fetch error");
      } finally {
        if (!controller.signal.aborted) {
          setIsRunPropositionsLoading(false);
        }
      }
    };

    void loadPropositions();

    return () => {
      controller.abort();
    };
  }, [propositionsEndpoint]);

  useEffect(() => {
    const controller = new AbortController();
    if (!propositionHistoryEndpoint) {
      setPropositionHistory(null);
      setPropositionHistoryError(null);
      setIsPropositionHistoryLoading(false);
      return () => controller.abort();
    }

    const loadPropositionHistory = async () => {
      setIsPropositionHistoryLoading(true);
      setPropositionHistoryError(null);
      try {
        const response = await fetch(propositionHistoryEndpoint, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Request failed (${response.status})`);
        }
        setPropositionHistory((await response.json()) as PropositionHistoryPayload);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setPropositionHistory(null);
        setPropositionHistoryError(error instanceof Error ? error.message : "Unknown fetch error");
      } finally {
        if (!controller.signal.aborted) {
          setIsPropositionHistoryLoading(false);
        }
      }
    };

    void loadPropositionHistory();

    return () => {
      controller.abort();
    };
  }, [propositionHistoryEndpoint]);

  useEffect(() => {
    const controller = new AbortController();
    if (!divergenceAssessmentsEndpoint) {
      setRunDivergenceAssessments([]);
      setSelectedFindingId("");
      return () => controller.abort();
    }

    const loadDivergenceAssessments = async () => {
      setIsRunDivergenceAssessmentsLoading(true);
      setRunDivergenceAssessmentsError(null);
      try {
        const response = await fetch(divergenceAssessmentsEndpoint, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Request failed (${response.status})`);
        }
        const payload = (await response.json()) as {
          divergence_assessments?: DivergenceAssessmentRecord[];
        };
        const assessments = Array.isArray(payload.divergence_assessments)
          ? payload.divergence_assessments
          : [];
        setRunDivergenceAssessments(assessments);
        setSelectedFindingId((current) => {
          const trimmedCurrent = current.trim();
          if (
            trimmedCurrent &&
            assessments.some((item) => divergenceFindingId(item) === trimmedCurrent)
          ) {
            return trimmedCurrent;
          }
          return assessments[0] ? divergenceFindingId(assessments[0]) : "";
        });
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setRunDivergenceAssessments([]);
        setSelectedFindingId("");
        setRunDivergenceAssessmentsError(
          error instanceof Error ? error.message : "Unknown fetch error"
        );
      } finally {
        if (!controller.signal.aborted) {
          setIsRunDivergenceAssessmentsLoading(false);
        }
      }
    };

    void loadDivergenceAssessments();

    return () => {
      controller.abort();
    };
  }, [divergenceAssessmentsEndpoint]);

  useEffect(() => {
    const controller = new AbortController();
    if (!divergenceHistoryEndpoint) {
      setDivergenceHistory(null);
      setDivergenceHistoryError(null);
      setIsDivergenceHistoryLoading(false);
      return () => controller.abort();
    }

    const loadDivergenceHistory = async () => {
      setIsDivergenceHistoryLoading(true);
      setDivergenceHistoryError(null);
      try {
        const response = await fetch(divergenceHistoryEndpoint, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Request failed (${response.status})`);
        }
        setDivergenceHistory((await response.json()) as DivergenceHistoryPayload);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setDivergenceHistory(null);
        setDivergenceHistoryError(error instanceof Error ? error.message : "Unknown fetch error");
      } finally {
        if (!controller.signal.aborted) {
          setIsDivergenceHistoryLoading(false);
        }
      }
    };

    void loadDivergenceHistory();

    return () => {
      controller.abort();
    };
  }, [divergenceHistoryEndpoint]);

  useEffect(() => {
    const controller = new AbortController();
    if (!sourcesEndpoint) {
      setSourceRecords([]);
      return () => controller.abort();
    }

    const loadSources = async () => {
      setIsSourcesLoading(true);
      setSourcesError(null);
      try {
        const response = await fetch(sourcesEndpoint, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Request failed (${response.status})`);
        }
        const payload = (await response.json()) as { source_records?: SourceRecord[] };
        const records = Array.isArray(payload.source_records) ? payload.source_records : [];
        setSourceRecords(records);
        setSelectedSourceId((current) => {
          if (current && records.some((row) => row.id === current)) {
            return current;
          }
          return records[0]?.id ?? null;
        });
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setSourcesError(error instanceof Error ? error.message : "Unknown fetch error");
      } finally {
        if (!controller.signal.aborted) {
          setIsSourcesLoading(false);
        }
      }
    };

    void loadSources();

    return () => {
      controller.abort();
    };
  }, [sourcesEndpoint]);

  useEffect(() => {
    const controller = new AbortController();
    if (!sourceDetailEndpoint) {
      setSourceDetail(null);
      setSourceDetailSummaryFallback(false);
      return () => controller.abort();
    }

    const loadSourceDetail = async () => {
      setIsSourceDetailLoading(true);
      setSourceDetailError(null);
      setSourceDetailSummaryFallback(false);
      setSourceDetail(null);
      try {
        const response = await fetch(sourceDetailEndpoint, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          if (response.status === 404) {
            const hasSummary =
              Boolean(selectedSourceId) &&
              sourceRecords.some((row) => row.id === selectedSourceId);
            if (hasSummary) {
              setSourceDetailSummaryFallback(true);
              return;
            }
          }
          throw new Error(`Request failed (${response.status})`);
        }
        setSourceDetail((await response.json()) as SourceDetailPayload);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setSourceDetail(null);
        setSourceDetailError(error instanceof Error ? error.message : "Unknown fetch error");
      } finally {
        if (!controller.signal.aborted) {
          setIsSourceDetailLoading(false);
        }
      }
    };

    void loadSourceDetail();

    return () => {
      controller.abort();
    };
  }, [sourceDetailEndpoint, selectedSourceId, sourceRecords]);

  useEffect(() => {
    const controller = new AbortController();
    if (!sourceFragmentsEndpoint) {
      setSourceFragments([]);
      return () => controller.abort();
    }

    const loadFragments = async () => {
      setIsSourceFragmentsLoading(true);
      setSourceFragmentsError(null);
      setSourceFragments([]);
      try {
        const response = await fetch(sourceFragmentsEndpoint, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Request failed (${response.status})`);
        }
        const payload = (await response.json()) as SourceFragmentPayload;
        setSourceFragments(Array.isArray(payload.source_fragments) ? payload.source_fragments : []);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setSourceFragments([]);
        setSourceFragmentsError(error instanceof Error ? error.message : "Unknown fetch error");
      } finally {
        if (!controller.signal.aborted) {
          setIsSourceFragmentsLoading(false);
        }
      }
    };

    void loadFragments();

    return () => {
      controller.abort();
    };
  }, [sourceFragmentsEndpoint]);

  useEffect(() => {
    const controller = new AbortController();
    if (!sourceTimelineEndpoint) {
      setSourceSnapshotTimeline([]);
      setSelectedSnapshotEventId(null);
      return () => controller.abort();
    }

    const loadTimeline = async () => {
      setIsSourceSnapshotTimelineLoading(true);
      setSourceSnapshotTimelineError(null);
      setSourceSnapshotTimeline([]);
      try {
        const response = await fetch(sourceTimelineEndpoint, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Request failed (${response.status})`);
        }
        const payload = (await response.json()) as SourceSnapshotTimelinePayload;
        const timepoints = Array.isArray(payload.timepoints) ? payload.timepoints : [];
        setSourceSnapshotTimeline(timepoints);
        setSelectedSnapshotEventId((current) => {
          if (current && timepoints.some((item) => item.event_id === current)) {
            return current;
          }
          return timepoints[timepoints.length - 1]?.event_id ?? null;
        });
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setSourceSnapshotTimeline([]);
        setSourceSnapshotTimelineError(
          error instanceof Error ? error.message : "Unknown fetch error"
        );
      } finally {
        if (!controller.signal.aborted) {
          setIsSourceSnapshotTimelineLoading(false);
        }
      }
    };

    void loadTimeline();

    return () => {
      controller.abort();
    };
  }, [sourceTimelineEndpoint]);

  const filteredRuns = useMemo(() => {
    return runs.filter((run) => {
      const haystack = [
        run.run_id,
        run.workflow_mode,
        run.created_at,
        run.proposition_count,
        run.divergence_assessment_count,
        run.artifact_count,
        run.stage_trace_count,
      ]
        .map((item) => toText(item, ""))
        .join(" ");
      return matchesQuery(haystack, runSearch);
    });
  }, [runSearch, runs]);

  const runRecord = asRecord(runDetail?.run) ?? {};
  const runManifest = asRecord(runDetail?.manifest) ?? {};
  const runTraceManifest = asRecord(runDetail?.trace_manifest) ?? {};
  const traceManifestStages = asArrayRecords(runTraceManifest.stages);

  const filteredTraces = useMemo(() => {
    return traces.filter((trace) => {
      const traceRecord = asRecord(trace.trace) ?? {};
      const haystack = [
        trace.order,
        trace.stage_name,
        trace.storage_uri,
        traceRecord.strategy_used,
        traceRecord.model_alias_used,
        traceRecord.duration_ms,
        traceRecord.timestamp,
      ]
        .map((item) => toText(item, ""))
        .join(" ");
      return matchesQuery(haystack, traceSearch);
    });
  }, [traceSearch, traces]);

  const filteredReviewDecisions = useMemo(() => {
    return reviewDecisions.filter((decision) => {
      const haystack = [
        decision.id,
        decision.target_type,
        decision.target_id,
        decision.previous_status,
        decision.new_status,
        decision.reviewer,
        decision.timestamp,
        decision.note,
      ]
        .map((item) => toText(item, ""))
        .join(" ");
      return matchesQuery(haystack, decisionSearch);
    });
  }, [decisionSearch, reviewDecisions]);

  const filteredRunPropositions = useMemo(() => {
    return runPropositions.filter((proposition) => {
      const haystack = [
        proposition.id,
        proposition.proposition_key,
        proposition.proposition_version_id,
        proposition.source_record_id,
        proposition.source_snapshot_id,
        proposition.article_reference,
        proposition.fragment_locator,
        proposition.legal_subject,
        proposition.action,
      ]
        .map((item) => toText(item, ""))
        .join(" ");
      return matchesQuery(haystack, propositionSearch);
    });
  }, [propositionSearch, runPropositions]);

  const propositionHistoryObservedVersions = useMemo(() => {
    return Array.isArray(propositionHistory?.observed_versions)
      ? propositionHistory.observed_versions
      : [];
  }, [propositionHistory]);

  const filteredPropositionHistoryObservedVersions = useMemo(() => {
    return propositionHistoryObservedVersions.filter((version) => {
      const haystack = [
        version.proposition_key,
        version.proposition_version_id,
        version.source_record_id,
        version.source_snapshot_id,
        version.observed_in_run_id,
        version.article_reference,
        version.fragment_locator,
        version.legal_subject,
        version.action,
        version.proposition_text,
        version.previous_version_signal,
      ]
        .map((item) => toText(item, ""))
        .join(" ");
      return matchesQuery(haystack, propositionVersionSearch);
    });
  }, [propositionHistoryObservedVersions, propositionVersionSearch]);

  const propositionHistoryVersionsByRun = useMemo(() => {
    return Array.isArray(propositionHistory?.versions_by_run)
      ? propositionHistory.versions_by_run
      : [];
  }, [propositionHistory]);

  const propositionHistoryVersionsBySnapshot = useMemo(() => {
    return Array.isArray(propositionHistory?.versions_by_snapshot)
      ? propositionHistory.versions_by_snapshot
      : [];
  }, [propositionHistory]);

  const filteredRunDivergenceAssessments = useMemo(() => {
    return runDivergenceAssessments.filter((assessment) => {
      const findingId = divergenceFindingId(assessment);
      const sourceSnapshotIds = Array.isArray(assessment.source_snapshot_ids)
        ? assessment.source_snapshot_ids.join(" ")
        : "";
      const haystack = [
        assessment.id,
        findingId,
        assessment.proposition_id,
        assessment.comparator_proposition_id,
        assessment.divergence_type,
        assessment.confidence,
        assessment.review_status,
        assessment.rationale,
        assessment.operational_impact,
        sourceSnapshotIds,
      ]
        .map((item) => toText(item, ""))
        .join(" ");
      return matchesQuery(haystack, divergenceSearch);
    });
  }, [divergenceSearch, runDivergenceAssessments]);

  const divergenceHistoryObservedVersions = useMemo(() => {
    return Array.isArray(divergenceHistory?.observed_versions)
      ? divergenceHistory.observed_versions
      : [];
  }, [divergenceHistory]);

  const filteredDivergenceHistoryObservedVersions = useMemo(() => {
    return divergenceHistoryObservedVersions.filter((version) => {
      const sourceRecordIds = Array.isArray(version.source_record_ids)
        ? version.source_record_ids.join(" ")
        : "";
      const sourceSnapshotIds = Array.isArray(version.source_snapshot_ids)
        ? version.source_snapshot_ids.join(" ")
        : "";
      const haystack = [
        version.finding_id,
        version.observation_id,
        version.version_identity,
        version.observed_in_run_id,
        version.divergence_type,
        version.confidence,
        version.review_status,
        version.rationale,
        version.operational_impact,
        version.previous_version_signal,
        sourceRecordIds,
        sourceSnapshotIds,
      ]
        .map((item) => toText(item, ""))
        .join(" ");
      return matchesQuery(haystack, divergenceVersionSearch);
    });
  }, [divergenceHistoryObservedVersions, divergenceVersionSearch]);

  const divergenceHistoryVersionsByRun = useMemo(() => {
    return Array.isArray(divergenceHistory?.versions_by_run)
      ? divergenceHistory.versions_by_run
      : [];
  }, [divergenceHistory]);

  const divergenceHistoryVersionsBySnapshot = useMemo(() => {
    return Array.isArray(divergenceHistory?.versions_by_snapshot)
      ? divergenceHistory.versions_by_snapshot
      : [];
  }, [divergenceHistory]);

  const filteredSourceRecords = useMemo(() => {
    return sourceRecords.filter((source) => {
      const haystack = [
        source.id,
        source.title,
        source.jurisdiction,
        source.citation,
        source.review_status,
      ]
        .map((item) => toText(item, ""))
        .join(" ");
      return matchesQuery(haystack, sourceSearch);
    });
  }, [sourceRecords, sourceSearch]);

  const selectedSourceRecord = useMemo(() => {
    return sourceRecords.find((item) => item.id === selectedSourceId) ?? null;
  }, [selectedSourceId, sourceRecords]);

  const sourceDetailDisplayRecord = useMemo(() => {
    const fromDetail = asRecord(sourceDetail?.source_record);
    if (fromDetail) {
      return fromDetail;
    }
    if (sourceDetailSummaryFallback) {
      return asRecord(selectedSourceRecord);
    }
    return null;
  }, [sourceDetail, sourceDetailSummaryFallback, selectedSourceRecord]);

  const softenOptionalSourceAuditErrors = Boolean(
    sourceDetail?.partial || sourceDetailSummaryFallback,
  );

  const canShowRawSourceRecordJson = Boolean(
    sourceDetail && !sourceDetail.partial && !sourceDetailSummaryFallback,
  );

  const hasAuthoritativeText = Boolean(
    toText(sourceDetailDisplayRecord?.authoritative_text).trim(),
  );

  const optionalSourceAuditErrorClass = softenOptionalSourceAuditErrors
    ? "text-sm text-amber-900 dark:text-amber-300"
    : "text-sm text-destructive";

  const filteredSourceSnapshotTimeline = useMemo(() => {
    return sourceSnapshotTimeline.filter((timepoint) => {
      const comparison = asRecord(timepoint.comparison) ?? {};
      const haystack = [
        timepoint.event_id,
        timepoint.snapshot_id,
        timepoint.source_record_id,
        timepoint.version_id,
        timepoint.content_hash,
        timepoint.retrieved_at,
        timepoint.as_of_date,
        timepoint.provenance,
        timepoint.authoritative_locator,
        comparison.change_kind,
      ]
        .map((item) => toText(item, ""))
        .join(" ");
      return matchesQuery(haystack, snapshotSearch);
    });
  }, [snapshotSearch, sourceSnapshotTimeline]);

  const selectedSnapshotTimeline = useMemo(() => {
    if (!selectedSnapshotEventId) {
      return null;
    }
    return sourceSnapshotTimeline.find((item) => item.event_id === selectedSnapshotEventId) ?? null;
  }, [selectedSnapshotEventId, sourceSnapshotTimeline]);

  const filteredSourceFragments = useMemo(() => {
    return sourceFragments.filter((fragment) => {
      const haystack = [
        fragment.id,
        fragment.source_record_id,
        fragment.source_snapshot_id,
        fragment.locator,
        fragment.fragment_hash,
        fragment.review_status,
      ]
        .map((item) => toText(item, ""))
        .join(" ");
      return matchesQuery(haystack, fragmentSearch);
    });
  }, [fragmentSearch, sourceFragments]);

  const familyCandidatesGrouped = useMemo(() => {
    if (!familyDiscovery?.candidates?.length) {
      return [];
    }
    const order = [
      "required_core",
      "required_for_scope",
      "optional_context",
      "candidate_needs_review",
      "excluded",
      "unknown",
    ];
    const buckets = new Map<string, SourceFamilyCandidateRow[]>();
    for (const row of familyDiscovery.candidates) {
      const status = typeof row.inclusion_status === "string" ? row.inclusion_status : "unknown";
      const existing = buckets.get(status);
      if (existing) {
        existing.push(row);
      } else {
        buckets.set(status, [row]);
      }
    }
    const result: { status: string; rows: SourceFamilyCandidateRow[] }[] = [];
    for (const key of order) {
      const rows = buckets.get(key);
      if (rows && rows.length > 0) {
        result.push({ status: key, rows });
      }
    }
    for (const [status, rows] of buckets.entries()) {
      if (!order.includes(status) && rows.length > 0) {
        result.push({ status, rows });
      }
    }
    return result;
  }, [familyDiscovery]);

  const filteredRegistryEntries = useMemo(() => {
    return registryEntries.filter((entry) => {
      const reference = asRecord(entry.reference) ?? {};
      const currentState = asRecord(entry.current_state) ?? {};
      const sourceRecord = asRecord(currentState.source_record) ?? {};
      const haystack = [
        entry.registry_id,
        entry.created_at,
        entry.updated_at,
        reference.authority,
        reference.authority_source_id,
        reference.title,
        sourceRecord.id,
        sourceRecord.jurisdiction,
        sourceRecord.citation,
      ]
        .map((item) => toText(item, ""))
        .join(" ");
      return matchesQuery(haystack, registrySearch);
    });
  }, [registryEntries, registrySearch]);

  const registryAuthoritySourceIds = useMemo(() => {
    const ids = new Set<string>();
    for (const entry of registryEntries) {
      const reference = asRecord(entry.reference) ?? {};
      const membershipKey = sourceMembershipKey(reference.authority, reference.authority_source_id);
      if (!membershipKey || membershipKey === ":") {
        continue;
      }
      ids.add(membershipKey);
    }
    return ids;
  }, [registryEntries]);

  const knownMembershipKeys = useMemo(() => {
    return new Set<string>([...registryAuthoritySourceIds, ...optimisticRegisteredResultKeys]);
  }, [optimisticRegisteredResultKeys, registryAuthoritySourceIds]);

  const registryEntryByMembershipKey = useMemo(() => {
    const byMembershipKey = new Map<string, RegistryEntry>();
    for (const entry of registryEntries) {
      const reference = asRecord(entry.reference) ?? {};
      const membershipKey = sourceMembershipKey(reference.authority, reference.authority_source_id);
      if (!membershipKey || membershipKey === ":") {
        continue;
      }
      byMembershipKey.set(membershipKey, entry);
    }
    return byMembershipKey;
  }, [registryEntries]);

  const familyCandidateClassificationMap = useMemo(() => {
    const m = new Map<string, ClassifiedFamilyCandidate>();
    if (!familyDiscovery?.candidates?.length) {
      return m;
    }
    for (const row of familyDiscovery.candidates) {
      m.set(
        row.id,
        classifyFamilyCandidate({
          row,
          registryEntries,
          registryByMembershipKey: registryEntryByMembershipKey,
          registeredThisSession: familyCandidatesRegisteredSession,
          decisions: familyCandidateDecisions,
        })
      );
    }
    return m;
  }, [
    familyDiscovery,
    registryEntries,
    registryEntryByMembershipKey,
    familyCandidatesRegisteredSession,
    familyCandidateDecisions,
  ]);

  const familyNeedsSelectionRunWarning = useMemo(() => {
    if (
      !familyDiscovery?.candidates?.length ||
      !selectedRegistryId ||
      !selectedRegistryIdsForRun.includes(selectedRegistryId)
    ) {
      return false;
    }
    for (const row of familyDiscovery.candidates) {
      const c = familyCandidateClassificationMap.get(row.id);
      if (!c || c.primary === "ignored") {
        continue;
      }
      if (c.primary === "needs_source_selection" && !c.coverage_registry_id) {
        return true;
      }
    }
    return false;
  }, [
    familyDiscovery?.candidates,
    familyCandidateClassificationMap,
    selectedRegistryId,
    selectedRegistryIdsForRun,
  ]);

  const selectedRegistryEntry = useMemo(() => {
    if (!selectedRegistryId) {
      return null;
    }
    return registryEntries.find((entry) => entry.registry_id === selectedRegistryId) ?? null;
  }, [registryEntries, selectedRegistryId]);

  const findRegistryIdForCandidate = (candidate: SourceSearchCandidate): string | null => {
    const candidateKey = sourceMembershipKey(candidate.authority, candidate.authority_source_id);
    for (const entry of registryEntries) {
      const reference = asRecord(entry.reference) ?? {};
      if (
        sourceMembershipKey(reference.authority, reference.authority_source_id) === candidateKey
      ) {
        return entry.registry_id;
      }
    }
    return null;
  };

  const selectedRegistryReference = asRecord(selectedRegistryEntry?.reference) ?? {};
  const selectedRegistryCurrentState = asRecord(selectedRegistryEntry?.current_state) ?? {};
  const selectedRegistryCurrentSourceRecord =
    asRecord(selectedRegistryCurrentState.source_record) ?? {};
  const selectedRegistryCurrentSourceSnapshot =
    asRecord(selectedRegistryCurrentState.source_snapshot) ?? {};
  const selectedRegistryCurrentSourceFragment =
    asRecord(selectedRegistryCurrentState.source_fragment) ?? {};
  const hasSelectedRegistryCurrentState = Object.keys(selectedRegistryCurrentState).length > 0;
  const hasSelectedRunArtifacts =
    Boolean(selectedRunId) &&
    (sourceRecords.length > 0 || traces.length > 0 || reviewDecisions.length > 0);

  const toggleRegistrySelectionForRun = (registryId: string): void => {
    setSelectedRegistryIdsForRun((current) => {
      if (current.includes(registryId)) {
        return current.filter((item) => item !== registryId);
      }
      return [...current, registryId];
    });
  };

  const selectedRunJurisdictionCounts = useMemo(() => {
    let eu = 0;
    let uk = 0;
    let other = 0;
    for (const rid of selectedRegistryIdsForRun) {
      const entry = registryEntries.find((e) => e.registry_id === rid);
      if (!entry) {
        continue;
      }
      const ref = asRecord(entry.reference) ?? {};
      const j = String(ref.jurisdiction ?? "").trim().toUpperCase();
      if (j === "EU") {
        eu += 1;
      } else if (j === "UK") {
        uk += 1;
      } else if (j) {
        other += 1;
      }
    }
    return { eu, uk, other };
  }, [registryEntries, selectedRegistryIdsForRun]);

  const [compareLeftRunId, setCompareLeftRunId] = useState("");
  const [compareRightRunId, setCompareRightRunId] = useState("");
  const [compareBusy, setCompareBusy] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [compareSuccess, setCompareSuccess] = useState<string | null>(null);

  const handleRegistryRegister = async (): Promise<void> => {
    setIsRegistering(true);
    setRegisterError(null);
    setRegisterSuccess(null);
    try {
      const parsed = JSON.parse(registerPayload) as unknown;
      if (!asRecord(parsed)) {
        throw new Error("Reference payload must be a JSON object.");
      }
      const response = await fetch(`${API_BASE_URL}/ops/source-registry/register`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          reference: parsed,
          refresh: true,
        }),
      });
      if (!response.ok) {
        const errorPayload = (await response.json().catch(() => null)) as Record<
          string,
          unknown
        > | null;
        throw new Error(toText(errorPayload?.detail, `Request failed (${response.status})`));
      }
      const created = (await response.json()) as RegistryEntry;
      setRegisterSuccess(`Registered ${created.registry_id}`);
      setSelectedRegistryId(created.registry_id);
      await loadRegistryEntries(new AbortController().signal);
    } catch (error) {
      setRegisterError(error instanceof Error ? error.message : "Unknown register error");
    } finally {
      setIsRegistering(false);
    }
  };

  const handleSourceSearch = async (): Promise<void> => {
    const query = sourceSearchQuery.trim();
    if (!query) {
      setSourceSearchError("Search query is required.");
      return;
    }
    setHasSourceSearchAttempted(true);
    setIsSourceSearchLoading(true);
    setSourceSearchError(null);
    setSourceSearchSuccess(null);
    setRegisterError(null);
    setRegisterSuccess(null);
    try {
      const response = await fetch(`${API_BASE_URL}/ops/source-registry/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          provider: "legislation_gov_uk",
          query,
          limit: 10,
        }),
      });
      if (!response.ok) {
        const errorPayload = (await response.json().catch(() => null)) as Record<
          string,
          unknown
        > | null;
        throw new Error(toText(errorPayload?.detail, `Request failed (${response.status})`));
      }
      const payload = (await response.json()) as {
        candidates?: SourceSearchCandidate[];
        count?: number;
      };
      const candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
      setSourceSearchResults(candidates);
      setSourceSearchSuccess(`Found ${toText(payload.count ?? candidates.length)} candidate(s).`);
    } catch (error) {
      setSourceSearchResults([]);
      setSourceSearchError(error instanceof Error ? error.message : "Unknown source search error");
    } finally {
      setIsSourceSearchLoading(false);
    }
  };

  const handleAddSearchCandidateToRegistry = async (
    candidate: SourceSearchCandidate
  ): Promise<void> => {
    const membershipKey = sourceMembershipKey(candidate.authority, candidate.authority_source_id);
    const existingRegistryId = findRegistryIdForCandidate(candidate);
    if (existingRegistryId) {
      setSelectedRegistryId(existingRegistryId);
      setSelectedRegistryIdsForRun((current) =>
        current.includes(existingRegistryId) ? current : [...current, existingRegistryId]
      );
      setRegisterError(null);
      setRegisterSuccess(`Already in registry as ${existingRegistryId}`);
      return;
    }
    setAddingCandidateId(candidate.authority_source_id);
    setRegisterError(null);
    setRegisterSuccess(null);
    setRegistryRefreshError(null);
    setRegistryRefreshSuccess(null);
    try {
      const reference = {
        authority: candidate.authority,
        authority_source_id: candidate.authority_source_id,
        id: sourceIdFromAuthoritySourceId(candidate.authority_source_id),
        title: candidate.title,
        jurisdiction: candidate.jurisdiction,
        citation: candidate.citation,
        kind: "legislation",
        source_url: `${candidate.canonical_source_url}/data.xml`,
        version_id: "latest",
        provenance: candidate.provenance,
        metadata: {
          source_search: {
            source_identifier: candidate.source_identifier,
            canonical_source_url: candidate.canonical_source_url,
            searched_query: sourceSearchQuery.trim(),
          },
        },
      };
      const response = await fetch(`${API_BASE_URL}/ops/source-registry/register`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          reference,
          refresh: true,
        }),
      });
      if (!response.ok) {
        const errorPayload = (await response.json().catch(() => null)) as Record<
          string,
          unknown
        > | null;
        throw new Error(toText(errorPayload?.detail, `Request failed (${response.status})`));
      }
      const created = (await response.json()) as RegistryEntry;
      setOptimisticRegisteredResultKeys((current) => new Set(current).add(membershipKey));
      setRegisterSuccess(`Registered ${created.registry_id}`);
      setSelectedRegistryId(created.registry_id);
      setSelectedRegistryIdsForRun((current) =>
        current.includes(created.registry_id) ? current : [...current, created.registry_id]
      );
      await loadRegistryEntries(new AbortController().signal);
    } catch (error) {
      setOptimisticRegisteredResultKeys((current) => {
        const next = new Set(current);
        next.delete(membershipKey);
        return next;
      });
      setRegisterError(error instanceof Error ? error.message : "Unknown register error");
    } finally {
      setAddingCandidateId(null);
    }
  };

  const handleRegistryRefresh = async (): Promise<void> => {
    if (!selectedRegistryId) {
      return;
    }
    setIsRefreshingRegistryEntry(true);
    setRegistryRefreshError(null);
    setRegistryRefreshSuccess(null);
    setRunFromRegistryError(null);
    setRunFromRegistrySuccess(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/ops/source-registry/${encodeURIComponent(selectedRegistryId)}/refresh`,
        {
          method: "POST",
          headers: { Accept: "application/json" },
        }
      );
      if (!response.ok) {
        const errorPayload = (await response.json().catch(() => null)) as Record<
          string,
          unknown
        > | null;
        throw new Error(toText(errorPayload?.detail, `Request failed (${response.status})`));
      }
      await response.json();
      await loadRegistryEntries(new AbortController().signal);
      setRegistryRefreshSuccess(`Refreshed ${selectedRegistryId}`);
    } catch (error) {
      setRegistryRefreshError(error instanceof Error ? error.message : "Unknown refresh error");
    } finally {
      setIsRefreshingRegistryEntry(false);
    }
  };

  const toggleContextFamilyCandidate = (candidateId: string): void => {
    setContextFamilyCandidateIds((prev) =>
      prev.includes(candidateId) ? prev.filter((id) => id !== candidateId) : [...prev, candidateId]
    );
  };

  const toggleRegisterFamilyCandidate = (candidateId: string): void => {
    setRegisterFamilyCandidateIds((prev) =>
      prev.includes(candidateId) ? prev.filter((id) => id !== candidateId) : [...prev, candidateId]
    );
  };

  const handleDiscoverRelatedSources = async (): Promise<void> => {
    if (!selectedRegistryId) {
      setFamilyDiscoveryError("Select a registry entry first.");
      return;
    }
    setIsFamilyDiscoveryLoading(true);
    setFamilyDiscoveryError(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/ops/source-registry/${encodeURIComponent(selectedRegistryId)}/discover-related`,
        {
          method: "POST",
          headers: { Accept: "application/json" },
        }
      );
      if (!response.ok) {
        const errorPayload = (await response.json().catch(() => null)) as Record<
          string,
          unknown
        > | null;
        throw new Error(toText(errorPayload?.detail, `Request failed (${response.status})`));
      }
      const payload = (await response.json()) as {
        candidates?: SourceFamilyCandidateRow[];
        registry_id?: string;
        target_authority_source_id?: string;
      };
      const rows = Array.isArray(payload.candidates) ? payload.candidates : [];
      setFamilyDiscovery({
        registry_id: toText(payload.registry_id, selectedRegistryId),
        target_authority_source_id:
          typeof payload.target_authority_source_id === "string"
            ? payload.target_authority_source_id
            : undefined,
        candidates: rows,
      });
      setContextFamilyCandidateIds([]);
      setRegisterFamilyCandidateIds([]);
      setFamilyCandidatesRegisteredSession({});
      setFamilyCandidateDecisions({});
      setFamilyRegisterMessage(null);
      setFamilyRegisterError(null);
    } catch (error) {
      setFamilyDiscovery(null);
      setFamilyDiscoveryError(
        error instanceof Error ? error.message : "Unknown discovery error"
      );
    } finally {
      setIsFamilyDiscoveryLoading(false);
    }
  };

  const handleRegisterFamilyCandidates = async (): Promise<void> => {
    if (!selectedRegistryId) {
      setFamilyRegisterError("Select a registry entry first.");
      return;
    }
    if (registerFamilyCandidateIds.length === 0) {
      setFamilyRegisterError("Select at least one candidate to register.");
      return;
    }
    setIsRegisteringFamilyCandidates(true);
    setFamilyRegisterError(null);
    setFamilyRegisterMessage(null);
    try {
      const response = await fetch(`${API_BASE_URL}/ops/source-registry/register-family-candidates`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          target_registry_id: selectedRegistryId,
          candidate_ids: registerFamilyCandidateIds,
        }),
      });
      if (!response.ok) {
        const errorPayload = (await response.json().catch(() => null)) as Record<
          string,
          unknown
        > | null;
        throw new Error(toText(errorPayload?.detail, `Request failed (${response.status})`));
      }
      const payload = (await response.json()) as {
        registered?: { candidate_id: string; registry_id: string }[];
        already_registered?: { candidate_id: string; registry_id: string }[];
        manual_review_needed?: { candidate_id: string; reason: string }[];
        errors?: { candidate_id?: string; message?: string }[];
      };
      const registered = Array.isArray(payload.registered) ? payload.registered : [];
      const already = Array.isArray(payload.already_registered) ? payload.already_registered : [];
      const manual = Array.isArray(payload.manual_review_needed) ? payload.manual_review_needed : [];
      const errs = Array.isArray(payload.errors) ? payload.errors : [];

      setFamilyCandidatesRegisteredSession((prev) => {
        const next = { ...prev };
        for (const item of registered) {
          if (item.candidate_id && item.registry_id) {
            next[item.candidate_id] = item.registry_id;
          }
        }
        for (const item of already) {
          if (item.candidate_id && item.registry_id) {
            next[item.candidate_id] = item.registry_id;
          }
        }
        return next;
      });

      await loadRegistryEntries(new AbortController().signal);

      if (registered.length > 0) {
        setFamilyRegisterMessage(
          "Registered sources are now available in the Registered sources list. Tick them there to include them in analysis."
        );
      } else {
        const parts: string[] = [];
        if (already.length > 0) {
          parts.push(`${already.length} already in registry`);
        }
        if (manual.length > 0) {
          parts.push(`${manual.length} need manual review`);
        }
        if (errs.length > 0) {
          parts.push(`${errs.length} error(s)`);
        }
        setFamilyRegisterMessage(parts.length > 0 ? parts.join(" · ") : "No changes.");
      }
      if (errs.length > 0) {
        const first = errs[0];
        setFamilyRegisterError(
          toText(first?.message, `Registration error for ${toText(first?.candidate_id, "candidate")}`)
        );
      }
    } catch (error) {
      setFamilyRegisterError(error instanceof Error ? error.message : "Unknown registration error");
    } finally {
      setIsRegisteringFamilyCandidates(false);
    }
  };

  const handleComparePropositionDatasets = async (): Promise<void> => {
    const left = compareLeftRunId.trim();
    const right = compareRightRunId.trim();
    if (!left || !right) {
      setCompareError("Select both dataset runs (run IDs).");
      return;
    }
    if (left === right) {
      setCompareError("Choose two different runs.");
      return;
    }
    setCompareBusy(true);
    setCompareError(null);
    setCompareSuccess(null);
    try {
      const response = await fetch(`${API_BASE_URL}/ops/run-jobs/compare-proposition-datasets`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          left_run_id: left,
          right_run_id: right,
          use_llm: false,
          divergence_reasoning: "none",
        }),
      });
      if (!response.ok) {
        const errorPayload = (await response.json().catch(() => null)) as Record<
          string,
          unknown
        > | null;
        throw new Error(toText(errorPayload?.detail, `Request failed (${response.status})`));
      }
      const payload = (await response.json()) as Record<string, unknown>;
      const jobId = toText(payload.job_id, "");
      setCompareSuccess(
        jobId
          ? `Comparison queued (job ${jobId}). Open Propositions → Divergences after it finishes.`
          : "Comparison queued."
      );
      void loadRuns(new AbortController().signal);
    } catch (error) {
      setCompareError(error instanceof Error ? error.message : "Unknown compare error");
    } finally {
      setCompareBusy(false);
    }
  };

  const handleRunFromRegistry = async (): Promise<void> => {
    if (selectedRegistryIdsForRun.length === 0) {
      setRunFromRegistryError("Select at least one registry source.");
      return;
    }
    if (!runFromRegistryTopicName.trim()) {
      setRunFromRegistryError("Topic name is required.");
      return;
    }
    setIsRunningFromRegistry(true);
    setRunFromRegistryError(null);
    setRunFromRegistrySuccess(null);
    setRegistryRunJobPollError(null);
    setRegistryRunJob(null);
    setRegistryRunJobEvents([]);
    setRegistryRunJobId(null);
    setRegistryRefreshError(null);
    setRegistryRefreshSuccess(null);
    try {
      const requestBody: Record<string, unknown> = {
        registry_ids: selectedRegistryIdsForRun,
        topic_name: runFromRegistryTopicName.trim(),
        cluster_name: runFromRegistryClusterName.trim() || null,
        analysis_mode: runFromRegistryAnalysisMode,
        analysis_scope: runFromRegistryAnalysisScope,
      };
      const subjectTags = splitCommaValues(runFromRegistrySubjectTags);
      if (subjectTags.length > 0) {
        requestBody.subject_tags = subjectTags;
      }
      if (runFromRegistryQualityRun) {
        requestBody.quality_run = true;
      }
      if (runFromRegistryExtractionMode) {
        requestBody.extraction_mode = runFromRegistryExtractionMode;
      }
      if (runFromRegistryExtractionExecutionMode) {
        requestBody.extraction_execution_mode = runFromRegistryExtractionExecutionMode;
      }
      if (runFromRegistryExtractionFallback) {
        requestBody.extraction_fallback = runFromRegistryExtractionFallback;
      }
      if (runFromRegistryDivergenceReasoning) {
        requestBody.divergence_reasoning = runFromRegistryDivergenceReasoning;
      }
      const focusScopesPayload = splitCommaValues(runFromRegistryFocusScopesText);
      if (focusScopesPayload.length > 0) {
        requestBody.focus_scopes = focusScopesPayload;
      }
      const maxRaw = runFromRegistryMaxPropositions.trim();
      if (maxRaw) {
        const n = Number.parseInt(maxRaw, 10);
        if (!Number.isNaN(n) && n > 0) {
          requestBody.max_propositions_per_source = n;
        }
      }
      const advMode = runFromRegistryExtractionMode;
      const needsLlmForAdvanced =
        advMode === "frontier" || advMode === "local" || runFromRegistryDivergenceReasoning === "frontier";
      if (!runFromRegistryQualityRun && needsLlmForAdvanced) {
        requestBody.use_llm = true;
      }
      if (
        selectedRegistryId &&
        contextFamilyCandidateIds.length > 0 &&
        selectedRegistryIdsForRun.includes(selectedRegistryId)
      ) {
        requestBody.source_family_selection = {
          registry_id: selectedRegistryId,
          included_candidate_ids: contextFamilyCandidateIds,
        };
      }
      const response = await fetch(`${API_BASE_URL}/ops/run-jobs/from-registry`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(requestBody),
      });
      if (!response.ok) {
        const errorPayload = (await response.json().catch(() => null)) as Record<
          string,
          unknown
        > | null;
        throw new Error(toText(errorPayload?.detail, `Request failed (${response.status})`));
      }
      const payload = (await response.json()) as Record<string, unknown>;
      const jobId = toText(payload.job_id, "");
      if (!jobId) {
        throw new Error("Missing job_id from run-jobs response.");
      }
      setRegistryRunJobId(jobId);
      setRunFromRegistrySuccess("Run queued — progress updates below.");
    } catch (error) {
      setRunFromRegistryError(error instanceof Error ? error.message : "Unknown run error");
    } finally {
      setIsRunningFromRegistry(false);
    }
  };

  const handleCuratedEquineCorpusJob = async (): Promise<void> => {
    setIsRunningEquineCorpus(true);
    setEquineCorpusRunError(null);
    setEquineCorpusRunSuccess(null);
    setEquineCorpusRunJobPollError(null);
    setEquineCorpusRunJobEvents([]);
    setEquineCorpusRunJob(null);
    setEquineCorpusRunJobId(null);
    try {
      const response = await fetch(`${API_BASE_URL}/ops/run-jobs/equine-corpus`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          corpus_id: "equine_law",
          extraction_execution_mode: equineCorpusExtractionExecutionMode,
          extraction_mode:
            equineCorpusExtractionExecutionMode === "batch" ? "frontier" : undefined,
        }),
      });
      if (!response.ok) {
        const errorPayload = (await response.json().catch(() => null)) as Record<
          string,
          unknown
        > | null;
        throw new Error(toText(errorPayload?.detail, `Request failed (${response.status})`));
      }
      const payload = (await response.json()) as Record<string, unknown>;
      const jobId = toText(payload.job_id, "");
      if (!jobId) {
        throw new Error("Missing job_id from run-jobs response.");
      }
      setEquineCorpusRunJobId(jobId);
      setEquineCorpusRunJob({ id: jobId, status: "queued", progress_message: "Queued…" });
      setEquineCorpusRunSuccess("Queued — monitor progress below.");
    } catch (error) {
      setEquineCorpusRunError(error instanceof Error ? error.message : "Unknown run error");
    } finally {
      setIsRunningEquineCorpus(false);
    }
  };

  const handleDevClearRunsDryRun = (): void => {
    void (async (): Promise<void> => {
      setDevClearRunsStatus(null);
      setDevClearError(null);
      setIsDevClearRunsDryRunning(true);
      try {
        const response = await fetch(`${API_BASE_URL}/ops/dev/clear/runs`, {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ dry_run: true }),
        });
        const raw = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(
            toText(
              (raw as Record<string, unknown> | null)?.detail,
              `Request failed (${response.status})`
            )
          );
        }
        const payload = raw as Record<string, unknown>;
        const count = Array.isArray(payload.deleted_paths_export)
          ? payload.deleted_paths_export.length
          : undefined;
        setDevClearRunsStatus(
          `Dry run OK${typeof count === "number" ? ` — ${count} export paths inspected` : ""}`
        );
      } catch (error) {
        setDevClearError(error instanceof Error ? error.message : "Unknown clear dry run error");
      } finally {
        setIsDevClearRunsDryRunning(false);
      }
    })();
  };

  const handleDevClearRunsDestructive = (): void => {
    void (async (): Promise<void> => {
      setDevClearRunsStatus(null);
      setDevClearError(null);
      setIsDevClearRunsDestructiveRunning(true);
      try {
        const response = await fetch(`${API_BASE_URL}/ops/dev/clear/runs`, {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            dry_run: false,
            confirmation_text: devClearRunsPhrase.trim(),
          }),
        });
        const raw = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(
            toText(
              (raw as Record<string, unknown> | null)?.detail,
              `Request failed (${response.status})`
            )
          );
        }
        await loadRuns(new AbortController().signal);
        await loadRegistryEntries(new AbortController().signal);
        setSelectedRunId(null);
        const exportDirMsg =
          raw && typeof (raw as Record<string, unknown>).export_dir === "string"
            ? (raw as Record<string, string>).export_dir
            : "export dir";
        setRegistryRefreshSuccess(
          `Development: cleared analysis bundle at ${exportDirMsg}. Registered sources unchanged.`
        );
        setDevClearRunsPhrase("");
        setDevClearRunsStatus("Runs cleared.");
      } catch (error) {
        setDevClearError(error instanceof Error ? error.message : "Unknown clear runs error");
      } finally {
        setIsDevClearRunsDestructiveRunning(false);
      }
    })();
  };

  const handleDevClearAllDryRun = (): void => {
    void (async (): Promise<void> => {
      setDevClearAllStatus(null);
      setDevClearError(null);
      setIsDevClearAllDryRunning(true);
      try {
        const response = await fetch(`${API_BASE_URL}/ops/dev/clear/all`, {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ dry_run: true }),
        });
        const raw = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(
            toText(
              (raw as Record<string, unknown> | null)?.detail,
              `Request failed (${response.status})`
            )
          );
        }
        const payload = raw as Record<string, unknown>;
        const count = Array.isArray(payload.deleted_paths_export)
          ? payload.deleted_paths_export.length
          : undefined;
        setDevClearAllStatus(`Dry run OK${typeof count === "number" ? ` — ${count} targets listed` : ""}`);
      } catch (error) {
        setDevClearError(error instanceof Error ? error.message : "Unknown clear dry run error");
      } finally {
        setIsDevClearAllDryRunning(false);
      }
    })();
  };

  const handleDevClearAllDestructive = (): void => {
    void (async (): Promise<void> => {
      setDevClearAllStatus(null);
      setDevClearError(null);
      setIsDevClearAllDestructiveRunning(true);
      try {
        const response = await fetch(`${API_BASE_URL}/ops/dev/clear/all`, {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            dry_run: false,
            confirmation_text: devClearAllPhrase.trim(),
          }),
        });
        const raw = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(
            toText(
              (raw as Record<string, unknown> | null)?.detail,
              `Request failed (${response.status})`
            )
          );
        }
        await loadRuns(new AbortController().signal);
        await loadRegistryEntries(new AbortController().signal);
        setSelectedRunId(null);
        setSelectedRegistryId(null);
        setSelectedRegistryIdsForRun([]);
        const exportDirAll =
          raw && typeof (raw as Record<string, unknown>).export_dir === "string"
            ? (raw as Record<string, string>).export_dir
            : "export dir";
        setRegistryRefreshSuccess(
          `Development: cleared registry, caches, and analysis bundle at ${exportDirAll}.`
        );
        setDevClearAllPhrase("");
        setDevClearAllStatus("Clear-all completed.");
      } catch (error) {
        setDevClearError(error instanceof Error ? error.message : "Unknown clear-all error");
      } finally {
        setIsDevClearAllDestructiveRunning(false);
      }
    })();
  };

  return (
    <section id="operations-inspector" className="mt-8 space-y-4">
      <header className="space-y-2">
        <h2 className="text-2xl font-semibold tracking-tight">Operations inspector</h2>
        <p className="text-sm text-muted-foreground">
          Read-only audit view over <code>/ops/*</code> endpoints for runs, sources, traces, and
          decisions.
        </p>
      </header>

      <div
        className="rounded-lg border border-priguidance-discovery/25 bg-priguidance-discovery/[0.06] px-4 py-3"
        aria-label="Guided workflow steps"
      >
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Guided workflow
        </p>
        <ol className="flex list-none flex-wrap gap-2 text-[11px] text-foreground/90 md:gap-2.5">
          {OPERATIONS_WORKFLOW_STEPS.map((label, index) => (
            <li
              key={label}
              className="rounded-full border border-border/70 bg-background/85 px-2.5 py-1"
            >
              {index + 1}. {label}
            </li>
          ))}
        </ol>
      </div>

      <EquineCorpusCoveragePanel
        payload={equineCorpusCoverage}
        coverageEndpointError={equineCorpusCoverageError}
        readinessToolbar={
          <>
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>Run mode</span>
                <select
                  value={equineCorpusExtractionExecutionMode}
                  onChange={(event) => setEquineCorpusExtractionExecutionMode(event.target.value)}
                  className="h-8 rounded border border-border/80 bg-background px-2 text-xs outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                >
                  <option value="interactive">Interactive</option>
                  <option value="batch">Batch / async cheaper</option>
                </select>
              </label>
              <button
                type="button"
                onClick={() => void handleCuratedEquineCorpusJob()}
                disabled={isRunningEquineCorpus}
                className="inline-flex items-center justify-center rounded-md bg-primary px-3.5 py-2 text-xs font-semibold text-primary-foreground shadow-sm transition-colors hover:bg-priguidance-discovery/90 active:bg-priguidance-discovery/95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isRunningEquineCorpus ? "Starting…" : "Run curated equine corpus"}
              </button>
              {equineCorpusRunSuccess ? (
                <span className="text-xs font-medium text-emerald-700 dark:text-emerald-400">
                  {equineCorpusRunSuccess}
                </span>
              ) : null}
              {equineCorpusRunJobPollError ? (
                <span className="text-xs text-destructive">Poll: {equineCorpusRunJobPollError}</span>
              ) : null}
              {equineCorpusRunError ? (
                <span className="text-xs text-destructive">{equineCorpusRunError}</span>
              ) : null}
            </div>
            {equineCorpusRunJobId ? (
              <RegistryRunProgressPanel
                job={equineCorpusRunJob}
                events={equineCorpusRunJobEvents}
                viewPropositionsHref="/propositions?scope=equine"
              />
            ) : null}
            {String(equineCorpusRunJob?.status || "").toLowerCase() === "pass" ||
            String(equineCorpusRunJob?.status || "").toLowerCase() === "warning" ? (
              <Link
                href="/propositions?scope=equine"
                className="inline-flex text-[11px] font-medium text-primary underline underline-offset-2 hover:text-priguidance-discovery/90"
              >
                Open propositions scoped to equine
              </Link>
            ) : null}
          </>
        }
      />

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="md:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Source registry workbench</CardTitle>
            <CardDescription>
              Search legislation.gov.uk, add sources to the registry, then run from registry state.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Run readiness
              </p>
              <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
              <span className={META_CHIP_CLASS}>
                1 search {hasSourceSearchAttempted ? "done" : "pending"}
              </span>
              <span className={META_CHIP_CLASS}>
                2 registry {registryEntries.length > 0 ? "ready" : "pending"}
              </span>
              <span className={META_CHIP_CLASS}>
                3 inspect {selectedRegistryEntry ? "ready" : "pending"}
              </span>
              <span className={META_CHIP_CLASS}>
                4 refresh {hasSelectedRegistryCurrentState ? "ready" : "pending"}
              </span>
              <span className={META_CHIP_CLASS}>
                5 run {selectedRegistryIdsForRun.length > 0 ? "ready" : "pending"}
              </span>
              <span className={META_CHIP_CLASS}>
                6 traces/sources {hasSelectedRunArtifacts ? "ready" : "pending"}
              </span>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
              <span className={META_CHIP_CLASS}>search result (not registered)</span>
              <span className={META_CHIP_CLASS}>registered source</span>
              <span className={META_CHIP_CLASS}>selected for run</span>
              <span className={META_CHIP_CLASS}>has operational history</span>
            </div>
            <div
              id="ops-registry-source-search"
              className="space-y-2 rounded border border-border/70 bg-muted/20 p-3"
            >
              <p className="text-xs text-muted-foreground">
                Search by identifier/citation (for example <code>2016/429</code>), title text, or
                pasted legislation.gov.uk URL.
              </p>
              <div className="flex flex-wrap gap-2">
                <input
                  type="search"
                  value={sourceSearchQuery}
                  onChange={(event) => {
                    setSourceSearchQuery(event.target.value);
                    setSourceSearchError(null);
                    setSourceSearchSuccess(null);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void handleSourceSearch();
                    }
                  }}
                  placeholder="Search legislation.gov.uk sources..."
                  className="h-8 min-w-[280px] flex-1 rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                />
                <button
                  type="button"
                  onClick={() => void handleSourceSearch()}
                  disabled={isSourceSearchLoading}
                  className="rounded border border-priguidance-discovery/60 bg-priguidance-discovery/[0.1] px-3 py-1.5 text-xs font-medium transition-colors hover:bg-priguidance-discovery/[0.18] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isSourceSearchLoading ? "Searching..." : "Search sources"}
                </button>
              </div>
              {sourceSearchSuccess ? (
                <p className="text-xs text-emerald-700">{sourceSearchSuccess}</p>
              ) : null}
              {sourceSearchError ? (
                <p className="text-xs text-destructive">{sourceSearchError}</p>
              ) : null}
              {hasSourceSearchAttempted &&
              !isSourceSearchLoading &&
              !sourceSearchError &&
              sourceSearchResults.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No matching authority sources found. Try identifier form (
                  <code>eur/2016/429</code>) or a full legislation.gov.uk URL.
                </p>
              ) : null}
              {sourceSearchResults.length > 0 ? (
                <div className="space-y-2">
                  {sourceSearchResults.map((candidate) => {
                    const authorityKey = sourceMembershipKey(
                      candidate.authority,
                      candidate.authority_source_id
                    );
                    const isKnown = knownMembershipKeys.has(authorityKey);
                    const candidateRegistryEntry = registryEntryByMembershipKey.get(authorityKey);
                    const knownRegistryId = isKnown ? findRegistryIdForCandidate(candidate) : null;
                    const selectedForRun = knownRegistryId
                      ? selectedRegistryIdsForRun.includes(knownRegistryId)
                      : false;
                    const currentState = asRecord(candidateRegistryEntry?.current_state) ?? {};
                    const sourceRecord = asRecord(currentState.source_record) ?? {};
                    const sourceId = toText(sourceRecord.id, "");
                    const runUsageCount = sourceId
                      ? (sourceRunUsageCountBySourceId[sourceId] ?? 0)
                      : 0;
                    const refreshHistoryCount = Array.isArray(
                      candidateRegistryEntry?.refresh_history
                    )
                      ? candidateRegistryEntry.refresh_history.length
                      : 0;
                    const hasOperationalHistory = runUsageCount > 0 || refreshHistoryCount > 1;
                    return (
                      <div
                        key={candidate.authority_source_id}
                        className={`rounded border p-2 ${
                          isKnown
                            ? "border-emerald-500/40 bg-emerald-500/[0.06]"
                            : "border-border/70 bg-background"
                        }`}
                      >
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className={META_CHIP_CLASS}>{candidate.citation}</span>
                          <span className={META_CHIP_CLASS}>{candidate.jurisdiction}</span>
                          <span className={META_CHIP_CLASS}>{candidate.authority_source_id}</span>
                          <span className={META_CHIP_CLASS}>authority: {candidate.authority}</span>
                          {isKnown ? (
                            <span className="rounded border border-emerald-600/50 bg-emerald-600/10 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                              registered source
                            </span>
                          ) : (
                            <span className="rounded border border-amber-600/50 bg-amber-600/10 px-2 py-0.5 text-[11px] font-medium text-amber-700">
                              search result (not registered)
                            </span>
                          )}
                          {selectedForRun ? (
                            <span className={META_CHIP_CLASS}>selected for run</span>
                          ) : null}
                          {hasOperationalHistory ? (
                            <span className={META_CHIP_CLASS}>has operational history</span>
                          ) : null}
                          {knownRegistryId ? (
                            <span className={META_CHIP_CLASS}>{knownRegistryId}</span>
                          ) : null}
                        </div>
                        <p className="mt-1 text-sm text-foreground/90">{candidate.title}</p>
                        <p className="mt-0.5 text-[11px] text-foreground/70">
                          {candidate.canonical_source_url}
                        </p>
                        <p className="mt-0.5 text-[11px] text-foreground/60">
                          provenance: {candidate.provenance}
                        </p>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          {isKnown ? (
                            <>
                              <button
                                type="button"
                                disabled
                                className="rounded border border-emerald-600/50 bg-emerald-600/10 px-2.5 py-1 text-xs font-medium text-emerald-700 disabled:cursor-not-allowed disabled:opacity-100"
                              >
                                Registered
                              </button>
                              {knownRegistryId ? (
                                <button
                                  type="button"
                                  onClick={() => setSelectedRegistryId(knownRegistryId)}
                                  className="rounded border border-border/80 bg-background px-2.5 py-1 text-xs font-medium text-foreground/80 hover:bg-accent/50"
                                >
                                  View in registry
                                </button>
                              ) : null}
                            </>
                          ) : (
                            <button
                              type="button"
                              onClick={() => void handleAddSearchCandidateToRegistry(candidate)}
                              disabled={addingCandidateId === candidate.authority_source_id}
                              className="rounded border border-priguidance-discovery/60 bg-priguidance-discovery/[0.1] px-2.5 py-1 text-xs font-medium transition-colors hover:bg-priguidance-discovery/[0.18] disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {addingCandidateId === candidate.authority_source_id
                                ? "Adding..."
                                : "Add to registry"}
                            </button>
                          )}
                          <a
                            href={candidate.canonical_source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="rounded border border-border/80 bg-background px-2.5 py-1 text-xs font-medium text-foreground/80 hover:bg-accent/50"
                          >
                            Open source in new tab
                          </a>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </div>

            <details className="rounded border border-border/70 p-2">
              <summary className="cursor-pointer text-xs font-medium">
                Advanced: register raw JSON reference payload
              </summary>
              <div className="mt-2 space-y-2">
                <p className="text-xs text-muted-foreground">
                  Legacy JSON-first path kept for power users, CLI parity, and non-search
                  authorities.
                </p>
                <textarea
                  value={registerPayload}
                  onChange={(event) => setRegisterPayload(event.target.value)}
                  rows={10}
                  className="w-full rounded border border-border/80 bg-background p-2 font-mono text-[12px] leading-5 outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                />
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void handleRegistryRegister()}
                    disabled={isRegistering}
                    className="rounded border border-priguidance-discovery/60 bg-priguidance-discovery/[0.1] px-3 py-1.5 text-xs font-medium transition-colors hover:bg-priguidance-discovery/[0.18] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {isRegistering ? "Registering..." : "Register source reference"}
                  </button>
                </div>
              </div>
            </details>

            <div className="flex flex-wrap items-center gap-2">
              {registerSuccess ? (
                <span className="text-xs text-emerald-700">{registerSuccess}</span>
              ) : null}
              {registerError ? (
                <span className="text-xs text-destructive">{registerError}</span>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Registered sources</CardTitle>
            <CardDescription>
              Select one entry to inspect current state and operational history signals.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-[11px] leading-snug text-muted-foreground">
              Only checked registered sources are analysed in a run.
            </p>
            <input
              type="search"
              value={registrySearch}
              onChange={(event) => setRegistrySearch(event.target.value)}
              placeholder="Filter registry by id/authority/source..."
              className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
            />
            {isRegistryLoading ? (
              <p className="text-sm text-muted-foreground">Loading registry entries...</p>
            ) : null}
            {registryError ? (
              <p className="text-sm text-destructive">
                Failed to load registry entries: <code>{registryError}</code>
              </p>
            ) : null}
            {!isRegistryLoading && !registryError && filteredRegistryEntries.length === 0 ? (
              <p className="text-sm text-muted-foreground">No registry entries found.</p>
            ) : null}
            {isRunUsageLoading ? (
              <p className="text-xs text-muted-foreground">Checking run usage signals...</p>
            ) : null}
            {runUsageError ? (
              <p className="text-xs text-destructive">
                Run usage signals unavailable: <code>{runUsageError}</code>
              </p>
            ) : null}
            {filteredRegistryEntries.map((entry) => {
              const reference = asRecord(entry.reference) ?? {};
              const currentState = asRecord(entry.current_state) ?? {};
              const currentSourceRecord = asRecord(currentState.source_record) ?? {};
              const currentSourceSnapshot = asRecord(currentState.source_snapshot) ?? {};
              const currentSourceFragment = asRecord(currentState.source_fragment) ?? {};
              const sourceId = toText(currentSourceRecord.id, "");
              const runUsageCount = sourceId ? (sourceRunUsageCountBySourceId[sourceId] ?? 0) : 0;
              const refreshHistoryCount = Array.isArray(entry.refresh_history)
                ? entry.refresh_history.length
                : 0;
              const hasCurrentSnapshot =
                Boolean(toText(currentSourceRecord.current_snapshot_id, "")) ||
                Boolean(toText(currentSourceSnapshot.id, ""));
              const hasFragments = Boolean(toText(currentSourceFragment.id, ""));
              const hasOperationalHistory = runUsageCount > 0 || refreshHistoryCount > 1;
              const lastRefreshedAt = latestRefreshedAt(entry);
              const selectedForRun = selectedRegistryIdsForRun.includes(entry.registry_id);
              return (
                <div
                  key={entry.registry_id}
                  className={`rounded border p-2 ${
                    selectedRegistryId === entry.registry_id
                      ? "border-primary bg-priguidance-discovery/[0.08]"
                      : "border-border/70 bg-background"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => setSelectedRegistryId(entry.registry_id)}
                    className="w-full text-left"
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className={META_CHIP_CLASS}>{entry.registry_id}</span>
                      <span className={META_CHIP_CLASS}>
                        authority: {toText(reference.authority)}
                      </span>
                      <span className="rounded border border-emerald-600/50 bg-emerald-600/10 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                        registered source
                      </span>
                      {selectedForRun ? (
                        <span className={META_CHIP_CLASS}>selected for run</span>
                      ) : null}
                      {hasOperationalHistory ? (
                        <span className={META_CHIP_CLASS}>has operational history</span>
                      ) : null}
                      <span className={META_CHIP_CLASS}>
                        last refreshed: {lastRefreshedAt ? formatDateTime(lastRefreshedAt) : "—"}
                      </span>
                      <span className={META_CHIP_CLASS}>
                        current snapshot: {hasCurrentSnapshot ? "yes" : "no"}
                      </span>
                      <span className={META_CHIP_CLASS}>
                        fragments: {hasFragments ? "yes" : "no"}
                      </span>
                      <span className={META_CHIP_CLASS}>used in runs: {runUsageCount}</span>
                    </div>
                    <p className="mt-1 text-[11px] text-foreground/75">
                      {toText(reference.authority_source_id)} | {toText(currentSourceRecord.id)} |{" "}
                      {toText(currentSourceRecord.jurisdiction)} | updated{" "}
                      {formatDateTime(entry.updated_at)}
                    </p>
                  </button>
                  <label className="mt-2 flex items-center gap-2 text-[11px] text-foreground/80">
                    <input
                      type="checkbox"
                      checked={selectedForRun}
                      onChange={() => toggleRegistrySelectionForRun(entry.registry_id)}
                    />
                    select for run
                  </label>
                </div>
              );
            })}
            {registryEntries.length > 0 ? (
              <details className="rounded border border-border/70 p-2">
                <summary className="cursor-pointer text-xs font-medium">
                  Raw registry list JSON
                </summary>
                <div className="mt-2">
                  <JsonBlock payload={registryEntries} />
                </div>
              </details>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Registry entry detail</CardTitle>
            <CardDescription>
              Current entry: <code>{selectedRegistryEntry?.registry_id ?? "—"}</code>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {selectedRegistryEntry ? (
              <>
                <div className="grid gap-2 sm:grid-cols-2">
                  <FieldRow label="Registry id" value={selectedRegistryEntry.registry_id} />
                  <FieldRow
                    label="Created at"
                    value={formatDateTime(selectedRegistryEntry.created_at)}
                  />
                  <FieldRow
                    label="Updated at"
                    value={formatDateTime(selectedRegistryEntry.updated_at)}
                  />
                  <FieldRow label="Authority" value={selectedRegistryReference.authority} />
                  <FieldRow
                    label="Authority source id"
                    value={selectedRegistryReference.authority_source_id}
                  />
                  <FieldRow label="Reference id" value={selectedRegistryReference.id} />
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void handleRegistryRefresh()}
                    disabled={isRefreshingRegistryEntry}
                    className="rounded border border-priguidance-discovery/60 bg-priguidance-discovery/[0.1] px-3 py-1.5 text-xs font-medium transition-colors hover:bg-priguidance-discovery/[0.18] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {isRefreshingRegistryEntry ? "Refreshing..." : "Refresh selected entry"}
                  </button>
                  {registryRefreshSuccess ? (
                    <span className="text-xs text-emerald-700">{registryRefreshSuccess}</span>
                  ) : null}
                  {registryRefreshError ? (
                    <span className="text-xs text-destructive">{registryRefreshError}</span>
                  ) : null}
                </div>
                <div className="space-y-2 rounded border border-dashed border-amber-500/35 bg-amber-500/[0.04] p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs font-medium text-foreground">
                      Related legal instruments (discovery)
                    </p>
                    <button
                      type="button"
                      onClick={() => void handleDiscoverRelatedSources()}
                      disabled={!selectedRegistryId || isFamilyDiscoveryLoading}
                      className="rounded border border-amber-600/60 bg-amber-500/[0.12] px-3 py-1.5 text-xs font-medium transition-colors hover:bg-amber-500/[0.2] disabled:cursor-not-allowed disabled:opacity-50"
                      title="Deterministic adapters use the registry reference; refreshed text is recommended but not strictly required."
                    >
                      {isFamilyDiscoveryLoading ? "Discovering..." : "Discover related sources"}
                    </button>
                  </div>
                  <p className="text-[11px] leading-relaxed text-muted-foreground">
                    Discovered related sources are candidates. Register them to analyse them. Attach
                    them as context to record that they were considered without analysing them.
                  </p>
                  <p className="text-[11px] leading-snug text-muted-foreground">
                    Attached context is recorded for audit, but is not analysed unless registered.
                  </p>
                  {familyDiscoveryError ? (
                    <p className="text-xs text-destructive">{familyDiscoveryError}</p>
                  ) : null}
                  {familyRegisterError ? (
                    <p className="text-xs text-destructive">{familyRegisterError}</p>
                  ) : null}
                  {familyRegisterMessage ? (
                    <p className="text-xs text-emerald-700">{familyRegisterMessage}</p>
                  ) : null}
                  {familyDiscovery && familyCandidatesGrouped.length > 0 ? (
                    <div className="space-y-3">
                      {familyDiscovery.target_authority_source_id ? (
                        <p className="font-mono text-[11px] text-muted-foreground">
                          Anchor: {familyDiscovery.target_authority_source_id}
                        </p>
                      ) : null}
                      {familyCandidatesGrouped.map((group) => (
                        <div key={group.status} className="space-y-2">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                            {group.status.replace(/_/g, " ")}
                          </p>
                          <div className="space-y-2">
                            {group.rows.map((row) => {
                              const classification =
                                familyCandidateClassificationMap.get(row.id) ??
                                classifyFamilyCandidate({
                                  row,
                                  registryEntries,
                                  registryByMembershipKey: registryEntryByMembershipKey,
                                  registeredThisSession: familyCandidatesRegisteredSession,
                                  decisions: familyCandidateDecisions,
                                });
                              const primary = classification.primary;
                              const conceptual = isConceptualGroupingCandidate(row);
                              const dup = classification.duplicate_match;
                              const statusStyle =
                                primary === "needs_source_selection" || primary === "context_only"
                                  ? "border-amber-600/45 bg-amber-500/[0.08] text-amber-900"
                                  : primary === "possible_duplicate"
                                    ? "border-orange-700/55 bg-orange-500/[0.1] text-orange-950"
                                    : primary === "already_registered"
                                      ? "border-emerald-600/45 bg-emerald-600/[0.08] text-emerald-900"
                                      : primary === "ready_to_register"
                                        ? "border-sky-600/45 bg-sky-500/[0.08] text-sky-900"
                                        : primary === "ignored"
                                          ? "border-border/70 bg-muted/50 text-muted-foreground"
                                          : "border-border/60 bg-muted/40 text-foreground/85";
                              const registerEligible =
                                classificationRegisterEligible(primary) &&
                                !(isRunningFromRegistry || isRegisteringFamilyCandidates);
                              const covId = classification.coverage_registry_id;
                              const blockLines = describeBlockReasons(classification.block_reasons);
                              return (
                                <div
                                  key={row.id}
                                  className="space-y-2 rounded border border-border/60 bg-background/80 p-2"
                                >
                                  <div className="flex flex-wrap items-start gap-2">
                                    <span
                                      className={`rounded border px-2 py-0.5 text-[10px] font-medium leading-5 ${statusStyle}`}
                                    >
                                      {primaryBadgeLabel(primary)}
                                    </span>
                                    <div className="min-w-0 flex-1 space-y-1">
                                      <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                                        <span className="font-medium text-foreground">{row.title}</span>
                                        <span className={META_CHIP_CLASS}>{row.source_role ?? "role"}</span>
                                        <span className={META_CHIP_CLASS}>
                                          {row.relationship_to_target ?? "relationship"}
                                        </span>
                                        <span className={META_CHIP_CLASS}>{row.confidence ?? "—"}</span>
                                      </div>
                                      {conceptual ? (
                                        <p className="text-[11px] leading-snug text-amber-900/90 dark:text-amber-200/90">
                                          {CONCEPTUAL_FAMILY_HELP}
                                        </p>
                                      ) : null}
                                      {row.reason ? (
                                        <p className="text-[11px] text-muted-foreground">{row.reason}</p>
                                      ) : null}
                                      {classification.existing_registry_id &&
                                      primary === "already_registered" ? (
                                        <p className="text-[11px] text-muted-foreground">
                                          Registry entry:{" "}
                                          <code className="text-[10px]">
                                            {classification.existing_registry_id}
                                          </code>
                                        </p>
                                      ) : null}
                                      {covId ? (
                                        <p className="text-[11px] text-emerald-800 dark:text-emerald-300">
                                          Marked as covered by registry source{" "}
                                          <code className="font-mono text-[10px]">{covId}</code>
                                        </p>
                                      ) : null}
                                      {dup ? (
                                        <p className="text-[11px] text-muted-foreground">
                                          Possible match already registered:{" "}
                                          {[dup.citation, dup.title].filter(Boolean).join(" — ") ||
                                            "—"}{" "}
                                          <span className="font-mono text-[10px]">
                                            ({dup.registry_id})
                                          </span>
                                        </p>
                                      ) : null}
                                      {blockLines.length > 0 ? (
                                        <div className="space-y-0.5 rounded border border-border/60 bg-muted/30 p-2 text-[11px] text-muted-foreground">
                                          <span className="font-medium uppercase tracking-wide text-foreground/80">
                                            Why automated registration isn’t available
                                          </span>
                                          <ul className="mt-1 list-disc space-y-0.5 pl-4 leading-snug">
                                            {blockLines.map((line, idx) => (
                                              <li key={idx}>{line}</li>
                                            ))}
                                          </ul>
                                        </div>
                                      ) : null}
                                      {row.citation || row.celex ? (
                                        <p className="font-mono text-[10px] text-muted-foreground">
                                          {[row.citation, row.celex].filter(Boolean).join(" · ")}
                                        </p>
                                      ) : null}
                                      <div className="flex flex-wrap gap-1 pt-0.5">
                                        {primary === "ready_to_register" ? (
                                          <>
                                            <button
                                              type="button"
                                              className="rounded border border-priguidance-discovery/55 bg-background px-2 py-0.5 text-[10px] font-medium text-foreground hover:bg-muted/70"
                                              onClick={() => {
                                                toggleRegisterFamilyCandidate(row.id);
                                              }}
                                              disabled={
                                                isRunningFromRegistry || isRegisteringFamilyCandidates
                                              }
                                            >
                                              Register source
                                            </button>
                                            <button
                                              type="button"
                                              className="rounded border border-priguidance-discovery/55 bg-background px-2 py-0.5 text-[10px] font-medium text-foreground hover:bg-muted/70"
                                              onClick={() => {
                                                if (!contextFamilyCandidateIds.includes(row.id)) {
                                                  toggleContextFamilyCandidate(row.id);
                                                }
                                              }}
                                              disabled={isRunningFromRegistry}
                                            >
                                              Attach as context
                                            </button>
                                          </>
                                        ) : null}
                                        {primary === "already_registered" ? (
                                          <>
                                            <button
                                              type="button"
                                              className="rounded border border-emerald-800/35 bg-emerald-500/[0.08] px-2 py-0.5 text-[10px] font-medium text-emerald-900 hover:bg-emerald-500/[0.15] dark:text-emerald-200"
                                              onClick={() => {
                                                const rid = classification.existing_registry_id;
                                                if (
                                                  rid &&
                                                  !selectedRegistryIdsForRun.includes(rid)
                                                ) {
                                                  setSelectedRegistryIdsForRun((c) =>
                                                    [...c, rid]
                                                  );
                                                }
                                                setSelectedRegistryId(rid ?? null);
                                              }}
                                              disabled={!classification.existing_registry_id}
                                            >
                                              Select registered source for run
                                            </button>
                                            <button
                                              type="button"
                                              className="rounded border border-border/70 bg-background px-2 py-0.5 text-[10px] font-medium hover:bg-muted/70"
                                              onClick={() => {
                                                if (!contextFamilyCandidateIds.includes(row.id)) {
                                                  toggleContextFamilyCandidate(row.id);
                                                }
                                              }}
                                              disabled={isRunningFromRegistry}
                                            >
                                              Attach as context
                                            </button>
                                          </>
                                        ) : null}
                                        {(primary === "needs_source_selection" || conceptual) &&
                                        !covId ? (
                                          <>
                                            <button
                                              type="button"
                                              className="rounded border border-border/70 bg-background px-2 py-0.5 text-[10px] font-medium hover:bg-muted/70"
                                              onClick={() => {
                                                document
                                                  .getElementById(
                                                    "ops-registry-source-search"
                                                  )
                                                  ?.scrollIntoView({
                                                    behavior: "smooth",
                                                    block: "nearest",
                                                  });
                                              }}
                                            >
                                              Find source
                                            </button>
                                            <button
                                              type="button"
                                              className="rounded border border-border/70 bg-background px-2 py-0.5 text-[10px] font-medium hover:bg-muted/70"
                                              onClick={() => {
                                                document
                                                  .getElementById(
                                                    "ops-registry-source-search"
                                                  )
                                                  ?.scrollIntoView({
                                                    behavior: "smooth",
                                                    block: "nearest",
                                                  });
                                              }}
                                              title="Open source search to register manually from results"
                                            >
                                              Register manually
                                            </button>
                                            <button
                                              type="button"
                                              className="rounded border border-border/70 bg-background px-2 py-0.5 text-[10px] font-medium hover:bg-muted/70"
                                              onClick={() => {
                                                if (!contextFamilyCandidateIds.includes(row.id)) {
                                                  toggleContextFamilyCandidate(row.id);
                                                }
                                              }}
                                              disabled={
                                                primary === "ignored" || isRunningFromRegistry
                                              }
                                            >
                                              Attach as context only
                                            </button>
                                            <button
                                              type="button"
                                              className="rounded border border-border/70 bg-background px-2 py-0.5 text-[10px] font-medium hover:bg-muted/70"
                                              onClick={() => {
                                                setFamilyCandidateDecisions((p) => ({
                                                  ...p,
                                                  [row.id]: {
                                                    candidate_id: row.id,
                                                    decision: "ignored",
                                                    reviewed_at: new Date().toISOString(),
                                                  },
                                                }));
                                              }}
                                            >
                                              Ignore
                                            </button>
                                          </>
                                        ) : null}
                                        {primary === "possible_duplicate" && dup?.registry_id ? (
                                          <>
                                            <button
                                              type="button"
                                              className="rounded border border-emerald-800/35 bg-emerald-500/[0.08] px-2 py-0.5 text-[10px] font-medium text-emerald-900 hover:bg-emerald-500/[0.15] dark:text-emerald-200"
                                              onClick={() => {
                                                const rid = dup.registry_id;
                                                setSelectedRegistryId(rid);
                                                if (
                                                  rid &&
                                                  !selectedRegistryIdsForRun.includes(rid)
                                                ) {
                                                  setSelectedRegistryIdsForRun((c) =>
                                                    [...c, rid]
                                                  );
                                                }
                                              }}
                                            >
                                              Use existing source
                                            </button>
                                            <button
                                              type="button"
                                              className="rounded border border-orange-900/35 bg-orange-500/[0.08] px-2 py-0.5 text-[10px] font-medium"
                                              disabled
                                              title="Add a distinguishable registry reference elsewhere; ambiguous rows are blocked from automated registration."
                                            >
                                              Register separately (manual)
                                            </button>
                                            <button
                                              type="button"
                                              className="rounded border border-border/70 bg-background px-2 py-0.5 text-[10px] font-medium hover:bg-muted/70"
                                              onClick={() => {
                                                if (!contextFamilyCandidateIds.includes(row.id)) {
                                                  toggleContextFamilyCandidate(row.id);
                                                }
                                              }}
                                              disabled={isRunningFromRegistry}
                                            >
                                              Attach as context
                                            </button>
                                            <button
                                              type="button"
                                              className="rounded border border-border/70 bg-background px-2 py-0.5 text-[10px] font-medium hover:bg-muted/70"
                                              onClick={() =>
                                                setFamilyCandidateDecisions((p) => ({
                                                  ...p,
                                                  [row.id]: {
                                                    candidate_id: row.id,
                                                    decision: "ignored",
                                                    reviewed_at: new Date().toISOString(),
                                                  },
                                                }))
                                              }
                                            >
                                              Ignore
                                            </button>
                                          </>
                                        ) : null}
                                      </div>
                                      {(primary === "needs_source_selection" ||
                                        primary === "possible_duplicate") &&
                                      !conceptual &&
                                      dup?.registry_id !== covId ? (
                                        <label className="flex flex-wrap items-center gap-2 pt-1 text-[10px] text-muted-foreground">
                                          <span>Mark covered by existing registry source</span>
                                          <select
                                            className="max-w-[260px] rounded border border-border/80 bg-background px-2 py-0.5 font-mono text-[10px] outline-none"
                                            value={
                                              familyCandidateDecisions[row.id]?.existing_registry_id ??
                                              covId ??
                                              ""
                                            }
                                            onChange={(e) => {
                                              const rid = e.target.value.trim();
                                              if (!rid) {
                                                setFamilyCandidateDecisions((p) => {
                                                  const copy = { ...p };
                                                  delete copy[row.id];
                                                  return copy;
                                                });
                                                return;
                                              }
                                              setFamilyCandidateDecisions((p) => ({
                                                ...p,
                                                [row.id]: {
                                                  candidate_id: row.id,
                                                  decision: "covered_by_existing",
                                                  existing_registry_id: rid,
                                                  reviewed_at: new Date().toISOString(),
                                                },
                                              }));
                                            }}
                                          >
                                            <option value="">Choose registry id…</option>
                                            {registryEntries.map((entry) => (
                                              <option
                                                key={entry.registry_id}
                                                value={entry.registry_id}
                                              >
                                                {entry.registry_id}{" "}
                                                {toText(
                                                  asRecord(entry.reference)?.title,
                                                  ""
                                                ).slice(0, 72)}
                                              </option>
                                            ))}
                                          </select>
                                        </label>
                                      ) : null}
                                    </div>
                                  </div>
                                  <div className="flex flex-col gap-2 border-t border-border/40 pt-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-4 sm:gap-y-1">
                                    <label className="flex cursor-pointer items-center gap-2 text-[11px] text-foreground/85">
                                      <input
                                        type="checkbox"
                                        className="h-4 w-4 shrink-0"
                                        checked={registerFamilyCandidateIds.includes(row.id)}
                                        disabled={
                                          !registerEligible ||
                                          primary === "ignored"
                                        }
                                        onChange={() => toggleRegisterFamilyCandidate(row.id)}
                                      />
                                      <span>Select for registration</span>
                                    </label>
                                    <label className="flex cursor-pointer items-center gap-2 text-[11px] text-foreground/85">
                                      <input
                                        type="checkbox"
                                        className="h-4 w-4 shrink-0"
                                        checked={contextFamilyCandidateIds.includes(row.id)}
                                        disabled={
                                          primary === "ignored" || isRunningFromRegistry
                                        }
                                        onChange={() =>
                                          toggleContextFamilyCandidate(row.id)
                                        }
                                      />
                                      <span>Attach as run context (audit only — not analysed)</span>
                                    </label>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                      <div className="flex flex-wrap items-center gap-2 border-t border-border/50 pt-2">
                        <button
                          type="button"
                          onClick={() => void handleRegisterFamilyCandidates()}
                          disabled={
                            !selectedRegistryId ||
                            registerFamilyCandidateIds.length === 0 ||
                            isRegisteringFamilyCandidates ||
                            isRunningFromRegistry
                          }
                          className="rounded border border-priguidance-discovery/60 bg-priguidance-discovery/[0.12] px-3 py-1.5 text-xs font-medium transition-colors hover:bg-priguidance-discovery/[0.18] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {isRegisteringFamilyCandidates
                            ? "Registering..."
                            : "Register selected sources"}
                        </button>
                        <span className="text-[10px] text-muted-foreground">
                          Uses the same registry refresh path as manual registration.
                        </span>
                      </div>
                    </div>
                  ) : null}
                  {familyDiscovery && familyDiscovery.candidates.length === 0 && !familyDiscoveryError ? (
                    <p className="text-xs text-muted-foreground">
                      No fixture family members for this authority id (map e.g. EUR 2016/429 first).
                    </p>
                  ) : null}
                </div>
                <details className="rounded border border-border/70 p-2">
                  <summary className="cursor-pointer text-xs font-medium">
                    Raw registry entry JSON
                  </summary>
                  <div className="mt-2">
                    <JsonBlock payload={selectedRegistryEntry} />
                  </div>
                </details>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                Select a registry entry to inspect it.
              </p>
            )}
          </CardContent>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Registry current state</CardTitle>
            <CardDescription>
              Current SourceRecord, SourceSnapshot, and SourceFragment for selected registry entry.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-3">
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                SourceRecord
              </p>
              <div className="grid gap-2">
                <FieldRow label="id" value={selectedRegistryCurrentSourceRecord.id} />
                <FieldRow label="title" value={selectedRegistryCurrentSourceRecord.title} />
                <FieldRow
                  label="jurisdiction"
                  value={selectedRegistryCurrentSourceRecord.jurisdiction}
                />
                <FieldRow label="citation" value={selectedRegistryCurrentSourceRecord.citation} />
                <FieldRow
                  label="current_snapshot_id"
                  value={selectedRegistryCurrentSourceRecord.current_snapshot_id}
                />
              </div>
              <details className="rounded border border-border/70 p-2">
                <summary className="cursor-pointer text-xs font-medium">
                  Raw SourceRecord JSON
                </summary>
                <div className="mt-2">
                  <JsonBlock payload={selectedRegistryCurrentSourceRecord} />
                </div>
              </details>
            </div>
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                SourceSnapshot
              </p>
              <div className="grid gap-2">
                <FieldRow label="id" value={selectedRegistryCurrentSourceSnapshot.id} />
                <FieldRow
                  label="source_record_id"
                  value={selectedRegistryCurrentSourceSnapshot.source_record_id}
                />
                <FieldRow
                  label="version_id"
                  value={selectedRegistryCurrentSourceSnapshot.version_id}
                />
                <FieldRow
                  label="retrieved_at"
                  value={formatDateTime(selectedRegistryCurrentSourceSnapshot.retrieved_at)}
                />
                <FieldRow
                  label="content_hash"
                  value={selectedRegistryCurrentSourceSnapshot.content_hash}
                />
              </div>
              <details className="rounded border border-border/70 p-2">
                <summary className="cursor-pointer text-xs font-medium">
                  Raw SourceSnapshot JSON
                </summary>
                <div className="mt-2">
                  <JsonBlock payload={selectedRegistryCurrentSourceSnapshot} />
                </div>
              </details>
            </div>
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                SourceFragment
              </p>
              <div className="grid gap-2">
                <FieldRow label="id" value={selectedRegistryCurrentSourceFragment.id} />
                <FieldRow
                  label="source_record_id"
                  value={selectedRegistryCurrentSourceFragment.source_record_id}
                />
                <FieldRow
                  label="source_snapshot_id"
                  value={selectedRegistryCurrentSourceFragment.source_snapshot_id}
                />
                <FieldRow label="locator" value={selectedRegistryCurrentSourceFragment.locator} />
                <FieldRow
                  label="review_status"
                  value={selectedRegistryCurrentSourceFragment.review_status}
                />
              </div>
              <details className="rounded border border-border/70 p-2">
                <summary className="cursor-pointer text-xs font-medium">
                  Raw SourceFragment JSON
                </summary>
                <div className="mt-2">
                  <JsonBlock payload={selectedRegistryCurrentSourceFragment} />
                </div>
              </details>
            </div>
          </CardContent>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Run from registry</CardTitle>
            <CardDescription>
              Runs analyse only registry sources selected below. Family candidates attached as context
              stay audit-only.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="rounded border border-border/60 bg-muted/25 px-2 py-1.5 text-[11px] leading-snug text-muted-foreground">
              Only sources you tick under Registered sources are analysed. Family candidates attached
              as run context are recorded on the bundle for audit—they do not add operative inputs
              unless registered separately.
            </div>
            {familyNeedsSelectionRunWarning ? (
              <div className="rounded border border-amber-700/35 bg-amber-500/[0.08] px-2 py-2 text-[11px] leading-snug text-amber-950 dark:border-amber-700/55 dark:bg-amber-950/35 dark:text-amber-50">
                Some related-source candidates were not registered or resolved as covered by existing
                sources. They will not be analysed unless you register concrete instruments first.
              </div>
            ) : null}
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
              <label className="space-y-1">
                <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  Topic name
                </span>
                <input
                  type="text"
                  value={runFromRegistryTopicName}
                  onChange={(event) => setRunFromRegistryTopicName(event.target.value)}
                  className="h-8 w-full rounded border border-border/80 bg-background px-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                />
              </label>
              <label className="space-y-1">
                <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  Cluster name
                </span>
                <input
                  type="text"
                  value={runFromRegistryClusterName}
                  onChange={(event) => setRunFromRegistryClusterName(event.target.value)}
                  placeholder="optional"
                  className="h-8 w-full rounded border border-border/80 bg-background px-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                />
              </label>
              <label className="space-y-1">
                <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  Analysis mode
                </span>
                <select
                  value={runFromRegistryAnalysisMode}
                  onChange={(event) => setRunFromRegistryAnalysisMode(event.target.value)}
                  className="h-8 w-full rounded border border-border/80 bg-background px-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                >
                  <option value="auto">auto</option>
                  <option value="divergence">divergence</option>
                  <option value="single_jurisdiction">single_jurisdiction</option>
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  Analysis scope
                </span>
                <select
                  value={runFromRegistryAnalysisScope}
                  onChange={(event) => setRunFromRegistryAnalysisScope(event.target.value)}
                  className="h-8 w-full rounded border border-border/80 bg-background px-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                >
                  <option value="selected_sources">Selected sources (exact tick list)</option>
                  <option value="eu">EU only</option>
                  <option value="uk">UK only</option>
                  <option value="eu_uk">EU + UK (from selection)</option>
                </select>
              </label>
            </div>
            {selectedRegistryIdsForRun.length > 0 ? (
              <p className="text-[11px] text-muted-foreground">
                <span className="font-medium text-foreground">Selected for run:</span> 🇪🇺 EU:{" "}
                {selectedRunJurisdictionCounts.eu} · 🇬🇧 UK: {selectedRunJurisdictionCounts.uk}
                {selectedRunJurisdictionCounts.other > 0
                  ? ` · other: ${selectedRunJurisdictionCounts.other}`
                  : ""}
              </p>
            ) : null}
            <p className="text-[10px] leading-snug text-muted-foreground">
              <span className="font-medium text-foreground/90">Terms:</span> an{" "}
              <span className="font-medium">analysis run</span> produces one{" "}
              <span className="font-medium">proposition dataset</span> (extraction). A{" "}
              <span className="font-medium">comparison run</span> pairs two existing datasets for
              divergences (separate panel below) and does not re-extract.
            </p>
            <label className="block space-y-1">
              <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                Topic subject tags (optional, comma-separated)
              </span>
              <input
                type="text"
                value={runFromRegistrySubjectTags}
                onChange={(event) => setRunFromRegistrySubjectTags(event.target.value)}
                placeholder="e.g. equine, animal health"
                className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
              />
            </label>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={runFromRegistryQualityRun}
                onChange={(event) => {
                  const on = event.target.checked;
                  setRunFromRegistryQualityRun(on);
                  if (on) {
                    setRunFromRegistryExtractionMode("frontier");
                    setRunFromRegistryExtractionFallback("mark_needs_review");
                    setRunFromRegistryDivergenceReasoning("frontier");
                    setRunFromRegistryMaxPropositions("12");
                    setRunFromRegistryFocusScopesText(
                      equineFocusScopesDefaultText(
                        runFromRegistryTopicName,
                        runFromRegistrySubjectTags
                      )
                    );
                  } else {
                    setRunFromRegistryExtractionMode("");
                    setRunFromRegistryExtractionFallback("");
                    setRunFromRegistryDivergenceReasoning("");
                    setRunFromRegistryFocusScopesText("");
                    setRunFromRegistryMaxPropositions("");
                  }
                }}
                className="h-3.5 w-3.5 rounded border-border"
              />
              <span>Quality run (export-case-style profile: frontier extraction, review fallback)</span>
            </label>
            <details className="rounded border border-border/60 bg-muted/20 px-2 py-1.5">
              <summary className="cursor-pointer text-[11px] font-medium text-muted-foreground">
                Advanced extraction
              </summary>
              <div className="mt-2 grid gap-2 md:grid-cols-2">
                <label className="space-y-1">
                  <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    Extraction mode
                  </span>
                  <select
                    value={runFromRegistryExtractionMode}
                    onChange={(event) => setRunFromRegistryExtractionMode(event.target.value)}
                    className="h-8 w-full rounded border border-border/80 bg-background px-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                  >
                    <option value="">pipeline default</option>
                    <option value="heuristic">heuristic</option>
                    <option value="local">local</option>
                    <option value="frontier">frontier</option>
                  </select>
                </label>
                <label className="space-y-1">
                  <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    Extraction fallback
                  </span>
                  <select
                    value={runFromRegistryExtractionFallback}
                    onChange={(event) => setRunFromRegistryExtractionFallback(event.target.value)}
                    className="h-8 w-full rounded border border-border/80 bg-background px-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                  >
                    <option value="">pipeline default</option>
                    <option value="fallback">fallback</option>
                    <option value="mark_needs_review">mark_needs_review</option>
                    <option value="fail_closed">fail_closed</option>
                  </select>
                </label>
                <label className="space-y-1">
                  <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    Execution mode
                  </span>
                  <select
                    value={runFromRegistryExtractionExecutionMode}
                    onChange={(event) =>
                      setRunFromRegistryExtractionExecutionMode(event.target.value)
                    }
                    className="h-8 w-full rounded border border-border/80 bg-background px-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                  >
                    <option value="">pipeline default (interactive)</option>
                    <option value="interactive">interactive</option>
                    <option value="batch">batch / async cheaper</option>
                  </select>
                </label>
                <label className="space-y-1 md:col-span-2">
                  <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    Divergence reasoning
                  </span>
                  <select
                    value={runFromRegistryDivergenceReasoning}
                    onChange={(event) => setRunFromRegistryDivergenceReasoning(event.target.value)}
                    className="h-8 w-full rounded border border-border/80 bg-background px-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                  >
                    <option value="">pipeline default</option>
                    <option value="none">none</option>
                    <option value="frontier">frontier</option>
                  </select>
                </label>
                <label className="space-y-1 md:col-span-2">
                  <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    Focus scopes (comma-separated)
                  </span>
                  <input
                    type="text"
                    value={runFromRegistryFocusScopesText}
                    onChange={(event) => setRunFromRegistryFocusScopesText(event.target.value)}
                    placeholder="Leave empty to use quality defaults or none"
                    className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                  />
                </label>
                <label className="space-y-1 md:col-span-2">
                  <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    Max propositions per source
                  </span>
                  <input
                    type="number"
                    min={1}
                    value={runFromRegistryMaxPropositions}
                    onChange={(event) => setRunFromRegistryMaxPropositions(event.target.value)}
                    placeholder="default 4, quality preset 12"
                    className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                  />
                </label>
              </div>
            </details>
            <div className="text-xs text-muted-foreground">
              Selected registry IDs:{" "}
              {selectedRegistryIdsForRun.length > 0 ? selectedRegistryIdsForRun.join(", ") : "none"}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void handleRunFromRegistry()}
                disabled={isRunningFromRegistry}
                className="rounded border border-priguidance-discovery/60 bg-priguidance-discovery/[0.1] px-3 py-1.5 text-xs font-medium transition-colors hover:bg-priguidance-discovery/[0.18] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isRunningFromRegistry
                  ? "Starting run..."
                  : "Run analysis from selected registry sources"}
              </button>
              {runFromRegistrySuccess ? (
                <span className="text-xs text-emerald-700">{runFromRegistrySuccess}</span>
              ) : null}
              {registryRunJobPollError ? (
                <span className="text-xs text-destructive">Poll: {registryRunJobPollError}</span>
              ) : null}
              {runFromRegistryError ? (
                <span className="text-xs text-destructive">{runFromRegistryError}</span>
              ) : null}
            </div>
            {registryRunJobId ? (
              <RegistryRunProgressPanel job={registryRunJob} events={registryRunJobEvents} />
            ) : null}
          </CardContent>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Compare existing proposition datasets</CardTitle>
            <CardDescription>
              Runs a <span className="font-medium">comparison run</span> on two exported analysis
              runs — divergence/pairing only, <span className="font-medium">no</span> proposition
              extraction. Open{" "}
              <a
                href="/propositions?jview=divergences"
                className="font-medium text-primary underline-offset-2 hover:underline"
              >
                Propositions → Divergences
              </a>{" "}
              on the new run when complete.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap items-end gap-3">
            <label className="space-y-1">
              <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                Dataset A (run id)
              </span>
              <select
                value={compareLeftRunId}
                onChange={(e) => setCompareLeftRunId(e.target.value)}
                className="h-8 min-w-[14rem] rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary"
              >
                <option value="">Select run…</option>
                {filteredRuns.map((r) => (
                  <option key={`cmp-l-${r.run_id}`} value={r.run_id}>
                    {r.run_id}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                Dataset B (run id)
              </span>
              <select
                value={compareRightRunId}
                onChange={(e) => setCompareRightRunId(e.target.value)}
                className="h-8 min-w-[14rem] rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary"
              >
                <option value="">Select run…</option>
                {filteredRuns.map((r) => (
                  <option key={`cmp-r-${r.run_id}`} value={r.run_id}>
                    {r.run_id}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => void handleComparePropositionDatasets()}
              disabled={compareBusy || filteredRuns.length < 2}
              className="rounded border border-priguidance-discovery/60 bg-priguidance-discovery/[0.1] px-3 py-1.5 text-xs font-medium transition-colors hover:bg-priguidance-discovery/[0.18] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {compareBusy ? "Queueing…" : "Run comparison"}
            </button>
            {compareSuccess ? (
              <span className="text-xs font-medium text-emerald-700">{compareSuccess}</span>
            ) : null}
            {compareError ? (
              <span className="text-xs text-destructive">{compareError}</span>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Runs</CardTitle>
            <CardDescription>Select a run to inspect details and audit artifacts.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <input
              type="search"
              value={runSearch}
              onChange={(event) => setRunSearch(event.target.value)}
              placeholder="Filter runs by id/mode/date..."
              className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
            />
            {isRunsLoading ? (
              <p className="text-sm text-muted-foreground">Loading runs...</p>
            ) : null}
            {runsError ? (
              <p className="text-sm text-destructive">
                Failed to load runs: <code>{runsError}</code>
              </p>
            ) : null}
            {!isRunsLoading && !runsError && filteredRuns.length === 0 ? (
              <p className="text-sm text-muted-foreground">No exported runs found.</p>
            ) : null}
            {filteredRuns.map((run) => (
              <button
                key={run.run_id}
                type="button"
                onClick={() => setSelectedRunId(run.run_id)}
                className={`w-full rounded border px-2 py-2 text-left text-xs transition-colors ${
                  selectedRunId === run.run_id
                    ? "border-primary bg-priguidance-discovery/[0.1]"
                    : "border-border/70 bg-background hover:bg-accent/40"
                }`}
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className={META_CHIP_CLASS}>{run.run_id}</span>
                  <span className={META_CHIP_CLASS}>mode: {toText(run.workflow_mode)}</span>
                  <span className={META_CHIP_CLASS}>traces: {toText(run.stage_trace_count)}</span>
                  <span className={META_CHIP_CLASS}>
                    decisions: {toText(run.divergence_assessment_count)}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-foreground/70">
                  created: {formatDateTime(run.created_at)} | propositions:{" "}
                  {toText(run.proposition_count)} | artifacts: {toText(run.artifact_count)}
                </p>
              </button>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Run detail</CardTitle>
            <CardDescription>
              Manifest and run payload for <code>{selectedRunId ?? "—"}</code>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {isRunDetailLoading ? (
              <p className="text-sm text-muted-foreground">Loading run detail...</p>
            ) : null}
            {runDetailError ? (
              <p className="text-sm text-destructive">
                Failed to load run detail: <code>{runDetailError}</code>
              </p>
            ) : null}
            {runDetail ? (
              <div className="space-y-2">
                <div className="grid gap-2 sm:grid-cols-2">
                  <FieldRow label="Run id" value={runRecord.id} />
                  <FieldRow label="Created at" value={formatDateTime(runRecord.created_at)} />
                  <FieldRow label="Workflow mode" value={runRecord.workflow_mode} />
                  <FieldRow label="Model profile" value={runRecord.model_profile} />
                  <FieldRow label="Topic id" value={runRecord.topic_id} />
                  <FieldRow label="Cluster id" value={runRecord.cluster_id} />
                  <FieldRow label="Source records" value={runSourceRecordIds(runRecord).length} />
                  <FieldRow
                    label="Source snapshots"
                    value={
                      Array.isArray(runRecord.source_snapshot_ids)
                        ? runRecord.source_snapshot_ids.length
                        : "0"
                    }
                  />
                  <FieldRow
                    label="Source fragments"
                    value={
                      Array.isArray(runRecord.source_fragment_ids)
                        ? runRecord.source_fragment_ids.length
                        : "0"
                    }
                  />
                  <FieldRow
                    label="Review decisions"
                    value={
                      Array.isArray(runRecord.review_decision_ids)
                        ? runRecord.review_decision_ids.length
                        : "0"
                    }
                  />
                </div>
                <details className="rounded border border-border/70 p-2">
                  <summary className="cursor-pointer text-xs font-medium">Manifest summary</summary>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    <FieldRow label="Artifact count" value={runManifest.artifact_count} />
                    <FieldRow label="Stage trace count" value={runManifest.stage_trace_count} />
                    <FieldRow label="Proposition count" value={runManifest.proposition_count} />
                    <FieldRow
                      label="Divergence assessment count"
                      value={runManifest.divergence_assessment_count}
                    />
                    <FieldRow label="Trace manifest uri" value={runManifest.trace_manifest_uri} />
                    <FieldRow label="Trace stage count" value={runTraceManifest.stage_count} />
                  </div>
                </details>
                <details className="rounded border border-border/70 p-2">
                  <summary className="cursor-pointer text-xs font-medium">
                    Raw run detail JSON
                  </summary>
                  <div className="mt-2">
                    <JsonBlock payload={runDetail} />
                  </div>
                </details>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <div className="md:col-span-2 pt-1">
          <p className="text-sm text-muted-foreground">
            Audit details are available below for traceability and debugging.
          </p>
        </div>

        <AuditPanelCollapsible
          className="md:col-span-2"
          title="Stage traces"
          description="Stage-by-stage trace payloads for selected run."
        >
            <input
              type="search"
              value={traceSearch}
              onChange={(event) => setTraceSearch(event.target.value)}
              placeholder="Filter traces by stage/strategy/model..."
              className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
            />
            {isTracesLoading ? (
              <p className="text-sm text-muted-foreground">Loading traces...</p>
            ) : null}
            {tracesError ? (
              <p className="text-sm text-destructive">
                Failed to load traces: <code>{tracesError}</code>
              </p>
            ) : null}
            {!isTracesLoading && !tracesError && filteredTraces.length === 0 ? (
              <p className="text-sm text-muted-foreground">No traces available for this run.</p>
            ) : null}
            {filteredTraces.map((trace) => {
              const traceRecord = asRecord(trace.trace) ?? {};
              const warnings = Array.isArray(traceRecord.warnings) ? traceRecord.warnings : [];
              const errors = Array.isArray(traceRecord.errors) ? traceRecord.errors : [];
              const inputs = asRecord(traceRecord.inputs) ?? {};
              const outputs = asRecord(traceRecord.outputs) ?? {};
              return (
                <details
                  key={`${trace.order}-${trace.stage_name}`}
                  className="rounded border border-border/70"
                >
                  <summary className="cursor-pointer px-2 py-2 text-sm">
                    <span className={META_CHIP_CLASS}>{toText(trace.order)}</span>
                    <span className={`${META_CHIP_CLASS} ml-1`}>{toText(trace.stage_name)}</span>
                    <span className={`${META_CHIP_CLASS} ml-1`}>
                      duration: {toText(traceRecord.duration_ms)}ms
                    </span>
                    <span className={`${META_CHIP_CLASS} ml-1`}>
                      warnings: {warnings.length} | errors: {errors.length}
                    </span>
                  </summary>
                  <div className="space-y-2 px-2 pb-2">
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      <FieldRow label="Timestamp" value={formatDateTime(traceRecord.timestamp)} />
                      <FieldRow label="Strategy" value={traceRecord.strategy_used} />
                      <FieldRow label="Model alias" value={traceRecord.model_alias_used} />
                      <FieldRow label="Storage URI" value={trace.storage_uri} />
                      <FieldRow label="Input keys" value={Object.keys(inputs).join(", ")} />
                      <FieldRow label="Output keys" value={Object.keys(outputs).join(", ")} />
                    </div>
                    {warnings.length > 0 ? (
                      <div className="rounded border border-amber-500/40 bg-amber-500/5 p-2">
                        <p className="text-[11px] uppercase tracking-wide text-amber-700">
                          Warnings
                        </p>
                        <ul className="mt-1 list-disc space-y-1 pl-4 text-xs">
                          {warnings.map((warning, idx) => (
                            <li key={`warning-${idx}`}>{toText(warning)}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {errors.length > 0 ? (
                      <div className="rounded border border-destructive/40 bg-destructive/[0.06] p-2">
                        <p className="text-[11px] uppercase tracking-wide text-destructive">
                          Errors
                        </p>
                        <ul className="mt-1 list-disc space-y-1 pl-4 text-xs">
                          {errors.map((error, idx) => (
                            <li key={`error-${idx}`}>{toText(error)}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    <details className="rounded border border-border/70 p-2">
                      <summary className="cursor-pointer text-xs font-medium">
                        Raw trace JSON
                      </summary>
                      <div className="mt-2">
                        <JsonBlock payload={trace.trace ?? {}} />
                      </div>
                    </details>
                  </div>
                </details>
              );
            })}
            {traceManifestStages.length > 0 ? (
              <details className="rounded border border-border/70 p-2">
                <summary className="cursor-pointer text-xs font-medium">
                  Raw trace manifest JSON
                </summary>
                <div className="mt-2">
                  <JsonBlock payload={runTraceManifest} />
                </div>
              </details>
            ) : null}
        </AuditPanelCollapsible>

        <AuditPanelCollapsible
          className="md:col-span-2"
          title="Review decisions"
          description="Read-only decision ledger for selected run."
        >
            <input
              type="search"
              value={decisionSearch}
              onChange={(event) => setDecisionSearch(event.target.value)}
              placeholder="Filter decisions by target/status/reviewer..."
              className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
            />
            {isReviewDecisionsLoading ? (
              <p className="text-sm text-muted-foreground">Loading review decisions...</p>
            ) : null}
            {reviewDecisionsError ? (
              <p className="text-sm text-destructive">
                Failed to load review decisions: <code>{reviewDecisionsError}</code>
              </p>
            ) : null}
            {!isReviewDecisionsLoading &&
            !reviewDecisionsError &&
            filteredReviewDecisions.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No review decisions found for this run.
              </p>
            ) : null}
            {filteredReviewDecisions.map((decision) => (
              <details
                key={toText(decision.id, JSON.stringify(decision))}
                className="rounded border border-border/70"
              >
                <summary className="cursor-pointer px-2 py-2 text-sm">
                  <span className={META_CHIP_CLASS}>{toText(decision.id)}</span>
                  <span className={`${META_CHIP_CLASS} ml-1`}>
                    {toText(decision.target_type)}:{toText(decision.target_id)}
                  </span>
                  <span className={`${META_CHIP_CLASS} ml-1`}>
                    {toText(decision.previous_status)} -&gt; {toText(decision.new_status)}
                  </span>
                </summary>
                <div className="space-y-2 px-2 pb-2">
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    <FieldRow label="Reviewer" value={decision.reviewer} />
                    <FieldRow label="Timestamp" value={formatDateTime(decision.timestamp)} />
                    <FieldRow label="Decision status" value={decision.new_status} />
                    <FieldRow label="Target type" value={decision.target_type} />
                    <FieldRow label="Target id" value={decision.target_id} />
                    <FieldRow
                      label="Has edited fields"
                      value={asRecord(decision.edited_fields) ? "yes" : "no"}
                    />
                  </div>
                  <div className="rounded border border-border/70 bg-muted/20 p-2">
                    <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                      Note
                    </p>
                    <p className="mt-1 whitespace-pre-wrap text-sm">{toText(decision.note)}</p>
                  </div>
                  <details className="rounded border border-border/70 p-2">
                    <summary className="cursor-pointer text-xs font-medium">
                      Raw decision JSON
                    </summary>
                    <div className="mt-2">
                      <JsonBlock payload={decision} />
                    </div>
                  </details>
                </div>
              </details>
            ))}
            {reviewDecisions.length > 0 ? (
              <details className="rounded border border-border/70 p-2">
                <summary className="cursor-pointer text-xs font-medium">
                  Raw review decisions list JSON
                </summary>
                <div className="mt-2">
                  <JsonBlock payload={reviewDecisions} />
                </div>
              </details>
            ) : null}
        </AuditPanelCollapsible>

        <AuditPanelCollapsible
          className="md:col-span-2"
          title="Proposition history inspector"
          description={
            <>
              Read-only proposition history from{" "}
              <code>/ops/propositions/{"{proposition_key}"}/history</code>.
            </>
          }
        >
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-2 rounded border border-border/70 bg-muted/20 p-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Select proposition key from current run
                </p>
                <input
                  type="search"
                  value={propositionSearch}
                  onChange={(event) => setPropositionSearch(event.target.value)}
                  placeholder="Filter proposition keys by key/version/subject/action..."
                  className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                />
                {isRunPropositionsLoading ? (
                  <p className="text-sm text-muted-foreground">Loading run propositions...</p>
                ) : null}
                {runPropositionsError ? (
                  <p className="text-sm text-destructive">
                    Failed to load propositions: <code>{runPropositionsError}</code>
                  </p>
                ) : null}
                {!isRunPropositionsLoading &&
                !runPropositionsError &&
                filteredRunPropositions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No proposition candidates for selected run.
                  </p>
                ) : null}
                <div className="max-h-56 space-y-1 overflow-auto pr-1">
                  {filteredRunPropositions.map((proposition) => {
                    const propositionKey = toText(proposition.proposition_key, "");
                    const selected =
                      propositionKey && selectedPropositionKey.trim() === propositionKey;
                    return (
                      <button
                        key={`${propositionKey}-${toText(proposition.proposition_version_id)}-${toText(proposition.id)}`}
                        type="button"
                        onClick={() => setSelectedPropositionKey(propositionKey)}
                        className={`w-full rounded border px-2 py-1.5 text-left text-xs transition-colors ${
                          selected
                            ? "border-primary bg-priguidance-discovery/[0.1]"
                            : "border-border/70 bg-background hover:bg-accent/40"
                        }`}
                      >
                        <div className="flex flex-wrap gap-1.5">
                          <span className={META_CHIP_CLASS}>{propositionKey || "—"}</span>
                          <span className={META_CHIP_CLASS}>
                            version: {toText(proposition.proposition_version_id)}
                          </span>
                          <span className={META_CHIP_CLASS}>
                            run: {toText(proposition.observed_in_run_id)}
                          </span>
                        </div>
                        <p className="mt-0.5 text-[11px] text-foreground/75">
                          {toText(proposition.legal_subject)} | {toText(proposition.action)}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-2 rounded border border-border/70 bg-muted/20 p-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Inspect by proposition key
                </p>
                <input
                  type="text"
                  value={selectedPropositionKey}
                  onChange={(event) => setSelectedPropositionKey(event.target.value)}
                  placeholder="Enter proposition_key..."
                  className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                />
                <p className="text-xs text-muted-foreground">
                  Selected proposition key:{" "}
                  <code>{selectedPropositionKey.trim() ? selectedPropositionKey.trim() : "—"}</code>
                </p>
                {isPropositionHistoryLoading ? (
                  <p className="text-sm text-muted-foreground">Loading proposition history...</p>
                ) : null}
                {propositionHistoryError ? (
                  <p className="text-sm text-destructive">
                    Failed to load proposition history: <code>{propositionHistoryError}</code>
                  </p>
                ) : null}
              </div>
            </div>

            {propositionHistory ? (
              <div className="space-y-2 rounded border border-border/70 bg-muted/20 p-2">
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  <FieldRow label="Proposition key" value={propositionHistory.proposition_key} />
                  <FieldRow
                    label="Observed versions"
                    value={propositionHistory.observed_version_count}
                  />
                  <FieldRow
                    label="Runs scanned"
                    value={
                      Array.isArray(propositionHistory.run_ids_scanned)
                        ? propositionHistory.run_ids_scanned.length
                        : 0
                    }
                  />
                  <FieldRow label="Scope" value={propositionHistory.scope} />
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {(Array.isArray(propositionHistory.run_ids_scanned)
                    ? propositionHistory.run_ids_scanned
                    : []
                  ).map((runId) => (
                    <span key={runId} className={META_CHIP_CLASS}>
                      {runId}
                    </span>
                  ))}
                </div>

                <details className="rounded border border-border/70 p-2" open>
                  <summary className="cursor-pointer text-xs font-medium">
                    Observed versions
                  </summary>
                  <div className="mt-2 space-y-2">
                    <input
                      type="search"
                      value={propositionVersionSearch}
                      onChange={(event) => setPropositionVersionSearch(event.target.value)}
                      placeholder="Filter observed versions by run/snapshot/version/signal/subject/action/text..."
                      className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                    />
                    {filteredPropositionHistoryObservedVersions.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No observed versions for this proposition key.
                      </p>
                    ) : null}
                    {filteredPropositionHistoryObservedVersions.map((version) => (
                      <details
                        key={`${toText(version.proposition_version_id)}-${toText(version.source_snapshot_id)}-${toText(version.observed_in_run_id)}-${toText(version.proposition_id)}`}
                        className="rounded border border-border/70"
                      >
                        <summary className="cursor-pointer px-2 py-2 text-sm">
                          <span className={META_CHIP_CLASS}>{toText(version.proposition_key)}</span>
                          <span className={`${META_CHIP_CLASS} ml-1`}>
                            version: {toText(version.proposition_version_id)}
                          </span>
                          <span className={`${META_CHIP_CLASS} ml-1`}>
                            run: {toText(version.observed_in_run_id)}
                          </span>
                          <span className={`${META_CHIP_CLASS} ml-1`}>
                            snapshot: {toText(version.source_snapshot_id)}
                          </span>
                          <span className={`${META_CHIP_CLASS} ml-1`}>
                            signal: {toText(version.previous_version_signal)}
                          </span>
                        </summary>
                        <div className="space-y-2 px-2 pb-2">
                          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                            <FieldRow label="proposition_key" value={version.proposition_key} />
                            <FieldRow
                              label="proposition_version_id"
                              value={version.proposition_version_id}
                            />
                            <FieldRow label="source_record_id" value={version.source_record_id} />
                            <FieldRow
                              label="source_snapshot_id"
                              value={version.source_snapshot_id}
                            />
                            <FieldRow
                              label="observed_in_run_id"
                              value={version.observed_in_run_id}
                            />
                            <FieldRow
                              label="observed_at"
                              value={formatDateTime(version.observed_at)}
                            />
                            <FieldRow label="article_reference" value={version.article_reference} />
                            <FieldRow label="fragment_locator" value={version.fragment_locator} />
                            <FieldRow label="legal_subject" value={version.legal_subject} />
                            <FieldRow label="action" value={version.action} />
                            <FieldRow
                              label="previous_version_signal"
                              value={version.previous_version_signal}
                            />
                          </div>
                          <details className="rounded border border-border/70 p-2">
                            <summary className="cursor-pointer text-xs font-medium">
                              Proposition text
                            </summary>
                            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">
                              {toText(version.proposition_text)}
                            </p>
                          </details>
                          <details className="rounded border border-border/70 p-2">
                            <summary className="cursor-pointer text-xs font-medium">
                              Previous-version comparison JSON
                            </summary>
                            <div className="mt-2">
                              <JsonBlock payload={version.previous_version_comparison ?? {}} />
                            </div>
                          </details>
                        </div>
                      </details>
                    ))}
                  </div>
                </details>

                <details className="rounded border border-border/70 p-2">
                  <summary className="cursor-pointer text-xs font-medium">Grouped by run</summary>
                  <div className="mt-2 space-y-2">
                    {propositionHistoryVersionsByRun.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No run groupings returned.</p>
                    ) : null}
                    {propositionHistoryVersionsByRun.map((group) => {
                      const versions = Array.isArray(group.observed_versions)
                        ? group.observed_versions
                        : [];
                      return (
                        <details
                          key={toText(group.observed_in_run_id)}
                          className="rounded border border-border/70"
                        >
                          <summary className="cursor-pointer px-2 py-2 text-sm">
                            <span className={META_CHIP_CLASS}>
                              run: {toText(group.observed_in_run_id)}
                            </span>
                            <span className={`${META_CHIP_CLASS} ml-1`}>
                              versions: {toText(group.observed_version_count)}
                            </span>
                          </summary>
                          <div className="space-y-1 px-2 pb-2">
                            {versions.map((version) => (
                              <div
                                key={`${toText(group.observed_in_run_id)}-${toText(version.proposition_version_id)}-${toText(version.source_snapshot_id)}-${toText(version.proposition_id)}`}
                                className="rounded border border-border/70 bg-background px-2 py-1.5 text-xs"
                              >
                                <span className={META_CHIP_CLASS}>
                                  {toText(version.proposition_version_id)}
                                </span>
                                <span className={`${META_CHIP_CLASS} ml-1`}>
                                  {toText(version.source_snapshot_id)}
                                </span>
                                <span className={`${META_CHIP_CLASS} ml-1`}>
                                  {toText(version.previous_version_signal)}
                                </span>
                                <p className="mt-1 text-[11px] text-foreground/75">
                                  {toText(version.legal_subject)} | {toText(version.action)}
                                </p>
                              </div>
                            ))}
                          </div>
                        </details>
                      );
                    })}
                  </div>
                </details>

                <details className="rounded border border-border/70 p-2">
                  <summary className="cursor-pointer text-xs font-medium">
                    Grouped by snapshot
                  </summary>
                  <div className="mt-2 space-y-2">
                    {propositionHistoryVersionsBySnapshot.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No snapshot groupings returned.
                      </p>
                    ) : null}
                    {propositionHistoryVersionsBySnapshot.map((group) => {
                      const versions = Array.isArray(group.observed_versions)
                        ? group.observed_versions
                        : [];
                      return (
                        <details
                          key={toText(group.source_snapshot_id)}
                          className="rounded border border-border/70"
                        >
                          <summary className="cursor-pointer px-2 py-2 text-sm">
                            <span className={META_CHIP_CLASS}>
                              snapshot: {toText(group.source_snapshot_id)}
                            </span>
                            <span className={`${META_CHIP_CLASS} ml-1`}>
                              versions: {toText(group.observed_version_count)}
                            </span>
                          </summary>
                          <div className="space-y-1 px-2 pb-2">
                            {versions.map((version) => (
                              <div
                                key={`${toText(group.source_snapshot_id)}-${toText(version.proposition_version_id)}-${toText(version.observed_in_run_id)}-${toText(version.proposition_id)}`}
                                className="rounded border border-border/70 bg-background px-2 py-1.5 text-xs"
                              >
                                <span className={META_CHIP_CLASS}>
                                  {toText(version.proposition_version_id)}
                                </span>
                                <span className={`${META_CHIP_CLASS} ml-1`}>
                                  run: {toText(version.observed_in_run_id)}
                                </span>
                                <span className={`${META_CHIP_CLASS} ml-1`}>
                                  {toText(version.previous_version_signal)}
                                </span>
                                <p className="mt-1 text-[11px] text-foreground/75">
                                  {toText(version.legal_subject)} | {toText(version.action)}
                                </p>
                              </div>
                            ))}
                          </div>
                        </details>
                      );
                    })}
                  </div>
                </details>

                <details className="rounded border border-border/70 p-2">
                  <summary className="cursor-pointer text-xs font-medium">
                    Raw proposition history JSON
                  </summary>
                  <div className="mt-2">
                    <JsonBlock payload={propositionHistory} />
                  </div>
                </details>
              </div>
            ) : null}
        </AuditPanelCollapsible>

        <AuditPanelCollapsible
          className="md:col-span-2"
          title="Divergence history inspector"
          description={
            <>
              Read-only divergence history from{" "}
              <code>/ops/divergence-findings/{"{finding_id}"}/history</code>.
            </>
          }
        >
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-2 rounded border border-border/70 bg-muted/20 p-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Select finding id from current run
                </p>
                <input
                  type="search"
                  value={divergenceSearch}
                  onChange={(event) => setDivergenceSearch(event.target.value)}
                  placeholder="Filter findings by id/type/status/confidence..."
                  className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                />
                {isRunDivergenceAssessmentsLoading ? (
                  <p className="text-sm text-muted-foreground">
                    Loading run divergence findings...
                  </p>
                ) : null}
                {runDivergenceAssessmentsError ? (
                  <p className="text-sm text-destructive">
                    Failed to load divergence assessments:{" "}
                    <code>{runDivergenceAssessmentsError}</code>
                  </p>
                ) : null}
                {!isRunDivergenceAssessmentsLoading &&
                !runDivergenceAssessmentsError &&
                filteredRunDivergenceAssessments.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No divergence findings for selected run.
                  </p>
                ) : null}
                <div className="max-h-56 space-y-1 overflow-auto pr-1">
                  {filteredRunDivergenceAssessments.map((assessment) => {
                    const findingId = divergenceFindingId(assessment);
                    const selected = findingId && selectedFindingId.trim() === findingId;
                    return (
                      <button
                        key={`${findingId}-${toText(assessment.id)}-${toText(assessment.proposition_id)}-${toText(assessment.comparator_proposition_id)}`}
                        type="button"
                        onClick={() => setSelectedFindingId(findingId)}
                        className={`w-full rounded border px-2 py-1.5 text-left text-xs transition-colors ${
                          selected
                            ? "border-primary bg-priguidance-discovery/[0.1]"
                            : "border-border/70 bg-background hover:bg-accent/40"
                        }`}
                      >
                        <div className="flex flex-wrap gap-1.5">
                          <span className={META_CHIP_CLASS}>{findingId || "—"}</span>
                          <span className={META_CHIP_CLASS}>
                            type: {toText(assessment.divergence_type)}
                          </span>
                          <span className={META_CHIP_CLASS}>
                            status: {toText(assessment.review_status)}
                          </span>
                          <span className={META_CHIP_CLASS}>
                            confidence: {toText(assessment.confidence)}
                          </span>
                        </div>
                        <p className="mt-0.5 text-[11px] text-foreground/75">
                          {toText(assessment.proposition_id)} vs{" "}
                          {toText(assessment.comparator_proposition_id)}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-2 rounded border border-border/70 bg-muted/20 p-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Inspect by finding id
                </p>
                <input
                  type="text"
                  value={selectedFindingId}
                  onChange={(event) => setSelectedFindingId(event.target.value)}
                  placeholder="Enter finding_id..."
                  className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                />
                <p className="text-xs text-muted-foreground">
                  Selected finding id:{" "}
                  <code>{selectedFindingId.trim() ? selectedFindingId.trim() : "—"}</code>
                </p>
                {isDivergenceHistoryLoading ? (
                  <p className="text-sm text-muted-foreground">Loading divergence history...</p>
                ) : null}
                {divergenceHistoryError ? (
                  <p className="text-sm text-destructive">
                    Failed to load divergence history: <code>{divergenceHistoryError}</code>
                  </p>
                ) : null}
              </div>
            </div>

            {divergenceHistory ? (
              <div className="space-y-2 rounded border border-border/70 bg-muted/20 p-2">
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  <FieldRow label="Finding id" value={divergenceHistory.finding_id} />
                  <FieldRow
                    label="Observed versions"
                    value={divergenceHistory.observed_version_count}
                  />
                  <FieldRow
                    label="Runs scanned"
                    value={
                      Array.isArray(divergenceHistory.run_ids_scanned)
                        ? divergenceHistory.run_ids_scanned.length
                        : 0
                    }
                  />
                  <FieldRow label="Scope" value={divergenceHistory.scope} />
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {(Array.isArray(divergenceHistory.run_ids_scanned)
                    ? divergenceHistory.run_ids_scanned
                    : []
                  ).map((runId) => (
                    <span key={runId} className={META_CHIP_CLASS}>
                      {runId}
                    </span>
                  ))}
                </div>

                <details className="rounded border border-border/70 p-2" open>
                  <summary className="cursor-pointer text-xs font-medium">
                    Observed versions
                  </summary>
                  <div className="mt-2 space-y-2">
                    <input
                      type="search"
                      value={divergenceVersionSearch}
                      onChange={(event) => setDivergenceVersionSearch(event.target.value)}
                      placeholder="Filter observed versions by run/snapshot/type/status/confidence/signal..."
                      className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
                    />
                    {filteredDivergenceHistoryObservedVersions.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No observed versions for this finding id.
                      </p>
                    ) : null}
                    {filteredDivergenceHistoryObservedVersions.map((version) => (
                      <details
                        key={`${toText(version.finding_id)}-${toText(version.observation_id)}-${toText(version.version_identity)}`}
                        className="rounded border border-border/70"
                      >
                        <summary className="cursor-pointer px-2 py-2 text-sm">
                          <span className={META_CHIP_CLASS}>{toText(version.finding_id)}</span>
                          <span className={`${META_CHIP_CLASS} ml-1`}>
                            observation: {toText(version.observation_id)}
                          </span>
                          <span className={`${META_CHIP_CLASS} ml-1`}>
                            run: {toText(version.observed_in_run_id)}
                          </span>
                          <span className={`${META_CHIP_CLASS} ml-1`}>
                            type: {toText(version.divergence_type)}
                          </span>
                          <span className={`${META_CHIP_CLASS} ml-1`}>
                            signal: {toText(version.previous_version_signal)}
                          </span>
                        </summary>
                        <div className="space-y-2 px-2 pb-2">
                          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                            <FieldRow label="finding_id" value={version.finding_id} />
                            <FieldRow label="observation_id" value={version.observation_id} />
                            <FieldRow label="version_identity" value={version.version_identity} />
                            <FieldRow
                              label="observed_in_run_id"
                              value={version.observed_in_run_id}
                            />
                            <FieldRow
                              label="observed_at"
                              value={formatDateTime(version.observed_at)}
                            />
                            <FieldRow label="divergence_type" value={version.divergence_type} />
                            <FieldRow label="confidence" value={version.confidence} />
                            <FieldRow label="review_status" value={version.review_status} />
                            <FieldRow
                              label="previous_version_signal"
                              value={version.previous_version_signal}
                            />
                            <FieldRow
                              label="source_record_ids"
                              value={
                                Array.isArray(version.source_record_ids)
                                  ? version.source_record_ids.join(", ")
                                  : "—"
                              }
                            />
                            <FieldRow
                              label="source_snapshot_ids"
                              value={
                                Array.isArray(version.source_snapshot_ids)
                                  ? version.source_snapshot_ids.join(", ")
                                  : "—"
                              }
                            />
                          </div>
                          <details className="rounded border border-border/70 p-2">
                            <summary className="cursor-pointer text-xs font-medium">
                              Rationale
                            </summary>
                            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">
                              {toText(version.rationale)}
                            </p>
                          </details>
                          <details className="rounded border border-border/70 p-2">
                            <summary className="cursor-pointer text-xs font-medium">
                              Operational impact
                            </summary>
                            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">
                              {toText(version.operational_impact)}
                            </p>
                          </details>
                          <details className="rounded border border-border/70 p-2">
                            <summary className="cursor-pointer text-xs font-medium">
                              Previous-version comparison JSON
                            </summary>
                            <div className="mt-2">
                              <JsonBlock payload={version.previous_version_comparison ?? {}} />
                            </div>
                          </details>
                        </div>
                      </details>
                    ))}
                  </div>
                </details>

                <details className="rounded border border-border/70 p-2">
                  <summary className="cursor-pointer text-xs font-medium">Grouped by run</summary>
                  <div className="mt-2 space-y-2">
                    {divergenceHistoryVersionsByRun.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No run groupings returned.</p>
                    ) : null}
                    {divergenceHistoryVersionsByRun.map((group) => {
                      const versions = Array.isArray(group.observed_versions)
                        ? group.observed_versions
                        : [];
                      return (
                        <details
                          key={toText(group.observed_in_run_id)}
                          className="rounded border border-border/70"
                        >
                          <summary className="cursor-pointer px-2 py-2 text-sm">
                            <span className={META_CHIP_CLASS}>
                              run: {toText(group.observed_in_run_id)}
                            </span>
                            <span className={`${META_CHIP_CLASS} ml-1`}>
                              versions: {toText(group.observed_version_count)}
                            </span>
                          </summary>
                          <div className="space-y-1 px-2 pb-2">
                            {versions.map((version) => (
                              <div
                                key={`${toText(group.observed_in_run_id)}-${toText(version.version_identity)}-${toText(version.observation_id)}`}
                                className="rounded border border-border/70 bg-background px-2 py-1.5 text-xs"
                              >
                                <span className={META_CHIP_CLASS}>
                                  {toText(version.observation_id)}
                                </span>
                                <span className={`${META_CHIP_CLASS} ml-1`}>
                                  type: {toText(version.divergence_type)}
                                </span>
                                <span className={`${META_CHIP_CLASS} ml-1`}>
                                  {toText(version.previous_version_signal)}
                                </span>
                                <p className="mt-1 text-[11px] text-foreground/75">
                                  status {toText(version.review_status)} | confidence{" "}
                                  {toText(version.confidence)}
                                </p>
                              </div>
                            ))}
                          </div>
                        </details>
                      );
                    })}
                  </div>
                </details>

                <details className="rounded border border-border/70 p-2">
                  <summary className="cursor-pointer text-xs font-medium">
                    Grouped by snapshot
                  </summary>
                  <div className="mt-2 space-y-2">
                    {divergenceHistoryVersionsBySnapshot.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No snapshot groupings returned.
                      </p>
                    ) : null}
                    {divergenceHistoryVersionsBySnapshot.map((group) => {
                      const versions = Array.isArray(group.observed_versions)
                        ? group.observed_versions
                        : [];
                      return (
                        <details
                          key={toText(group.source_snapshot_id)}
                          className="rounded border border-border/70"
                        >
                          <summary className="cursor-pointer px-2 py-2 text-sm">
                            <span className={META_CHIP_CLASS}>
                              snapshot: {toText(group.source_snapshot_id)}
                            </span>
                            <span className={`${META_CHIP_CLASS} ml-1`}>
                              versions: {toText(group.observed_version_count)}
                            </span>
                          </summary>
                          <div className="space-y-1 px-2 pb-2">
                            {versions.map((version) => (
                              <div
                                key={`${toText(group.source_snapshot_id)}-${toText(version.version_identity)}-${toText(version.observation_id)}`}
                                className="rounded border border-border/70 bg-background px-2 py-1.5 text-xs"
                              >
                                <span className={META_CHIP_CLASS}>
                                  {toText(version.observation_id)}
                                </span>
                                <span className={`${META_CHIP_CLASS} ml-1`}>
                                  run: {toText(version.observed_in_run_id)}
                                </span>
                                <span className={`${META_CHIP_CLASS} ml-1`}>
                                  {toText(version.previous_version_signal)}
                                </span>
                                <p className="mt-1 text-[11px] text-foreground/75">
                                  {toText(version.divergence_type)} |{" "}
                                  {toText(version.review_status)}
                                </p>
                              </div>
                            ))}
                          </div>
                        </details>
                      );
                    })}
                  </div>
                </details>

                <details className="rounded border border-border/70 p-2">
                  <summary className="cursor-pointer text-xs font-medium">
                    Raw divergence history JSON
                  </summary>
                  <div className="mt-2">
                    <JsonBlock payload={divergenceHistory} />
                  </div>
                </details>
              </div>
            ) : null}
        </AuditPanelCollapsible>

        <AuditPanelCollapsible
          title="Source records"
          description="Select a source for detail, snapshots, and fragments."
        >
            <input
              type="search"
              value={sourceSearch}
              onChange={(event) => setSourceSearch(event.target.value)}
              placeholder="Filter sources by id/title/jurisdiction/citation..."
              className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
            />
            {isSourcesLoading ? (
              <p className="text-sm text-muted-foreground">Loading sources...</p>
            ) : null}
            {sourcesError ? (
              <p className="text-sm text-destructive">
                Failed to load sources: <code>{sourcesError}</code>
              </p>
            ) : null}
            {!isSourcesLoading && !sourcesError && filteredSourceRecords.length === 0 ? (
              <p className="text-sm text-muted-foreground">No source records found for this run.</p>
            ) : null}
            {filteredSourceRecords.map((source) => (
              <button
                key={source.id}
                type="button"
                onClick={() => setSelectedSourceId(source.id)}
                className={`w-full rounded border px-2 py-2 text-left text-xs transition-colors ${
                  selectedSourceId === source.id
                    ? "border-primary bg-priguidance-discovery/[0.1]"
                    : "border-border/70 bg-background hover:bg-accent/40"
                }`}
              >
                <div className="flex flex-wrap gap-1.5">
                  <span className={META_CHIP_CLASS}>{source.id}</span>
                  <span className={META_CHIP_CLASS}>
                    jurisdiction: {toText(source.jurisdiction)}
                  </span>
                  <span className={META_CHIP_CLASS}>status: {toText(source.review_status)}</span>
                </div>
                <p className="mt-1 text-[12px] text-foreground/85">{toText(source.title)}</p>
                <p className="mt-0.5 text-[11px] text-foreground/70">
                  citation: {toText(source.citation)}
                </p>
              </button>
            ))}
            {sourceRecords.length > 0 ? (
              <details className="rounded border border-border/70 p-2">
                <summary className="cursor-pointer text-xs font-medium">
                  Raw source records list JSON
                </summary>
                <div className="mt-2">
                  <JsonBlock payload={sourceRecords} />
                </div>
              </details>
            ) : null}
        </AuditPanelCollapsible>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Source detail</CardTitle>
            <CardDescription>
              Record payload for <code>{selectedSourceId ?? "—"}</code>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {isSourceDetailLoading ? (
              <p className="text-sm text-muted-foreground">Loading source detail...</p>
            ) : null}
            {!isSourceDetailLoading && (sourceDetailSummaryFallback || sourceDetail?.partial) ? (
              <p className="text-sm text-amber-900 dark:text-amber-300">
                {sourceDetailSummaryFallback
                  ? "Full source detail is unavailable for this run; showing summary fields from the sources list."
                  : "Full source detail is unavailable for this run; showing summary fields."}
              </p>
            ) : null}
            {sourceDetailError ? (
              <p className="text-sm text-destructive">
                Failed to load source detail: <code>{sourceDetailError}</code>
              </p>
            ) : null}
            {sourceDetailDisplayRecord ? (
              <div className="space-y-2">
                <div className="grid gap-2 sm:grid-cols-2">
                  <FieldRow
                    label="Source id"
                    value={
                      toText(sourceDetailDisplayRecord.id) ||
                      toText(selectedSourceRecord?.id, selectedSourceId ?? "—")
                    }
                  />
                  <FieldRow
                    label="Current snapshot id"
                    value={sourceDetailDisplayRecord.current_snapshot_id}
                  />
                  <FieldRow label="Title" value={sourceDetailDisplayRecord.title} />
                  <FieldRow label="Jurisdiction" value={sourceDetailDisplayRecord.jurisdiction} />
                  <FieldRow label="Citation" value={sourceDetailDisplayRecord.citation} />
                  <FieldRow label="Kind" value={sourceDetailDisplayRecord.kind} />
                  <FieldRow label="Version id" value={sourceDetailDisplayRecord.version_id} />
                  <FieldRow
                    label="Review status"
                    value={sourceDetailDisplayRecord.review_status}
                  />
                  <FieldRow label="As of date" value={sourceDetailDisplayRecord.as_of_date} />
                  <FieldRow
                    label="Retrieved at"
                    value={formatDateTime(sourceDetailDisplayRecord.retrieved_at)}
                  />
                  <FieldRow label="Content hash" value={sourceDetailDisplayRecord.content_hash} />
                  <FieldRow label="Source URL" value={sourceDetailDisplayRecord.source_url} />
                </div>
                {hasAuthoritativeText ? (
                  <details className="rounded border border-border/70 p-2">
                    <summary className="cursor-pointer text-xs font-medium">
                      Authoritative text
                    </summary>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">
                      {toText(sourceDetailDisplayRecord.authoritative_text)}
                    </p>
                  </details>
                ) : null}
                {canShowRawSourceRecordJson ? (
                  <details className="rounded border border-border/70 p-2">
                    <summary className="cursor-pointer text-xs font-medium">
                      Raw source record JSON
                    </summary>
                    <div className="mt-2">
                      <JsonBlock payload={sourceDetailDisplayRecord} />
                    </div>
                  </details>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <AuditPanelCollapsible
          title="Source snapshot timeline"
          description="Ordered snapshot timepoints for selected source with default previous-snapshot diffs."
        >
            <label className="flex items-center gap-2 text-xs text-foreground/80">
              <input
                type="checkbox"
                checked={useAggregatedSourceHistory}
                onChange={(event) => setUseAggregatedSourceHistory(event.target.checked)}
              />
              aggregate across all runs + registry refresh history (read-only)
            </label>
            <input
              type="search"
              value={snapshotSearch}
              onChange={(event) => setSnapshotSearch(event.target.value)}
              placeholder="Filter timeline by event/snapshot/version/hash..."
              className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
            />
            {isSourceSnapshotTimelineLoading ? (
              <p className="text-sm text-muted-foreground">Loading snapshot timeline...</p>
            ) : null}
            {sourceSnapshotTimelineError ? (
              <p className={optionalSourceAuditErrorClass}>
                Failed to load timeline: <code>{sourceSnapshotTimelineError}</code>
              </p>
            ) : null}
            {!isSourceSnapshotTimelineLoading &&
            !sourceSnapshotTimelineError &&
            filteredSourceSnapshotTimeline.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No timeline timepoints for selected source.
              </p>
            ) : null}
            <div className="space-y-2">
              {filteredSourceSnapshotTimeline.map((timepoint) => {
                const comparison = asRecord(timepoint.comparison) ?? {};
                const origins = asArrayRecords(timepoint.origins);
                return (
                  <button
                    key={timepoint.event_id}
                    type="button"
                    onClick={() => setSelectedSnapshotEventId(timepoint.event_id)}
                    className={`w-full rounded border px-2 py-2 text-left text-xs transition-colors ${
                      selectedSnapshotEventId === timepoint.event_id
                        ? "border-primary bg-priguidance-discovery/[0.1]"
                        : "border-border/70 bg-background hover:bg-accent/40"
                    }`}
                  >
                    <div className="flex flex-wrap gap-1.5">
                      <span className={META_CHIP_CLASS}>{toText(timepoint.snapshot_id)}</span>
                      <span className={META_CHIP_CLASS}>v: {toText(timepoint.version_id)}</span>
                      <span className={META_CHIP_CLASS}>
                        {toText(comparison.change_kind, "initial")}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-foreground/75">
                      retrieved {formatDateTime(timepoint.retrieved_at)} | as_of{" "}
                      {toText(timepoint.as_of_date)}
                    </p>
                    {origins.length > 0 ? (
                      <p className="mt-0.5 text-[11px] text-foreground/70">
                        origins:{" "}
                        {origins
                          .map((origin) => {
                            const kind = toText(origin.kind, "unknown");
                            const runId = toText(origin.run_id, "").trim();
                            const registryId = toText(origin.registry_id, "").trim();
                            if (runId) {
                              return `${kind}:${runId}`;
                            }
                            if (registryId) {
                              return `${kind}:${registryId}`;
                            }
                            return kind;
                          })
                          .join(", ")}
                      </p>
                    ) : null}
                    <p className="mt-0.5 break-all font-mono text-[11px] text-foreground/60">
                      event: {timepoint.event_id}
                    </p>
                  </button>
                );
              })}
            </div>
            {selectedSnapshotTimeline ? (
              <div className="space-y-2 rounded border border-border/70 bg-muted/20 p-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Selected timepoint
                </p>
                <div className="grid gap-2 sm:grid-cols-2">
                  <FieldRow label="Snapshot id" value={selectedSnapshotTimeline.snapshot_id} />
                  <FieldRow label="Version id" value={selectedSnapshotTimeline.version_id} />
                  <FieldRow
                    label="Retrieved at"
                    value={formatDateTime(selectedSnapshotTimeline.retrieved_at)}
                  />
                  <FieldRow label="As of date" value={selectedSnapshotTimeline.as_of_date} />
                  <FieldRow label="Provenance" value={selectedSnapshotTimeline.provenance} />
                  <FieldRow
                    label="Authoritative locator"
                    value={selectedSnapshotTimeline.authoritative_locator}
                  />
                  <FieldRow label="Content hash" value={selectedSnapshotTimeline.content_hash} />
                  <FieldRow label="Event id" value={selectedSnapshotTimeline.event_id} />
                </div>
                {(() => {
                  const origins = asArrayRecords(selectedSnapshotTimeline.origins);
                  if (origins.length === 0) {
                    return null;
                  }
                  return (
                    <div className="rounded border border-border/70 bg-background p-2">
                      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                        Origins
                      </p>
                      <div className="mt-1 flex flex-wrap gap-1.5">
                        {origins.map((origin, idx) => (
                          <span
                            key={`${toText(origin.kind)}-${toText(origin.run_id)}-${toText(origin.registry_id)}-${idx}`}
                            className={META_CHIP_CLASS}
                          >
                            {toText(origin.kind)}
                            {toText(origin.run_id, "").trim() ? `:${toText(origin.run_id)}` : ""}
                            {toText(origin.registry_id, "").trim()
                              ? `:${toText(origin.registry_id)}`
                              : ""}
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })()}
                {(() => {
                  const comparison = asRecord(selectedSnapshotTimeline.comparison) ?? {};
                  const metadataDiff = asArrayRecords(comparison.metadata_diff);
                  const textDiff = toText(comparison.text_diff, "");
                  const hasPrevious = Boolean(comparison.has_previous);
                  const textChanged = Boolean(comparison.text_changed);
                  const metadataChanged = Boolean(comparison.metadata_changed);
                  return (
                    <div className="space-y-2 rounded border border-border/70 bg-background p-2">
                      <div className="flex flex-wrap gap-1.5">
                        <span className={META_CHIP_CLASS}>
                          compare: {hasPrevious ? "previous snapshot" : "none (initial)"}
                        </span>
                        <span className={META_CHIP_CLASS}>
                          kind: {toText(comparison.change_kind, "initial")}
                        </span>
                        <span className={META_CHIP_CLASS}>
                          text changed: {textChanged ? "yes" : "no"}
                        </span>
                        <span className={META_CHIP_CLASS}>
                          metadata changed: {metadataChanged ? "yes" : "no"}
                        </span>
                      </div>
                      {hasPrevious ? (
                        <div className="grid gap-2 sm:grid-cols-2">
                          <FieldRow
                            label="Baseline event id"
                            value={comparison.baseline_event_id}
                          />
                          <FieldRow
                            label="Baseline snapshot id"
                            value={comparison.baseline_snapshot_id}
                          />
                        </div>
                      ) : null}
                      <div className="rounded border border-border/70 bg-muted/20 p-2">
                        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                          Compact metadata diff
                        </p>
                        {metadataDiff.length > 0 ? (
                          <div className="mt-2 space-y-2">
                            {metadataDiff.map((item) => (
                              <div
                                key={`${toText(item.field)}-${toText(item.previous)}-${toText(item.current)}`}
                                className="rounded border border-border/70 bg-background p-2"
                              >
                                <p className="text-[11px] font-medium">{toText(item.field)}</p>
                                <p className="mt-0.5 font-mono text-[11px] text-foreground/70">
                                  {toText(item.previous)} -&gt; {toText(item.current)}
                                </p>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="mt-1 text-xs text-muted-foreground">No metadata changes.</p>
                        )}
                      </div>
                      <div className="rounded border border-border/70 bg-muted/20 p-2">
                        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                          Authoritative text diff
                        </p>
                        {textChanged ? (
                          textDiff ? (
                            <pre className="mt-2 max-h-72 overflow-auto rounded-md border border-border/80 bg-background p-2 font-mono text-[11px] leading-5">
                              {textDiff}
                            </pre>
                          ) : (
                            <p className="mt-1 text-xs text-muted-foreground">
                              Content changed but no renderable line diff was produced.
                            </p>
                          )
                        ) : (
                          <p className="mt-1 text-xs text-muted-foreground">
                            No text change detected. This is metadata-only or unchanged state.
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })()}
                <details className="rounded border border-border/70 p-2">
                  <summary className="cursor-pointer text-xs font-medium">
                    Selected snapshot JSON
                  </summary>
                  <div className="mt-2">
                    <JsonBlock payload={selectedSnapshotTimeline.snapshot ?? {}} />
                  </div>
                </details>
              </div>
            ) : null}
            {sourceSnapshotTimeline.length > 0 ? (
              <details className="rounded border border-border/70 p-2">
                <summary className="cursor-pointer text-xs font-medium">
                  Raw source snapshot timeline JSON
                </summary>
                <div className="mt-2">
                  <JsonBlock payload={sourceSnapshotTimeline} />
                </div>
              </details>
            ) : null}
        </AuditPanelCollapsible>

        <AuditPanelCollapsible
          title="Source fragments"
          description="Fragment payloads for selected source in this run."
        >
            <input
              type="search"
              value={fragmentSearch}
              onChange={(event) => setFragmentSearch(event.target.value)}
              placeholder="Filter fragments by id/snapshot/locator/hash..."
              className="h-8 w-full rounded border border-border/80 bg-background px-2 font-mono text-[12px] outline-none focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
            />
            {isSourceFragmentsLoading ? (
              <p className="text-sm text-muted-foreground">Loading fragments...</p>
            ) : null}
            {sourceFragmentsError ? (
              <p className={optionalSourceAuditErrorClass}>
                Failed to load fragments: <code>{sourceFragmentsError}</code>
              </p>
            ) : null}
            {!isSourceFragmentsLoading &&
            !sourceFragmentsError &&
            filteredSourceFragments.length === 0 ? (
              <p className="text-sm text-muted-foreground">No fragments for selected source.</p>
            ) : null}
            {filteredSourceFragments.map((fragment) => (
              <details
                key={toText(fragment.id, JSON.stringify(fragment))}
                className="rounded border border-border/70"
              >
                <summary className="cursor-pointer px-2 py-2 text-sm">
                  <span className={META_CHIP_CLASS}>{toText(fragment.id)}</span>
                  <span className={`${META_CHIP_CLASS} ml-1`}>
                    snapshot: {toText(fragment.source_snapshot_id)}
                  </span>
                  <span className={`${META_CHIP_CLASS} ml-1`}>
                    status: {toText(fragment.review_status)}
                  </span>
                </summary>
                <div className="space-y-2 px-2 pb-2">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <FieldRow label="Source record id" value={fragment.source_record_id} />
                    <FieldRow label="Source snapshot id" value={fragment.source_snapshot_id} />
                    <FieldRow label="Locator" value={fragment.locator} />
                    <FieldRow label="Fragment hash" value={fragment.fragment_hash} />
                    <FieldRow label="Review status" value={fragment.review_status} />
                  </div>
                  <details className="rounded border border-border/70 p-2">
                    <summary className="cursor-pointer text-xs font-medium">Fragment text</summary>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">
                      {toText(fragment.fragment_text)}
                    </p>
                  </details>
                  <details className="rounded border border-border/70 p-2">
                    <summary className="cursor-pointer text-xs font-medium">
                      Raw fragment JSON
                    </summary>
                    <div className="mt-2">
                      <JsonBlock payload={fragment} />
                    </div>
                  </details>
                </div>
              </details>
            ))}
            {sourceFragments.length > 0 ? (
              <details className="rounded border border-border/70 p-2">
                <summary className="cursor-pointer text-xs font-medium">
                  Raw source fragments list JSON
                </summary>
                <div className="mt-2">
                  <JsonBlock payload={sourceFragments} />
                </div>
              </details>
            ) : null}
        </AuditPanelCollapsible>
      </div>

      <div className="space-y-3 border-t border-dashed border-border/70 pt-10">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Administration
        </p>
        <Card className="border-amber-800/35 border-dashed bg-muted/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Development / admin — reset local operations state</CardTitle>
            <CardDescription>
              Calls POST <code className="text-[11px]">/ops/dev/clear/runs</code> or{" "}
              <code className="text-[11px]">/ops/dev/clear/all</code> on the configured API (
              <code>{API_BASE_URL}</code>). Use <strong>dry run</strong> to inspect targets without deleting.
              Clearing runs preserves the <strong>source registry JSON</strong>; clear-all resets the registry
              file and wipes source snapshot and derived artifact caches aligned with{" "}
              <code>SOURCE_CACHE_DIR</code> / <code>DERIVED_CACHE_DIR</code>.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-[13px]">
            <p className="text-xs text-muted-foreground">
              The <strong>registry</strong> is the API-side JSON list of legislations/sources you saved for
              re-use; <strong>runs</strong> live under <code>&lt;export-dir&gt;/runs</code> plus the flattened
              bundle JSONs at the export root. Clear runs wipes the export bundle only; clear-all also removes
              registered sources and caches.
            </p>
            {devClearError ? (
              <p className="rounded border border-destructive/50 bg-destructive/10 px-2 py-1 text-xs text-destructive">
                {devClearError}
              </p>
            ) : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 rounded border border-border/80 p-3">
                <p className="font-medium text-xs">Clear runs only (keep registry)</p>
                <p className="text-muted-foreground text-[11px] leading-relaxed">
                  Type <kbd className="rounded bg-muted px-1">CLEAR RUNS</kbd> exactly to unlock destructive delete.
                </p>
                <input
                  type="text"
                  value={devClearRunsPhrase}
                  onChange={(e) => setDevClearRunsPhrase(e.target.value)}
                  placeholder="CLEAR RUNS"
                  autoComplete="off"
                  spellCheck={false}
                  className={DEV_CLEAR_CONFIRM_INPUT_CLASS}
                />
                <div className="flex flex-wrap gap-2 pt-1">
                  <button
                    type="button"
                    disabled={isDevClearRunsDryRunning || isDevClearRunsDestructiveRunning}
                    onClick={handleDevClearRunsDryRun}
                    className={DEV_CLEAR_DRY_RUN_BUTTON_CLASS}
                  >
                    {isDevClearRunsDryRunning ? "…" : "Dry run"}
                  </button>
                  <button
                    type="button"
                    disabled={
                      isDevClearRunsDryRunning ||
                      isDevClearRunsDestructiveRunning ||
                      devClearRunsPhrase.trim() !== "CLEAR RUNS"
                    }
                    onClick={handleDevClearRunsDestructive}
                    className="rounded border border-amber-800/70 bg-amber-950/45 px-2 py-1 text-[11px] font-semibold hover:bg-amber-950/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Clear runs
                  </button>
                </div>
                {devClearRunsStatus ? <DevClearSuccessMessage message={devClearRunsStatus} /> : null}
              </div>

              <div className="space-y-2.5 rounded-lg border-2 border-destructive bg-destructive/[0.08] p-3.5 shadow-md dark:bg-destructive/[0.14]">
                <p className="text-xs font-semibold tracking-tight text-destructive">Clear all sources and runs</p>
                <p className="text-[11px] leading-relaxed text-foreground/90">
                  Type <kbd className="rounded border border-border/80 bg-background px-1.5 py-0.5 font-mono shadow-sm">
                    CLEAR ALL
                  </kbd>{" "}
                  exactly. Resets registry to empty JSON and clears source snapshot + derived caches.
                </p>
                <input
                  type="text"
                  value={devClearAllPhrase}
                  onChange={(e) => setDevClearAllPhrase(e.target.value)}
                  placeholder="CLEAR ALL"
                  autoComplete="off"
                  spellCheck={false}
                  className={DEV_CLEAR_CONFIRM_INPUT_CLASS}
                />
                <div className="flex flex-wrap gap-2 pt-0.5">
                  <button
                    type="button"
                    disabled={isDevClearAllDryRunning || isDevClearAllDestructiveRunning}
                    onClick={handleDevClearAllDryRun}
                    className={DEV_CLEAR_DRY_RUN_BUTTON_CLASS}
                  >
                    {isDevClearAllDryRunning ? "…" : "Dry run"}
                  </button>
                  <button
                    type="button"
                    disabled={
                      isDevClearAllDryRunning ||
                      isDevClearAllDestructiveRunning ||
                      devClearAllPhrase.trim() !== "CLEAR ALL"
                    }
                    onClick={handleDevClearAllDestructive}
                    className="inline-flex items-center justify-center rounded-md border border-destructive bg-destructive px-2.5 py-1.5 text-[11px] font-semibold text-destructive-foreground shadow-sm transition-colors hover:bg-destructive-hover hover:shadow active:bg-destructive-active focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none disabled:hover:bg-destructive disabled:active:bg-destructive"
                  >
                    Clear everything
                  </button>
                </div>
                {devClearAllStatus ? <DevClearSuccessMessage message={devClearAllStatus} /> : null}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
