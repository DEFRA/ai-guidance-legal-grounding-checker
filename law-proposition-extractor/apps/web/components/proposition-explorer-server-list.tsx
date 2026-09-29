"use client";

import type { JSX } from "react";
import { useCallback } from "react";

import {
  type ExplorerSectionHeading,
  type PropositionGroupSummary,
  type UnknownRecord,
  PropositionJurisdictionChip,
  asRecord,
  citationForSourceRecord,
  formatArticleClusterHeading,
  jurisdictionForSource,
  territorialApplicationFromProposition,
  TERRITORIAL_APPLICATION_CHIP_TOOLTIP,
  propositionGroupMetaChipText,
  propositionSubtitleParts,
  humanReviewNotesForDisplay,
  verbatimEvidenceUiFromProposition,
} from "@/components/proposition-explorer-helpers";
import type { PropositionDisplayMode } from "@/components/structured-proposition-ui";
import {
  CompletenessChipBadge,
  PropositionEvidenceDetails,
  PropositionScopeLinksSection,
  StructuredPropositionSections,
} from "@/components/structured-proposition-ui";
import {
  PropositionReviewPanel,
  type PipelineReviewAction,
} from "@/components/proposition-review-panel";
import {
  PropositionClassificationMeta,
  partitionSummariesByScopeSecondary,
  propositionInformativeLabel,
  type ExplorerClassificationFilters,
} from "@/components/proposition-classification-ui";

function extractionNeedsReviewFromArtifacts(
  oa: UnknownRecord,
  traceRow: UnknownRecord | undefined
): boolean {
  const rs = String(oa.review_status ?? "").toLowerCase();
  if (rs === "needs_review") {
    return true;
  }
  const ev = traceRow ? (asRecord(traceRow.effective_value) ?? {}) : {};
  if (String(ev.confidence ?? "").toLowerCase() === "low") {
    return true;
  }
  const sig = asRecord(ev.signals);
  if (sig?.fallback_used === true) {
    return true;
  }
  return false;
}

const PROPOSITION_DETAILS_CLASS =
  "rounded-lg border border-border/90 bg-card text-card-foreground shadow-sm";
const PROPOSITION_SUMMARY_CLASS =
  "cursor-pointer list-none px-3 py-2.5 text-sm outline-none marker:content-none [&::-webkit-details-marker]:hidden";
const HIER_SECTION_LABEL =
  "text-[10px] font-semibold uppercase tracking-wide text-muted-foreground";

type Section = {
  clusterKey: string;
  sectionHeadline: string;
  sectionHeadlineCompact: string;
  sectionSubtitle: string | null;
  instrumentSectionHeading: ExplorerSectionHeading | null;
  summaries: PropositionGroupSummary[];
};

export function PropositionExplorerServerList(props: {
  sections: Section[];
  sources: UnknownRecord[];
  scopeById: Map<string, UnknownRecord>;
  scopeLinkRowsByPropId: Map<string, UnknownRecord[]>;
  sourceTitleById: ReadonlyMap<string, string>;
  propositionDisplayMode: PropositionDisplayMode;
  groupDetailById: Record<string, UnknownRecord>;
  groupDetailLoading: Record<string, boolean>;
  ensureGroupDetailLoaded: (groupId: string) => Promise<void>;
  pipelineReviewDecisions: UnknownRecord[];
  actionBusyKey: string | null;
  reviewRecordedFlash: { propositionId: string; at: number } | null;
  appendPipelineReviewDecision: (
    propositionId: string,
    artifactType: string,
    artifactId: string,
    decision: PipelineReviewAction
  ) => Promise<void>;
  openFragmentModal: (
    sourceRecordId: string,
    fragmentId: string,
    options?: { highlightLocator?: string; contextInjections?: UnknownRecord | null }
  ) => Promise<void>;
  setTraceModalPid: (pid: string | null) => void;
  traceByPropId: Map<string, UnknownRecord>;
  initialArticleSectionsOpen: number;
  filtersActive: boolean;
  classificationFilters: ExplorerClassificationFilters;
  propositionArtifactById: ReadonlyMap<string, UnknownRecord>;
}): JSX.Element {
  const {
    sections,
    sources,
    scopeById,
    scopeLinkRowsByPropId,
    sourceTitleById,
    propositionDisplayMode,
    groupDetailById,
    groupDetailLoading,
    ensureGroupDetailLoaded,
    pipelineReviewDecisions,
    actionBusyKey,
    reviewRecordedFlash,
    appendPipelineReviewDecision,
    openFragmentModal,
    setTraceModalPid,
    traceByPropId,
    initialArticleSectionsOpen,
    filtersActive,
    classificationFilters,
    propositionArtifactById,
  } = props;

  const showExtractionDebug = propositionDisplayMode === "raw";

  const onGroupToggle = useCallback(
    async (groupId: string, open: boolean) => {
      if (open) {
        await ensureGroupDetailLoaded(groupId);
      }
    },
    [ensureGroupDetailLoaded]
  );

  return (
    <div className="space-y-4">
      {sections.map((sec, secIdx) => {
        const articleSectionOpen = filtersActive || secIdx < initialArticleSectionsOpen;
        const ARTICLE_SECTION_DETAILS_CLASS =
          "rounded-lg border border-border/75 bg-muted/[0.15] open:bg-muted/[0.22]";
        const ARTICLE_SECTION_SUMMARY_CLASS =
          "cursor-pointer list-none px-3 py-2.5 text-sm outline-none marker:content-none [&::-webkit-details-marker]:hidden";
        return (
          <details
            key={sec.clusterKey}
            className={ARTICLE_SECTION_DETAILS_CLASS}
            open={articleSectionOpen}
          >
            <summary className={ARTICLE_SECTION_SUMMARY_CLASS}>
              <p className={`${HIER_SECTION_LABEL} mb-1`}>Section</p>
              {sec.instrumentSectionHeading ? (
                <div className="space-y-0.5">
                  <span className="text-[15px] font-semibold leading-snug text-foreground">
                    {sec.instrumentSectionHeading.primaryInstrumentLine}
                  </span>
                  <span className="text-[14px] font-medium leading-snug text-foreground/90">
                    {sec.instrumentSectionHeading.provisionLine}
                  </span>
                  <p className="text-[11px] text-muted-foreground">{sec.instrumentSectionHeading.metadataLine}</p>
                </div>
              ) : (
                <div className="space-y-0.5">
                  <span className="text-[15px] font-semibold text-foreground">{sec.sectionHeadline}</span>
                  {sec.sectionSubtitle ? (
                    <p className="text-[11px] text-muted-foreground">{sec.sectionSubtitle}</p>
                  ) : null}
                </div>
              )}
            </summary>
            <div className="space-y-4 border-t border-border/50 px-2 pb-3 pt-3">
              {(() => {
                const { primary, scopeSecondary } = partitionSummariesByScopeSecondary(
                  sec.summaries,
                  propositionArtifactById,
                  classificationFilters.collapseScopeRules
                );

                const renderGroupSummary = (sum: PropositionGroupSummary) => {
                const detail = groupDetailById[sum.group_id];
                const rows = (detail?.effective_propositions as UnknownRecord[] | undefined) ?? [];
                const busy = groupDetailLoading[sum.group_id];
                const repOa =
                  sum.row_ids
                    .map((id) => propositionArtifactById.get(id))
                    .find((oa): oa is UnknownRecord => Boolean(oa)) ?? null;
                const groupTitle = repOa ? propositionInformativeLabel(repOa) : sum.display_label;
                const metaChip = propositionGroupMetaChipText({
                  sourceRowCount: sum.source_row_count,
                  allSameWording: sum.wording_status !== "diff",
                  jurisdictionBadgeLabels: sum.jurisdictions,
                });
                return (
                  <details
                    key={sum.group_id}
                    className={PROPOSITION_DETAILS_CLASS}
                    onToggle={(e) => {
                      const t = e.target as HTMLDetailsElement;
                      void onGroupToggle(sum.group_id, t.open);
                    }}
                  >
                    <summary className={PROPOSITION_SUMMARY_CLASS}>
                      <p className={`${HIER_SECTION_LABEL} mb-1`}>Proposition group</p>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-foreground">{groupTitle}</span>
                        <span className="rounded border border-border/70 bg-muted/80 px-2 py-0.5 font-mono text-[11px]">
                          {metaChip}
                        </span>
                        <CompletenessChipBadge
                          pipelineStatus={
                            sum.completeness_status && typeof sum.completeness_status === "string"
                              ? sum.completeness_status
                              : undefined
                          }
                          noAssessment={!sum.completeness_status}
                        />
                      </div>
                      {repOa ? (
                        <div className="mt-2">
                          <PropositionClassificationMeta oa={repOa} compact />
                        </div>
                      ) : null}
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        {formatArticleClusterHeading(sum.article_key)} ·{" "}
                        {Object.entries(sum.review_summary)
                          .map(([k, v]) => `${k}:${v}`)
                          .join(", ")}
                      </p>
                    </summary>
                    <div className="space-y-3 border-t border-border/50 px-3 py-3">
                      {busy ? <p className="text-xs text-muted-foreground">Loading group details…</p> : null}
                      {!busy && rows.length === 0 ? (
                        <p className="text-xs text-muted-foreground">Open to load source rows and reviews.</p>
                      ) : null}
                      {rows.map((row, rowIdx) => {
                        const oa = asRecord(row.original_artifact) ?? {};
                        const pid = String(oa.id ?? "").trim();
                        const tr = pid ? traceByPropId.get(pid) : undefined;
                        const sid = typeof oa.source_record_id === "string" ? oa.source_record_id : "";
                        const fid = typeof oa.source_fragment_id === "string" ? oa.source_fragment_id : "";
                        const hl =
                          typeof oa.fragment_locator === "string" ? oa.fragment_locator.trim() : "";
                        const txt =
                          typeof oa.proposition_text === "string" ? oa.proposition_text : "";
                        const scopeRows = pid ? (scopeLinkRowsByPropId.get(pid) ?? []) : [];

                        const jl = jurisdictionForSource(sources, sid);
                        const territorial = territorialApplicationFromProposition(oa);
                        const compRows = (detail?.completeness_assessments as UnknownRecord[] | undefined) ?? [];
                        const compRow = compRows.find(
                          (c) => String(c.proposition_id ?? "").trim() === pid
                        );
                        const cStatus = typeof compRow?.status === "string" ? compRow.status : "";
                        const ctxInj =
                          compRow &&
                          compRow.context_injections &&
                          typeof compRow.context_injections === "object"
                            ? (compRow.context_injections as UnknownRecord)
                            : null;
                        const evidUi = verbatimEvidenceUiFromProposition(oa);
                        const reviewNotes = humanReviewNotesForDisplay(oa);
                        const suggStmt =
                          typeof compRow?.suggested_display_statement === "string"
                            ? compRow.suggested_display_statement.trim()
                            : "";
                        const reviewLabel = String(row.effective_status ?? "").trim().toLowerCase();

                        return (
                          <details
                            key={`${sum.group_id}-${pid || rowIdx}`}
                            className="rounded border border-border/60 bg-muted/[0.08] px-2 py-2"
                            open={rows.length === 1 || reviewLabel === "needs_review"}
                          >
                            <summary className="cursor-pointer list-none text-[12px] outline-none marker:content-none [&::-webkit-details-marker]:hidden">
                              <div className="flex flex-wrap items-center gap-2">
                                <PropositionJurisdictionChip jurisdiction={jl} sourceId={sid} />
                                {territorial.length > 0 ? (
                                  <span
                                    title={TERRITORIAL_APPLICATION_CHIP_TOOLTIP}
                                    className="rounded border border-amber-600/40 bg-amber-950/20 px-2 py-0.5 font-mono text-[11px] text-amber-100/90"
                                  >
                                    applies: {territorial.join(", ")}
                                  </span>
                                ) : null}
                                <span className="font-medium">{propositionInformativeLabel(oa)}</span>
                                <PropositionClassificationMeta oa={oa} compact />
                              </div>
                            </summary>
                            <div className="mt-2 space-y-2 border-t border-border/40 pt-2">
                              <div className="rounded-md border border-border/50 bg-muted/[0.12] px-2.5 py-2">
                                <PropositionClassificationMeta
                                  oa={oa}
                                  showExtractionDebug={showExtractionDebug}
                                />
                              </div>
                              <PropositionScopeLinksSection
                                propositionId={pid}
                                scopeRows={scopeRows}
                                scopeById={scopeById}
                              />
                              <StructuredPropositionSections
                                mode={propositionDisplayMode}
                                text={txt}
                                oa={oa}
                                sourceTitleById={sourceTitleById}
                                suggestedStatement={suggStmt}
                                extractionConfidence={
                                  tr && typeof asRecord(tr.effective_value)?.confidence === "string"
                                    ? String(asRecord(tr.effective_value)?.confidence)
                                    : undefined
                                }
                                extractionNeedsReview={extractionNeedsReviewFromArtifacts(oa, tr)}
                                completenessChipSlot={
                                  <CompletenessChipBadge
                                    pipelineStatus={cStatus}
                                    noAssessment={!compRow}
                                  />
                                }
                              />
                              {reviewNotes ? (
                                <p className="text-[12px] leading-relaxed text-muted-foreground">
                                  <span className="font-medium text-foreground">Review note: </span>
                                  {reviewNotes}
                                </p>
                              ) : null}
                              <PropositionEvidenceDetails
                                rawText={txt}
                                verbatimEvidenceKnown={evidUi.known}
                                verbatimEvidenceQuote={evidUi.quoteText}
                                evidenceMismatchWarning={
                                  evidUi.showTraceabilityWarning
                                    ? "Evidence quote could not be matched exactly to source text."
                                    : null
                                }
                                fragmentSlot={
                                  fid ? (
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
                                  ) : null
                                }
                                traceButton={
                                  <button
                                    type="button"
                                    className="rounded border border-border/80 px-2 py-0.5 text-[11px] hover:bg-accent/70"
                                    onClick={() => (pid ? setTraceModalPid(pid) : undefined)}
                                  >
                                    view extraction trace
                                  </button>
                                }
                              />
                              {pid ? (
                                <PropositionReviewPanel
                                  propositionId={pid}
                                  completenessArtifactId={
                                    (compRow && String(compRow.id ?? "").trim()) || pid
                                  }
                                  decisions={pipelineReviewDecisions}
                                  busyKey={actionBusyKey}
                                  disabled={actionBusyKey !== null}
                                  recordedFlashAt={
                                    reviewRecordedFlash?.propositionId === pid
                                      ? reviewRecordedFlash.at
                                      : null
                                  }
                                  onDecision={(
                                    artifactType: string,
                                    artifactId: string,
                                    dec: PipelineReviewAction
                                  ) =>
                                    void appendPipelineReviewDecision(
                                      pid,
                                      artifactType,
                                      artifactId,
                                      dec
                                    )
                                  }
                                />
                              ) : null}
                              <p className="text-[10px] text-muted-foreground">
                                {propositionSubtitleParts(oa).locatorLine ?? ""}
                                {sid ? ` · ${citationForSourceRecord(sources, sid)}` : ""}
                              </p>
                            </div>
                          </details>
                        );
                      })}
                    </div>
                  </details>
                );
                };

                return (
                  <>
                    {primary.map(renderGroupSummary)}
                    {scopeSecondary.length > 0 ? (
                      <details className="rounded-lg border border-dashed border-border/60 bg-muted/[0.08] px-2 py-2 open:bg-muted/[0.14]">
                        <summary className="cursor-pointer list-none px-1 py-1.5 text-[12px] font-medium text-muted-foreground marker:content-none [&::-webkit-details-marker]:hidden">
                          Scope &amp; application ({scopeSecondary.length})
                        </summary>
                        <div className="mt-2 space-y-4 border-t border-border/40 pt-3">
                          {scopeSecondary.map(renderGroupSummary)}
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
  );
}
