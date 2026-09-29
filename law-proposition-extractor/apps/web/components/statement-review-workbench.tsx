"use client";

import { ChevronRight, ExternalLink } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { buildContextRequirementResolutions } from "@/lib/context-locator-resolution";
import {
  legislationContextCrumbs,
  type LegislationContextCrumb,
} from "@/lib/legislation-gov-uk-url";
import {
  buildAssessmentContextViews,
  buildWorkbenchComposition,
  type AssessmentContextStatus,
  type AssessmentContextView,
  type CompositionSourceView,
  type LawFragmentView,
  type PropositionReviewView,
} from "@/lib/review-workbench-views";
import {
  shortInstrumentLabel,
  type UnknownRecord,
} from "@/components/proposition-explorer-helpers";
import {
  assessReviewCompleteness,
  buildWorkbenchReviewExport,
  CONTEXT_ASSESSMENT_OPTIONS,
  downloadWorkbenchReviewExport,
  emptyWorkbenchReview,
  FAILURE_STAGE_OPTIONS,
  loadRunWorkbenchReviews,
  loadWorkbenchReview,
  PROPOSITION_ISSUE_OPTIONS,
  REVIEW_SEVERITY_OPTIONS,
  saveWorkbenchReview,
  STATEMENT_VERDICT_OPTIONS,
  type ContextAssessmentFlag,
  type ContextAssessmentFlags,
  type FailureStage,
  type PropositionIssue,
  type ReviewSeverity,
  type ReviewStatus,
  type StatementVerdict,
  type WorkbenchReview,
} from "@/lib/review-workbench-state";
import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import {
  formatStructuralHeadingDisplay,
  nearestProvisionHeading,
} from "@/lib/structural-headings";
import {
  presentationRoleLabel,
  propositionRefsForStatement,
  type LawStatementRow,
  type PropositionRow,
  type SourceRow,
  type SourceSnapshotRow,
  type StatementQualityAssessment,
} from "@/lib/law-statements-index";
import {
  segmentsFromExportCompositionTrace,
  statementHasExportCompositionTrace,
} from "@/lib/composition-trace-segments";
import {
  classifyWorkbenchPropositions,
  formatMainPropositionRoleSummary,
  groupMainPropositionsByRole,
  type ClassifiedProposition,
} from "@/lib/review-workbench-proposition-classification";
import { buildStatementCompositionSegments } from "@/lib/statement-composition-highlight";
import { StatementCompositionHighlight } from "@/components/statement-composition-highlight";
import { LegalContextPanel } from "@/components/legal-context-panel";
import { StatementInlineReferenceText } from "@/components/statement-inline-reference-text";
import {
  addReferenceToWorkspace,
  removeReferenceFromWorkspace,
  resolveWorkspaceReferences,
  selectedReferenceAfterRemoval,
} from "@/lib/legal-context-workspace";
import {
  buildWorkbenchLegalReferences,
  referenceById,
  type InlineLegalReference,
  type StatementTextPart,
} from "@/lib/statement-inline-references";
import { StatementIncorporationPanels } from "@/components/statement-incorporation-panels";
import { TypedLegalContextSection } from "@/components/typed-legal-context-section";
import { SourceVersionSummary } from "@/components/source-version-summary";
import { StatementWhyPanel } from "@/components/statement-why-panel";
import type {
  DecisionExplanationIndex,
  HeuristicDefinition,
} from "@/lib/decision-explanations";
import {
  buildSourceLegalEffectsView,
  effectHasAffectingInstrumentIds,
  effectHasFragmentLinks,
  normalizeOutstandingEffectsStatus,
  type SourceLegalEffectsArtifactRow,
} from "@/lib/source-legal-effects";
import {
  buildTypedLegalContextSections,
  hasTypedLegalContext,
  statementWithGenericContextOnly,
} from "@/lib/typed-legal-context";
import {
  collectSourceVersionProvenanceForStatement,
  type SourceLegalEffectsKnowledgeInput,
} from "@/lib/source-version-provenance";
import {
  RW_CHIP,
  RW_CHIP_WARN,
  RW_JOURNEY_ARROW,
  RW_LEGAL_EXCERPT,
  RW_PANEL_HIGHLIGHT,
  RW_SECTION_HEADER_STATUS,
  RW_STAGE_LABEL,
  RW_STAGE_LABEL_ON_DARK,
  toggleButtonClass,
  verdictButtonClass,
} from "@/lib/review-workbench-ui";

const META_CHIP_CLASS = RW_CHIP;

const WARN_CHIP_CLASS = RW_CHIP_WARN;

const STAGE_LABEL = RW_STAGE_LABEL;

const JOURNEY_ARROW = RW_JOURNEY_ARROW;

const PANEL_HIGHLIGHT_CLASS = RW_PANEL_HIGHLIGHT;

function JourneyArrow(): JSX.Element {
  return (
    <div className={JOURNEY_ARROW} aria-hidden="true">
      ↓
    </div>
  );
}

function CollapsibleWorkbenchSection(props: {
  title: string;
  description?: string;
  count?: number;
  defaultOpen?: boolean;
  children: JSX.Element | JSX.Element[] | null;
}): JSX.Element {
  const { title, description, count, defaultOpen = false, children } = props;
  const [open, setOpen] = useState(defaultOpen);
  const countLabel = count !== undefined ? ` (${count})` : "";
  return (
    <section className="rounded-lg border border-border/80 bg-background shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        aria-expanded={open}
      >
        <div>
          <h3 className="text-[13px] font-medium text-foreground">
            {title}
            {countLabel}
          </h3>
          {description ? (
            <p className="mt-0.5 text-[11px] text-muted-foreground">{description}</p>
          ) : null}
        </div>
        <span className="text-[11px] text-muted-foreground">{open ? "Hide" : "Show"}</span>
      </button>
      {open ? <div className="border-t border-border/70 px-4 py-3">{children}</div> : null}
    </section>
  );
}

function ReviewerPropositionItem(props: {
  entry: ClassifiedProposition;
  issues: PropositionIssue[];
  onToggleIssue: (propositionId: string, issue: PropositionIssue) => void;
  highlighted?: boolean;
  showDeveloperFields?: boolean;
  propositionParts?: StatementTextPart[];
  propositionReferences?: InlineLegalReference[];
  excerptParts?: StatementTextPart[];
  excerptReferences?: InlineLegalReference[];
  selectedReferenceId?: string | null;
  onSelectReference?: (referenceId: string | null) => void;
  accumulateSelection?: boolean;
  mobilePanel?: JSX.Element | null;
}): JSX.Element {
  const {
    entry,
    issues,
    onToggleIssue,
    highlighted = false,
    showDeveloperFields = false,
    propositionParts,
    propositionReferences = [],
    excerptParts,
    excerptReferences = [],
    selectedReferenceId,
    onSelectReference,
    accumulateSelection = false,
    mobilePanel,
  } = props;
  const { proposition } = entry;
  const hasAnnotatedText = propositionParts && propositionParts.length > 0;
  const hasAnnotatedExcerpt = excerptParts && excerptParts.length > 0;
  return (
    <div
      className={`rounded-lg border px-3 py-2 ${
        issues.length > 0
          ? "border-amber-600/40 bg-amber-950/5"
          : highlighted
            ? PANEL_HIGHLIGHT_CLASS
            : "border-border/75"
      }`}
    >
      <div className="mb-1 flex flex-wrap gap-2">
        <span className={META_CHIP_CLASS}>{entry.roleLabel}</span>
        {showDeveloperFields ? (
          <span className="font-mono text-[10px] text-primary">{proposition.propositionId}</span>
        ) : null}
      </div>
      {hasAnnotatedText ? (
        <StatementInlineReferenceText
          statementText={proposition.propositionText}
          parts={propositionParts}
          references={propositionReferences}
          textClassName="text-[13px] leading-relaxed"
          selectedReferenceId={selectedReferenceId}
          onSelectReference={onSelectReference}
          accumulateSelection={accumulateSelection}
          mobilePanel={mobilePanel}
          emptyMessage="No proposition text."
        />
      ) : (
        <p className="text-[13px] leading-relaxed">{proposition.propositionText}</p>
      )}
      {proposition.sourceExcerpt !== "not available from current export" ? (
        hasAnnotatedExcerpt ? (
          <div className="mt-1">
            <StatementInlineReferenceText
              statementText={proposition.sourceExcerpt}
              parts={excerptParts!}
              references={excerptReferences}
              textClassName="text-[11px] leading-relaxed text-muted-foreground line-clamp-3"
              selectedReferenceId={selectedReferenceId}
              onSelectReference={onSelectReference}
              accumulateSelection={accumulateSelection}
              emptyMessage=""
            />
          </div>
        ) : (
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground line-clamp-3">
            {proposition.sourceExcerpt}
          </p>
        )
      ) : null}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {PROPOSITION_ISSUE_OPTIONS.map((option) => (
          <ToggleChip
            key={option.value}
            label={option.label}
            active={issues.includes(option.value)}
            onClick={() => onToggleIssue(proposition.propositionId, option.value)}
            compact
          />
        ))}
      </div>
    </div>
  );
}

function ReviewerPropositionGroup(props: {
  title: string;
  entries: ClassifiedProposition[];
  issuesById: Record<string, PropositionIssue[]>;
  onToggleIssue: (propositionId: string, issue: PropositionIssue) => void;
  highlightedPropositionIds?: ReadonlySet<string>;
  defaultOpen?: boolean;
  showDeveloperFields?: boolean;
  partsBySourceId: Map<string, StatementTextPart[]>;
  referencesBySourceId: Map<string, InlineLegalReference[]>;
  selectedReferenceId?: string | null;
  onSelectReference?: (referenceId: string | null) => void;
  accumulateSelection?: boolean;
  mobilePanel?: JSX.Element | null;
}): JSX.Element | null {
  const {
    title,
    entries,
    issuesById,
    onToggleIssue,
    highlightedPropositionIds,
    defaultOpen = true,
    showDeveloperFields = false,
    partsBySourceId,
    referencesBySourceId,
    selectedReferenceId,
    onSelectReference,
    accumulateSelection = false,
    mobilePanel,
  } = props;
  if (entries.length === 0) {
    return null;
  }
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between gap-2 text-left"
        aria-expanded={open}
      >
        <h4 className={STAGE_LABEL}>
          {title} ({entries.length})
        </h4>
        <span className="text-[10px] text-muted-foreground">{open ? "Hide" : "Show"}</span>
      </button>
      {open ? (
        <div className="space-y-2">
          {entries.map((entry) => {
            const propositionSourceId = `proposition:${entry.proposition.propositionId}`;
            const excerptSourceId = `${propositionSourceId}:excerpt`;
            return (
              <ReviewerPropositionItem
                key={entry.proposition.propositionId}
                entry={entry}
                issues={issuesById[entry.proposition.propositionId] ?? []}
                onToggleIssue={onToggleIssue}
                highlighted={highlightedPropositionIds?.has(entry.proposition.propositionId)}
                showDeveloperFields={showDeveloperFields}
                propositionParts={partsBySourceId.get(propositionSourceId)}
                propositionReferences={referencesBySourceId.get(propositionSourceId) ?? []}
                excerptParts={partsBySourceId.get(excerptSourceId)}
                excerptReferences={referencesBySourceId.get(excerptSourceId) ?? []}
                selectedReferenceId={selectedReferenceId}
                onSelectReference={onSelectReference}
                accumulateSelection={accumulateSelection}
                mobilePanel={mobilePanel}
              />
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function ToggleChip(props: {
  label: string;
  active: boolean;
  onClick: () => void;
  compact?: boolean;
  className?: string;
}): JSX.Element {
  const { label, active, onClick, compact = false, className } = props;
  return (
    <button
      type="button"
      onClick={onClick}
      className={className ?? toggleButtonClass(active, compact)}
    >
      {label}
    </button>
  );
}

const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  unreviewed: "Unreviewed",
  draft_review: "Draft review",
  complete_review: "Complete review",
};

function ReviewQualityPanel(props: {
  status: ReviewStatus;
  reasons: string[];
}): JSX.Element {
  const { status, reasons } = props;
  if (status === "complete_review") {
    return (
      <div className="rw-quality-banner-complete">
        <p>Review quality: complete — ready for export as evaluation data.</p>
      </div>
    );
  }
  if (status === "unreviewed") {
    return (
      <div className="rw-quality-banner-unreviewed">
        <p>Review quality: unreviewed — select a verdict to begin.</p>
      </div>
    );
  }
  return (
    <div className="rw-quality-banner-draft">
      <p>Review quality: draft — still missing required evidence.</p>
      <ul className="mt-1 list-inside list-disc text-[11px] leading-relaxed text-amber-100/90">
        {reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
    </div>
  );
}

function LegislationLocatorLink(props: {
  locator: string;
  href: string | null;
  className?: string;
}): JSX.Element {
  const { locator, href, className = "font-mono text-[10px] text-muted-foreground" } = props;
  if (!href) {
    return <span className={className}>{locator}</span>;
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={`${className} inline-flex items-center gap-1 text-sky-800 underline-offset-2 hover:underline dark:text-sky-200`}
      title="Open live legislation page"
    >
      <span>{locator}</span>
      <ExternalLink className="h-3 w-3 shrink-0 opacity-80" aria-hidden />
      <span className="sr-only"> (opens live legislation.gov.uk page)</span>
    </a>
  );
}

function SourceContextBreadcrumb(props: {
  crumbs: LegislationContextCrumb[];
}): JSX.Element {
  const { crumbs } = props;
  return (
    <nav aria-label="Source context" className="flex flex-wrap items-center gap-x-1 gap-y-1 text-[12px]">
      {crumbs.map((crumb, index) => {
        const isLast = index === crumbs.length - 1;
        const body = crumb.href ? (
          <a
            href={crumb.href}
            target="_blank"
            rel="noopener noreferrer"
            className={`inline-flex items-center gap-1 underline-offset-2 hover:underline ${
              isLast
                ? "font-medium text-sky-900 dark:text-sky-100"
                : "text-sky-800 dark:text-sky-200"
            }`}
            title="Open live legislation page"
          >
            <span>{crumb.label}</span>
            <ExternalLink className="h-3 w-3 shrink-0 opacity-70" aria-hidden />
          </a>
        ) : (
          <span className={isLast ? "font-medium text-foreground" : "text-muted-foreground"}>
            {crumb.label}
          </span>
        );
        return (
          <span key={`${crumb.label}-${index}`} className="inline-flex items-center gap-1">
            {index > 0 ? (
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70" aria-hidden />
            ) : null}
            {body}
          </span>
        );
      })}
    </nav>
  );
}

function LawFragmentPanel(props: {
  fragments: LawFragmentView[];
  missingById: Record<string, boolean>;
  coverageGapById: Record<string, boolean>;
  onToggleMissing: (fragmentId: string) => void;
  onToggleCoverageGap: (fragmentId: string) => void;
  highlightedFragmentIds?: ReadonlySet<string>;
  showDeveloperFields?: boolean;
}): JSX.Element {
  const {
    fragments,
    missingById,
    coverageGapById,
    onToggleMissing,
    onToggleCoverageGap,
    highlightedFragmentIds,
    showDeveloperFields = true,
  } = props;
  if (fragments.length === 0) {
    return <p className="text-sm italic text-muted-foreground">No source excerpts available.</p>;
  }
  return (
    <div className="space-y-2">
      {fragments.map((fragment) => {
        const markedMissing = Boolean(missingById[fragment.id]);
        const markedCoverage = Boolean(coverageGapById[fragment.id]);
        const linked = Boolean(highlightedFragmentIds?.has(fragment.id));
        return (
          <div
            key={fragment.id}
            className={`rounded-lg border px-3 py-2 ${
              markedMissing || markedCoverage
                ? "border-red-500/50 bg-red-950/5"
                : linked
                  ? PANEL_HIGHLIGHT_CLASS
                  : "border-border/75 bg-muted/[0.12]"
            }`}
          >
            <p className="mb-1">
              <LegislationLocatorLink
                locator={fragment.sourceLocator}
                href={fragment.legislationUrl}
              />
            </p>
            <p className={RW_LEGAL_EXCERPT}>{fragment.sourceExcerpt}</p>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              {showDeveloperFields ? (
                <p className="font-mono text-[10px] text-muted-foreground">
                  {fragment.propositionIds.join(", ")}
                </p>
              ) : (
                <span />
              )}
              <div className="flex flex-wrap gap-1.5">
                <ToggleChip
                  label="Missing proposition here"
                  active={markedMissing}
                  onClick={() => onToggleMissing(fragment.id)}
                  compact
                />
                <ToggleChip
                  label="Coverage gap here"
                  active={markedCoverage}
                  onClick={() => onToggleCoverageGap(fragment.id)}
                  compact
                />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

const ASSESSMENT_STATUS_CLASS: Record<AssessmentContextStatus, string> = {
  resolved: "text-emerald-700 dark:text-emerald-300",
  resolved_container: "text-emerald-700 dark:text-emerald-300",
  partially_resolved: "text-sky-800 dark:text-sky-200",
  unresolved: "text-amber-800 dark:text-amber-200",
  ambiguous: "text-orange-800 dark:text-orange-200",
  external: "text-muted-foreground",
};

function AssessmentContextChildItem(props: {
  child: NonNullable<AssessmentContextView["children"]>[number];
  showDeveloperFields?: boolean;
}): JSX.Element {
  const { child, showDeveloperFields = true } = props;
  return (
    <li className="space-y-1 border-l border-border/70 pl-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] text-foreground">{child.locator}</span>
        {showDeveloperFields ? (
          <span
            className={
              child.resolved
                ? "text-[10px] text-emerald-700 dark:text-emerald-300"
                : "text-[10px] text-amber-800 dark:text-amber-200"
            }
          >
            {child.resolved ? "resolved" : child.reason ?? "not found"}
          </span>
        ) : null}
      </div>
      {child.fragments.map((fragment) => (
        <div key={fragment.fragmentId} className="mt-1">
          {showDeveloperFields ? (
            <p className="font-mono text-[10px] text-muted-foreground">{fragment.locator}</p>
          ) : null}
          <p className="mt-1 text-[13px] leading-relaxed">{fragment.excerpt}</p>
        </div>
      ))}
    </li>
  );
}

function AssessmentContextItem(props: {
  context: AssessmentContextView;
  flags: ContextAssessmentFlags;
  onToggleFlag: (locator: string, flag: ContextAssessmentFlag) => void;
  showControls: boolean;
  highlighted?: boolean;
  showDeveloperFields?: boolean;
}): JSX.Element {
  const {
    context,
    flags,
    onToggleFlag,
    showControls,
    highlighted = false,
    showDeveloperFields = true,
  } = props;
  const [expanded, setExpanded] = useState(false);
  const toggleLabel = showDeveloperFields
    ? expanded
      ? "Hide resolved fragments"
      : "Show resolved fragments"
    : expanded
      ? "Hide context text"
      : "Show context text";
  const hasChildren = (context.children?.length ?? 0) > 0;
  const hasFragments = context.fragments.length > 0;

  return (
    <li
      className={`space-y-2 rounded-lg border px-2 py-2 ${
        highlighted ? PANEL_HIGHLIGHT_CLASS : "border-transparent"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[12px] text-foreground">{context.locator}</span>
            {showDeveloperFields ? (
              <span
                className={`text-[10px] font-medium uppercase tracking-wide ${ASSESSMENT_STATUS_CLASS[context.status]}`}
              >
                {context.status}
              </span>
            ) : null}
          </div>
          {context.inheritedContextLabel ? (
            <p className="text-[11px] text-muted-foreground">{context.inheritedContextLabel}</p>
          ) : null}
          {showDeveloperFields && context.resolvedLocator ? (
            <p className="font-mono text-[10px] text-muted-foreground">
              resolved to {context.resolvedLocator}
              {context.unresolvedChild ? ` · unresolved child: ${context.unresolvedChild}` : ""}
            </p>
          ) : null}
        </div>
        {hasFragments || hasChildren || (context.status !== "resolved" && context.status !== "resolved_container") ? (
          <button
            type="button"
            onClick={() => setExpanded((open) => !open)}
            className="rounded border border-border/80 px-2 py-0.5 text-[10px] font-medium text-muted-foreground hover:bg-muted/50"
            aria-expanded={expanded}
          >
            {toggleLabel}
          </button>
        ) : null}
      </div>
      {expanded ? (
        <div className="rounded-lg border border-border/75 bg-muted/[0.12] px-3 py-2">
          {context.status === "resolved" || context.status === "resolved_container" ? (
            <div className="space-y-2">
              {!hasChildren
                ? context.fragments.map((fragment) => (
                    <div key={fragment.fragmentId}>
                      {showDeveloperFields ? (
                        <p className="font-mono text-[10px] text-muted-foreground">{fragment.locator}</p>
                      ) : null}
                      <p className="mt-1 text-[13px] leading-relaxed">{fragment.excerpt}</p>
                    </div>
                  ))
                : null}
              {hasChildren ? (
                <ul className="space-y-2">
                  {context.children?.map((child) => (
                    <AssessmentContextChildItem
                      key={child.locator}
                      child={child}
                      showDeveloperFields={showDeveloperFields}
                    />
                  ))}
                </ul>
              ) : null}
            </div>
          ) : (
            <div className="space-y-2 text-[12px] leading-relaxed">
              {showDeveloperFields && context.resolvedLocator ? (
                <p className="font-mono text-[11px] text-foreground">{context.resolvedLocator}</p>
              ) : null}
              {showDeveloperFields && context.reason ? (
                <p className="text-muted-foreground">reason: {context.reason}</p>
              ) : null}
              {hasFragments
                ? context.fragments.map((fragment) => (
                    <div key={fragment.fragmentId}>
                      {showDeveloperFields ? (
                        <p className="font-mono text-[10px] text-muted-foreground">{fragment.locator}</p>
                      ) : null}
                      <p className="mt-1 text-[13px] leading-relaxed">{fragment.excerpt}</p>
                    </div>
                  ))
                : null}
              {hasChildren ? (
                <ul className="space-y-2">
                  {context.children?.map((child) => (
                    <AssessmentContextChildItem
                      key={child.locator}
                      child={child}
                      showDeveloperFields={showDeveloperFields}
                    />
                  ))}
                </ul>
              ) : null}
            </div>
          )}
        </div>
      ) : null}
      {showControls ? (
        <div className="flex flex-wrap gap-1.5">
          {CONTEXT_ASSESSMENT_OPTIONS.map((option) => (
            <ToggleChip
              key={option.value}
              label={option.label}
              active={Boolean(flags[option.value])}
              onClick={() => onToggleFlag(context.locator, option.value)}
              compact
            />
          ))}
        </div>
      ) : null}
    </li>
  );
}

function CompositionSourcesSection(props: {
  sources: CompositionSourceView[];
  lawFragments: LawFragmentView[];
  compact?: boolean;
  highlightedFragmentIds?: ReadonlySet<string>;
  highlightedPropositionIds?: ReadonlySet<string>;
  showDeveloperFields?: boolean;
}): JSX.Element | null {
  const {
    sources,
    lawFragments,
    compact = false,
    highlightedFragmentIds,
    highlightedPropositionIds,
    showDeveloperFields = true,
  } = props;
  if (sources.length === 0 && lawFragments.length === 0) {
    return null;
  }
  return (
    <section className="rw-panel-sources">
      <p className="text-[12px] font-medium text-foreground">Used to build this statement</p>
      <p className="mt-1 text-[11px] text-muted-foreground">
        These sources contributed to the statement wording.
      </p>
      {lawFragments.length > 0 ? (
        <ul className={`mt-2 space-y-2 ${compact ? "line-clamp-2" : ""}`}>
          {lawFragments.map((fragment) => (
            <li
              key={fragment.id}
              className={`rounded border px-2 py-1.5 ${
                highlightedFragmentIds?.has(fragment.id)
                  ? PANEL_HIGHLIGHT_CLASS
                  : "border-border/70 bg-background"
              }`}
            >
              <p>
                <LegislationLocatorLink
                  locator={fragment.sourceLocator}
                  href={fragment.legislationUrl}
                />
              </p>
              <p className="mt-1 text-[12px] leading-relaxed">{fragment.sourceExcerpt}</p>
              {showDeveloperFields ? (
                <p className="mt-1 font-mono text-[10px] text-primary">
                  {fragment.propositionIds.join(", ")}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {sources.length > 0 ? (
        <ul className="mt-2 space-y-1.5">
          {sources.map((source) => (
            <li
              key={source.propositionId}
              className={`rounded px-1 py-0.5 text-[11px] ${
                highlightedPropositionIds?.has(source.propositionId) ? PANEL_HIGHLIGHT_CLASS : ""
              }`}
            >
              <span className={META_CHIP_CLASS}>{source.roleLabel}</span>{" "}
              {showDeveloperFields ? (
                <>
                  <span className="font-mono text-primary">{source.propositionId}</span>
                  {source.fragmentLocator !== "not available from current export" ? (
                    <span className="ml-1">
                      <LegislationLocatorLink
                        locator={source.fragmentLocator}
                        href={source.legislationUrl}
                      />
                    </span>
                  ) : null}
                </>
              ) : null}
              {!compact && source.evidenceExcerpt !== "not available from current export" ? (
                <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
                  {source.evidenceExcerpt}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function AssessmentContextSection(props: {
  contexts: AssessmentContextView[];
  contextAssessments: Record<string, ContextAssessmentFlags>;
  onToggleFlag: (locator: string, flag: ContextAssessmentFlag) => void;
  showControls?: boolean;
  highlightedContextLocators?: ReadonlySet<string>;
  showDeveloperFields?: boolean;
  title?: string;
  description?: string;
}): JSX.Element | null {
  const {
    contexts,
    contextAssessments,
    onToggleFlag,
    showControls = false,
    highlightedContextLocators,
    showDeveloperFields = true,
    title = "Needed to assess this statement",
    description = "These references are needed to understand the legal effect, but may not have been incorporated into the statement.",
  } = props;
  if (contexts.length === 0) {
    return null;
  }
  return (
    <section className={showDeveloperFields ? "rw-panel-context" : "space-y-3"}>
      {showDeveloperFields ? (
        <>
          <p className="text-[12px] font-medium text-foreground">{title}</p>
          <p className="mt-1 text-[11px] text-muted-foreground">{description}</p>
        </>
      ) : null}
      <ul className={`list-none space-y-3 ${showDeveloperFields ? "mt-2" : ""}`}>
        {contexts.map((context, index) => (
          <AssessmentContextItem
            key={`${index}:${context.locator}`}
            context={context}
            flags={contextAssessments[context.locator] ?? {}}
            onToggleFlag={onToggleFlag}
            showControls={showControls}
            highlighted={highlightedContextLocators?.has(context.locator)}
            showDeveloperFields={showDeveloperFields}
          />
        ))}
      </ul>
    </section>
  );
}

function PropositionPanel(props: {
  propositions: PropositionReviewView[];
  issuesById: Record<string, PropositionIssue[]>;
  onToggleIssue: (propositionId: string, issue: PropositionIssue) => void;
  highlightedPropositionIds?: ReadonlySet<string>;
  showDeveloperFields?: boolean;
}): JSX.Element {
  const {
    propositions,
    issuesById,
    onToggleIssue,
    highlightedPropositionIds,
    showDeveloperFields = true,
  } = props;
  if (propositions.length === 0) {
    return <p className="text-sm italic text-muted-foreground">No propositions linked.</p>;
  }
  return (
    <div className="space-y-2">
      {propositions.map((proposition) => {
        const issues = issuesById[proposition.propositionId] ?? [];
        const linked = Boolean(highlightedPropositionIds?.has(proposition.propositionId));
        return (
          <div
            key={proposition.propositionId}
            className={`rounded-lg border px-3 py-2 ${
              issues.length > 0
                ? "border-amber-600/40 bg-amber-950/5"
                : linked
                  ? PANEL_HIGHLIGHT_CLASS
                  : "border-border/75"
            }`}
          >
            <div className="mb-1 flex flex-wrap gap-2">
              <span className={META_CHIP_CLASS}>{proposition.roleLabel}</span>
              {showDeveloperFields ? (
                <span className="font-mono text-[10px] text-primary">{proposition.propositionId}</span>
              ) : null}
            </div>
            <p className="text-[13px] leading-relaxed">{proposition.propositionText}</p>
            {proposition.sourceExcerpt !== "not available from current export" ? (
              <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground line-clamp-3">
                {proposition.sourceExcerpt}
              </p>
            ) : null}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {PROPOSITION_ISSUE_OPTIONS.map((option) => (
                <ToggleChip
                  key={option.value}
                  label={option.label}
                  active={issues.includes(option.value)}
                  onClick={() => onToggleIssue(proposition.propositionId, option.value)}
                  compact
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function StatementReviewWorkbench(props: {
  runId: string;
  apiBaseUrl?: string;
  statement: LawStatementRow;
  quality: StatementQualityAssessment | null;
  isPropositionMatcherCandidate: boolean;
  propositionById: Map<string, PropositionRow>;
  sourceById: Map<string, SourceRow>;
  snapshotById?: Map<string, SourceSnapshotRow>;
  fragmentById: Map<string, SourceFragmentRow>;
  sourceFragments: SourceFragmentRow[];
  sourceLegalEffects?: SourceLegalEffectsArtifactRow | null;
  decisionExplanationIndex?: DecisionExplanationIndex | null;
  heuristicsById?: Map<string, HeuristicDefinition>;
  sourceCompletenessByPropositionId: Map<string, string>;
  onNext?: () => void;
  onPrevious?: () => void;
  positionLabel?: string;
  filterStatementIds: string[];
}): JSX.Element {
  const {
    runId,
    apiBaseUrl = (process.env.NEXT_PUBLIC_LAW_PROPOSITION_EXTRACTOR_API_BASE_URL ?? "http://127.0.0.1:8010").replace(
      /\/+$/,
      "",
    ),
    statement,
    quality,
    isPropositionMatcherCandidate,
    propositionById,
    sourceById,
    snapshotById = new Map(),
    fragmentById,
    sourceFragments,
    sourceLegalEffects = null,
    decisionExplanationIndex = null,
    heuristicsById = new Map(),
    sourceCompletenessByPropositionId,
    onNext,
    onPrevious,
    positionLabel,
    filterStatementIds,
  } = props;

  const [review, setReview] = useState<WorkbenchReview>(() => emptyWorkbenchReview());
  const [selectedCompositionSegmentId, setSelectedCompositionSegmentId] = useState<string | null>(
    null,
  );
  const [selectedInlineReferenceId, setSelectedInlineReferenceId] = useState<string | null>(null);
  const [workspaceReferenceIds, setWorkspaceReferenceIds] = useState<string[]>([]);

  useEffect(() => {
    setReview(loadWorkbenchReview(runId, statement.id));
    setSelectedCompositionSegmentId(null);
    setSelectedInlineReferenceId(null);
    setWorkspaceReferenceIds([]);
  }, [runId, statement.id]);

  const persistReview = useCallback(
    (next: WorkbenchReview) => {
      setReview(next);
      saveWorkbenchReview(runId, statement.id, next);
    },
    [runId, statement.id],
  );

  const composition = useMemo(
    () =>
      buildWorkbenchComposition(statement, {
        propositionById,
        sourceById,
        fragmentById,
        sourceCompletenessByPropositionId,
      }),
    [statement, propositionById, sourceById, fragmentById, sourceCompletenessByPropositionId],
  );

  const typedLegalContext = useMemo(
    () => buildTypedLegalContextSections(statement, propositionById),
    [statement, propositionById],
  );

  const primaryProposition = useMemo(() => {
    const ids = statement.source_proposition_ids ?? [];
    for (const id of ids) {
      const row = propositionById.get(String(id));
      if (row) {
        return row;
      }
    }
    return null;
  }, [statement, propositionById]);

  const legislativeHeadingDisplay = useMemo(() => {
    if (!primaryProposition?.source_fragment_id) {
      return null;
    }
    const frag = fragmentById.get(primaryProposition.source_fragment_id);
    const nearest = nearestProvisionHeading(frag, fragmentById);
    if (!nearest) {
      return null;
    }
    return formatStructuralHeadingDisplay(nearest.number_label, nearest.heading_text) || null;
  }, [primaryProposition, fragmentById]);

  const assessmentContext = useMemo(() => {
    const genericStatement = statementWithGenericContextOnly(statement);
    const resolutions = buildContextRequirementResolutions(genericStatement, {
      sourceFragments,
      propositionById,
      fragmentById,
    });
    return buildAssessmentContextViews(resolutions);
  }, [statement, sourceFragments, propositionById, fragmentById]);

  const compositionSegments = useMemo(() => {
    if (statementHasExportCompositionTrace(statement)) {
      return segmentsFromExportCompositionTrace(statement);
    }
    return buildStatementCompositionSegments({
      statement,
      context: {
        propositionById,
        sourceById,
        fragmentById,
        sourceCompletenessByPropositionId,
      },
      lawFragments: composition.compositionLawFragments,
    });
  }, [
    statement,
    propositionById,
    sourceById,
    fragmentById,
    sourceCompletenessByPropositionId,
    composition.compositionLawFragments,
  ]);

  const compositionContext = useMemo(
    () => ({
      propositionById,
      sourceById,
      fragmentById,
      sourceCompletenessByPropositionId,
    }),
    [propositionById, sourceById, fragmentById, sourceCompletenessByPropositionId],
  );

  const classifiedPropositions = useMemo(
    () =>
      classifyWorkbenchPropositions({
        statement,
        propositions: composition.propositions,
        compositionSourcePropositionIds: composition.compositionSources.map(
          (source) => source.propositionId,
        ),
        context: compositionContext,
      }),
    [statement, composition.propositions, composition.compositionSources, compositionContext],
  );

  const workbenchLegalReferences = useMemo(
    () =>
      buildWorkbenchLegalReferences({
        statement,
        assessmentContext,
        propositionById,
        sourceFragments,
        fragmentById,
        classifiedPropositions: [
          ...classifiedPropositions.main,
          ...classifiedPropositions.supporting,
        ],
        compositionLawFragments: composition.compositionLawFragments,
      }),
    [
      statement,
      assessmentContext,
      propositionById,
      sourceFragments,
      fragmentById,
      classifiedPropositions,
      composition.compositionLawFragments,
    ],
  );

  const inlineStatementParts = useMemo(
    () => workbenchLegalReferences.partsBySourceId.get("statement") ?? [],
    [workbenchLegalReferences.partsBySourceId],
  );

  const inlineLegalReferences = useMemo(
    () => workbenchLegalReferences.referencesBySourceId.get("statement") ?? [],
    [workbenchLegalReferences.referencesBySourceId],
  );

  const selectedCompositionSegment = useMemo(
    () => compositionSegments.find((segment) => segment.id === selectedCompositionSegmentId) ?? null,
    [compositionSegments, selectedCompositionSegmentId],
  );

  const allReferencesById = useMemo(
    () => referenceById(workbenchLegalReferences.allReferences),
    [workbenchLegalReferences.allReferences],
  );

  const selectedInlineReference = useMemo(
    () =>
      selectedInlineReferenceId
        ? (allReferencesById.get(selectedInlineReferenceId) ?? null)
        : null,
    [allReferencesById, selectedInlineReferenceId],
  );

  const workspaceReferences = useMemo(
    () => resolveWorkspaceReferences(workspaceReferenceIds, allReferencesById),
    [workspaceReferenceIds, allReferencesById],
  );

  const handleSelectInlineReference = useCallback((referenceId: string | null) => {
    if (!referenceId) {
      setSelectedInlineReferenceId(null);
      return;
    }
    setWorkspaceReferenceIds((current) => addReferenceToWorkspace(current, referenceId));
    setSelectedInlineReferenceId(referenceId);
  }, []);

  const handleWorkspaceSelectReference = useCallback((referenceId: string) => {
    setSelectedInlineReferenceId(referenceId);
  }, []);

  const handleRemoveWorkspaceReference = useCallback((referenceId: string) => {
    setWorkspaceReferenceIds((current) => {
      const nextWorkspace = removeReferenceFromWorkspace(current, referenceId);
      setSelectedInlineReferenceId((currentSelected) =>
        selectedReferenceAfterRemoval(current, referenceId, currentSelected),
      );
      return nextWorkspace;
    });
  }, []);

  const legalContextMobilePanel = useMemo(
    () =>
      selectedInlineReference ? (
        <LegalContextPanel
          references={[selectedInlineReference]}
          selectedReferenceId={selectedInlineReference.id}
          onSelectReference={handleWorkspaceSelectReference}
          propositionById={propositionById}
          variant="drawer"
          className="mt-2 lg:hidden"
        />
      ) : null,
    [handleWorkspaceSelectReference, propositionById, selectedInlineReference],
  );

  const highlightedLawFragmentIds = useMemo(() => {
    const ids = new Set<string>();
    for (const id of selectedCompositionSegment?.lawFragmentIds ?? []) {
      ids.add(id);
    }
    for (const id of selectedInlineReference?.sourceFragmentIds ?? []) {
      ids.add(id);
    }
    return ids.size > 0 ? ids : undefined;
  }, [selectedCompositionSegment, selectedInlineReference]);

  const highlightedPropositionIds = useMemo(() => {
    const ids = new Set<string>();
    for (const id of selectedCompositionSegment?.propositionIds ?? []) {
      ids.add(id);
    }
    for (const id of selectedInlineReference?.propositionIds ?? []) {
      ids.add(id);
    }
    return ids.size > 0 ? ids : undefined;
  }, [selectedCompositionSegment, selectedInlineReference]);

  const highlightedContextLocators = useMemo(() => {
    const locators = new Set<string>();
    for (const locator of selectedCompositionSegment?.contextLocators ?? []) {
      locators.add(locator);
    }
    if (selectedInlineReference?.locator) {
      locators.add(selectedInlineReference.locator);
    }
    return locators.size > 0 ? locators : undefined;
  }, [selectedCompositionSegment, selectedInlineReference]);

  const compositionPropositions = useMemo(() => {
    const compositionPropositionIds = new Set(
      composition.compositionSources.map((source) => source.propositionId),
    );
    return composition.propositions.filter((proposition) =>
      compositionPropositionIds.has(proposition.propositionId),
    );
  }, [composition.compositionSources, composition.propositions]);

  const legislationQuickLinks = useMemo(() => {
    const byUrl = new Map<string, string>();
    for (const fragment of composition.compositionLawFragments) {
      if (fragment.legislationUrl && !byUrl.has(fragment.legislationUrl)) {
        byUrl.set(fragment.legislationUrl, fragment.sourceLocator);
      }
    }
    for (const source of composition.compositionSources) {
      if (source.legislationUrl && !byUrl.has(source.legislationUrl)) {
        byUrl.set(source.legislationUrl, source.fragmentLocator);
      }
    }
    return Array.from(byUrl.entries()).map(([href, locator]) => ({ href, locator }));
  }, [composition.compositionLawFragments, composition.compositionSources]);

  const sourceContextLineages = useMemo(() => {
    const byKey = new Map<string, LegislationContextCrumb[]>();

    const addFromProposition = (propositionId: string, locator: string) => {
      if (!locator || locator === "not available from current export") {
        return;
      }
      const proposition = propositionById.get(propositionId);
      const sourceRecordId = proposition?.source_record_id?.trim();
      const source = sourceRecordId ? sourceById.get(sourceRecordId) : undefined;
      const instrumentLabel =
        shortInstrumentLabel((source as UnknownRecord | undefined) ?? undefined) ||
        source?.citation?.trim() ||
        source?.title?.trim() ||
        "Legislation";
      const crumbs = legislationContextCrumbs({
        sourceUrl: source?.source_url,
        instrumentLabel,
        locator,
      });
      const key = crumbs.map((crumb) => `${crumb.label}|${crumb.href ?? ""}`).join(">");
      if (!byKey.has(key)) {
        byKey.set(key, crumbs);
      }
    };

    for (const source of composition.compositionSources) {
      addFromProposition(source.propositionId, source.fragmentLocator);
    }
    for (const fragment of composition.compositionLawFragments) {
      for (const propositionId of fragment.propositionIds) {
        addFromProposition(propositionId, fragment.sourceLocator);
      }
    }

    return Array.from(byKey.values());
  }, [
    composition.compositionLawFragments,
    composition.compositionSources,
    propositionById,
    sourceById,
  ]);

  const sourceVersionProvenance = useMemo(() => {
    const propositionIds = propositionRefsForStatement(statement).map((ref) => ref.propositionId);
    const knowledgeBySnapshot = new Map<string, SourceLegalEffectsKnowledgeInput>();
    if (sourceLegalEffects) {
      const snapshotIds = new Set(
        sourceLegalEffects.effects
          .map((effect) => String(effect.source_snapshot_id ?? "").trim())
          .filter(Boolean),
      );
      for (const snapshotId of snapshotIds) {
        const snapshotEffects = sourceLegalEffects.effects.filter(
          (effect) => String(effect.source_snapshot_id ?? "").trim() === snapshotId,
        );
        knowledgeBySnapshot.set(snapshotId, {
          hasEffects: snapshotEffects.length > 0,
          hasFragmentLinks: effectHasFragmentLinks(
            snapshotEffects,
            sourceLegalEffects.effect_links,
          ),
          hasAffectingInstrumentIds: effectHasAffectingInstrumentIds(snapshotEffects),
          outstandingEffectsStatus: normalizeOutstandingEffectsStatus(
            sourceLegalEffects.outstanding_effects_status,
          ),
          anyAffectingInstrumentConsumed: snapshotEffects.some(
            (effect) =>
              String(effect.independent_consumption_status ?? "").trim() ===
              "consumed_in_current_run",
          ),
        });
      }
    }
    return collectSourceVersionProvenanceForStatement({
      propositionIds,
      propositionById,
      sourceById,
      snapshotById,
      fragmentById,
      sourceLegalEffectsKnowledgeBySnapshotId: knowledgeBySnapshot,
    });
  }, [
    fragmentById,
    propositionById,
    snapshotById,
    sourceById,
    sourceLegalEffects,
    statement,
  ]);

  const sourceLegalEffectsViews = useMemo(() => {
    if (!sourceLegalEffects) {
      return new Map<string, ReturnType<typeof buildSourceLegalEffectsView>>();
    }
    const views = new Map<string, ReturnType<typeof buildSourceLegalEffectsView>>();
    for (const provenance of sourceVersionProvenance) {
      const key = `${provenance.sourceRecordId}:${provenance.sourceSnapshotId ?? "none"}`;
      const propositions = provenance.propositionIds
        .map((id) => propositionById.get(id))
        .filter((row): row is PropositionRow => Boolean(row));
      views.set(
        key,
        buildSourceLegalEffectsView({
          sourceRecordId: provenance.sourceRecordId,
          sourceSnapshotId: provenance.sourceSnapshotId,
          propositions,
          artifact: sourceLegalEffects,
          fragmentById,
        }),
      );
    }
    return views;
  }, [fragmentById, propositionById, sourceLegalEffects, sourceVersionProvenance]);

  const mainPropositionGroups = useMemo(
    () => groupMainPropositionsByRole(classifiedPropositions.main),
    [classifiedPropositions.main],
  );

  const propositionRoleSummary = useMemo(
    () => formatMainPropositionRoleSummary(classifiedPropositions.mainRoleCounts),
    [classifiedPropositions.mainRoleCounts],
  );

  const visibleIssueLabels = useMemo(() => {
    if (!quality) {
      return [];
    }
    if (assessmentContext.length === 0) {
      return quality.issueLabels;
    }
    return quality.issueLabels.filter(
      (label) => !label.includes("unresolved context") && !label.includes("ambiguous context"),
    );
  }, [assessmentContext.length, quality]);

  const toggleVerdict = useCallback(
    (verdict: StatementVerdict) => {
      const hasVerdict = review.verdicts.includes(verdict);
      if (hasVerdict) {
        persistReview({
          ...review,
          verdicts: review.verdicts.filter((entry) => entry !== verdict),
        });
        return;
      }
      if (verdict === "accurate") {
        persistReview({ ...review, verdicts: ["accurate"] });
        return;
      }
      persistReview({
        ...review,
        verdicts: [...review.verdicts.filter((entry) => entry !== "accurate"), verdict],
      });
    },
    [persistReview, review],
  );

  const toggleFailureStage = useCallback(
    (stage: FailureStage) => {
      const nextStages = review.failure_stages.includes(stage)
        ? review.failure_stages.filter((entry) => entry !== stage)
        : [...review.failure_stages, stage];
      persistReview({ ...review, failure_stages: nextStages });
    },
    [persistReview, review],
  );

  const setSeverity = useCallback(
    (severity: ReviewSeverity) => {
      persistReview({ ...review, severity });
    },
    [persistReview, review],
  );

  const toggleFragmentMissing = useCallback(
    (fragmentId: string) => {
      const current = Boolean(review.fragment_missing_proposition[fragmentId]);
      persistReview({
        ...review,
        fragment_missing_proposition: {
          ...review.fragment_missing_proposition,
          [fragmentId]: !current,
        },
      });
    },
    [persistReview, review],
  );

  const toggleCoverageGap = useCallback(
    (fragmentId: string) => {
      const current = Boolean(review.fragment_coverage_gap[fragmentId]);
      persistReview({
        ...review,
        fragment_coverage_gap: {
          ...review.fragment_coverage_gap,
          [fragmentId]: !current,
        },
      });
    },
    [persistReview, review],
  );

  const completeness = useMemo(() => assessReviewCompleteness(review), [review]);

  const togglePropositionIssue = useCallback(
    (propositionId: string, issue: PropositionIssue) => {
      const current = review.proposition_issues[propositionId] ?? [];
      const nextIssues = current.includes(issue)
        ? current.filter((entry) => entry !== issue)
        : [...current, issue];
      persistReview({
        ...review,
        proposition_issues: {
          ...review.proposition_issues,
          [propositionId]: nextIssues,
        },
      });
    },
    [persistReview, review],
  );

  const toggleContextAssessmentFlag = useCallback(
    (locator: string, flag: ContextAssessmentFlag) => {
      const current = review.context_assessments[locator] ?? {};
      persistReview({
        ...review,
        context_assessments: {
          ...review.context_assessments,
          [locator]: {
            ...current,
            [flag]: !current[flag],
          },
        },
      });
    },
    [persistReview, review],
  );

  const handleExport = useCallback(() => {
    const allReviews = loadRunWorkbenchReviews(runId);
    const payload = buildWorkbenchReviewExport(
      runId,
      {
        ...allReviews,
        [statement.id]: review,
      },
      filterStatementIds,
    );
    downloadWorkbenchReviewExport(payload);
  }, [filterStatementIds, review, runId, statement.id]);

  return (
    <div>
      <div className="rw-section-header">
        <div className="flex flex-wrap items-center gap-2">
          {positionLabel ? (
            <span className="rw-section-header-label">{positionLabel}</span>
          ) : null}
          <span className={RW_SECTION_HEADER_STATUS[completeness.status]}>
            {REVIEW_STATUS_LABEL[completeness.status]}
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {onPrevious ? (
            <button type="button" onClick={onPrevious} className="rw-btn-secondary">
              ← Previous
            </button>
          ) : null}
          {onNext ? (
            <button type="button" onClick={onNext} className="rw-btn-cta-on-dark">
              Next →
            </button>
          ) : null}
          <button type="button" onClick={handleExport} className="rw-btn-secondary">
            Export reviews JSON
            {completeness.status === "draft_review" ? " (includes draft)" : ""}
          </button>
        </div>
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(280px,320px)] lg:items-start">
        <div className="space-y-4">
        <section className="rw-panel-statement">
          <p className={STAGE_LABEL}>Statement</p>
          <div className="mt-2">
            <StatementInlineReferenceText
              statementText={statement.statement_text}
              parts={inlineStatementParts}
              references={inlineLegalReferences}
              textClassName="text-lg font-medium leading-snug"
              selectedReferenceId={selectedInlineReferenceId}
              onSelectReference={handleSelectInlineReference}
              accumulateSelection
              mobilePanel={legalContextMobilePanel}
            />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className={META_CHIP_CLASS}>
              {presentationRoleLabel(statement.presentation_role)}
            </span>
            <span className={META_CHIP_CLASS}>{statement.standalone_status}</span>
            <span className={META_CHIP_CLASS}>{statement.confidence}</span>
            {propositionRoleSummary ? (
              <span className={META_CHIP_CLASS}>{propositionRoleSummary}</span>
            ) : quality ? (
              <span className={META_CHIP_CLASS}>{quality.uniquePropositionCount} propositions</span>
            ) : null}
            {isPropositionMatcherCandidate ? <span className={META_CHIP_CLASS}>Proposition Matcher</span> : null}
          </div>
          {sourceContextLineages.length > 0 ||
          sourceVersionProvenance.length > 0 ||
          legislativeHeadingDisplay ? (
            <div className="mt-3 space-y-2 rounded-md border border-sky-700/25 bg-sky-950/[0.04] px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                Source context
              </p>
              {legislativeHeadingDisplay ? (
                <p
                  className="text-[12px] leading-snug text-muted-foreground"
                  data-testid="statement-legislative-heading"
                >
                  {legislativeHeadingDisplay}
                </p>
              ) : null}
              {sourceContextLineages.map((crumbs, index) => (
                <SourceContextBreadcrumb
                  key={`${crumbs.map((c) => c.label).join(">")}-${index}`}
                  crumbs={crumbs}
                />
              ))}
              {sourceVersionProvenance.map((view) => {
                const effectsKey = `${view.sourceRecordId}:${view.sourceSnapshotId ?? "none"}`;
                const effectsView = sourceLegalEffectsViews.get(effectsKey) ?? null;
                return (
                  <SourceVersionSummary
                    key={effectsKey}
                    view={view}
                    runId={runId}
                    apiBaseUrl={apiBaseUrl}
                    sourceLegalEffectsView={effectsView}
                  />
                );
              })}
              {sourceContextLineages.length > 0 ? (
                <p className="text-[11px] leading-snug text-muted-foreground">
                  Breadcrumb links open the current public legislation.gov.uk webpage and may not
                  exactly match the snapshot Law Proposition Extractor consumed.
                </p>
              ) : null}
            </div>
          ) : legislationQuickLinks.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {legislationQuickLinks.map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 rounded border border-sky-700/35 bg-sky-950/10 px-2 py-0.5 font-mono text-[11px] leading-5 text-sky-950 hover:bg-sky-950/20 dark:text-sky-100"
                  title="Open live legislation page"
                >
                  <ExternalLink className="h-3 w-3 shrink-0 opacity-80" aria-hidden />
                  {link.locator}
                </a>
              ))}
            </div>
          ) : null}
          {visibleIssueLabels.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1">
              {visibleIssueLabels.map((label) => (
                <span key={label} className={WARN_CHIP_CLASS}>
                  {label}
                </span>
              ))}
            </div>
          ) : null}
        </section>

        <section className="rounded-lg border border-border/80 bg-background px-4 py-3 shadow-sm">
          <h3 className="text-[13px] font-medium text-foreground">Main propositions</h3>
          <p className="mt-1 text-[11px] text-muted-foreground">
            Why Law Proposition Extractor treats this statement as true — core claims, limits, definitions, and
            exceptions drawn from the source law.
          </p>
          {classifiedPropositions.main.length === 0 ? (
            <p className="mt-3 text-sm italic text-muted-foreground">No main propositions linked.</p>
          ) : (
            <div className="mt-3 space-y-4">
              {mainPropositionGroups.map((group) => (
                <ReviewerPropositionGroup
                  key={group.role}
                  title={group.label}
                  entries={group.items}
                  issuesById={review.proposition_issues}
                  onToggleIssue={togglePropositionIssue}
                  highlightedPropositionIds={highlightedPropositionIds}
                  defaultOpen={group.role === "core" || group.role === "constraint"}
                  partsBySourceId={workbenchLegalReferences.partsBySourceId}
                  referencesBySourceId={workbenchLegalReferences.referencesBySourceId}
                  selectedReferenceId={selectedInlineReferenceId}
                  onSelectReference={handleSelectInlineReference}
                  accumulateSelection
                  mobilePanel={legalContextMobilePanel}
                />
              ))}
            </div>
          )}
        </section>

        {hasTypedLegalContext(typedLegalContext) ? (
          <section className="rounded-lg border border-border/80 bg-background px-4 py-3 shadow-sm">
            <TypedLegalContextSection sections={typedLegalContext} />
          </section>
        ) : null}

        <StatementWhyPanel
          statement={statement}
          primaryProposition={primaryProposition}
          propositionById={propositionById}
          fragmentById={fragmentById}
          decisionExplanationIndex={decisionExplanationIndex}
          heuristics={heuristicsById}
        />

        <CollapsibleWorkbenchSection
          title="Supporting propositions"
          description="Additional propositions that support the statement but are not the primary legal claim."
          count={classifiedPropositions.supporting.length}
          defaultOpen={false}
        >
          {classifiedPropositions.supporting.length === 0 ? (
            <p className="text-sm italic text-muted-foreground">No supporting propositions linked.</p>
          ) : (
            <div className="space-y-2">
              {classifiedPropositions.supporting.map((entry) => {
                const propositionSourceId = `proposition:${entry.proposition.propositionId}`;
                const excerptSourceId = `${propositionSourceId}:excerpt`;
                return (
                  <ReviewerPropositionItem
                    key={entry.proposition.propositionId}
                    entry={entry}
                    issues={review.proposition_issues[entry.proposition.propositionId] ?? []}
                    onToggleIssue={togglePropositionIssue}
                    highlighted={highlightedPropositionIds?.has(entry.proposition.propositionId)}
                    propositionParts={workbenchLegalReferences.partsBySourceId.get(
                      propositionSourceId,
                    )}
                    propositionReferences={
                      workbenchLegalReferences.referencesBySourceId.get(propositionSourceId) ?? []
                    }
                    excerptParts={workbenchLegalReferences.partsBySourceId.get(excerptSourceId)}
                    excerptReferences={
                      workbenchLegalReferences.referencesBySourceId.get(excerptSourceId) ?? []
                    }
                    selectedReferenceId={selectedInlineReferenceId}
                    onSelectReference={handleSelectInlineReference}
                    accumulateSelection
                    mobilePanel={legalContextMobilePanel}
                  />
                );
              })}
            </div>
          )}
        </CollapsibleWorkbenchSection>

        {assessmentContext.length > 0 ? (
          <CollapsibleWorkbenchSection
            title="Other referenced context"
            description="References needed to understand the legal effect, even when not written into the statement."
            count={assessmentContext.length}
            defaultOpen={!hasTypedLegalContext(typedLegalContext)}
          >
            <AssessmentContextSection
              contexts={assessmentContext}
              contextAssessments={review.context_assessments}
              onToggleFlag={toggleContextAssessmentFlag}
              showControls
              highlightedContextLocators={highlightedContextLocators}
              showDeveloperFields={false}
            />
          </CollapsibleWorkbenchSection>
        ) : null}

        <section className="rw-panel-verdict space-y-4">
          <h3 className={RW_STAGE_LABEL_ON_DARK}>Verdict</h3>

          <ReviewQualityPanel status={completeness.status} reasons={completeness.reasons} />

          <div className="space-y-1">
            <p className="text-[11px] text-navy-foreground/70">Overall verdict</p>
            <div className="flex flex-wrap gap-1.5">
              {STATEMENT_VERDICT_OPTIONS.map((option) => (
                <ToggleChip
                  key={option.value}
                  label={option.label}
                  active={review.verdicts.includes(option.value)}
                  onClick={() => toggleVerdict(option.value)}
                  className={verdictButtonClass(
                    option.value,
                    review.verdicts.includes(option.value),
                  )}
                />
              ))}
            </div>
          </div>

          <div className="space-y-1">
            <p className="text-[11px] text-navy-foreground/70">Failure stages</p>
            <div className="flex flex-wrap gap-1.5">
              {FAILURE_STAGE_OPTIONS.map((option) => (
                <ToggleChip
                  key={option.value}
                  label={option.label}
                  active={review.failure_stages.includes(option.value)}
                  onClick={() => toggleFailureStage(option.value)}
                  compact
                />
              ))}
            </div>
          </div>

          <div className="space-y-1">
            <p className="text-[11px] text-navy-foreground/70">Severity</p>
            <div className="flex flex-wrap gap-1.5">
              {REVIEW_SEVERITY_OPTIONS.filter((option) => option.value !== "").map((option) => (
                <ToggleChip
                  key={option.value}
                  label={option.label}
                  active={review.severity === option.value}
                  onClick={() => setSeverity(option.value)}
                  compact
                />
              ))}
            </div>
          </div>

          <label className="flex flex-col gap-1 text-xs">
            <span className="uppercase tracking-wide text-navy-foreground/60">Notes (optional)</span>
            <textarea
              value={review.free_text_notes}
              onChange={(event) =>
                persistReview({ ...review, free_text_notes: event.target.value })
              }
              rows={2}
              placeholder="Brief reviewer note"
              className="w-full rounded border border-navy-border bg-navy-muted px-2 py-1.5 text-[12px] text-navy-foreground outline-none focus:border-navy-foreground/40"
            />
          </label>

          {review.updated_at ? (
            <p className="text-[10px] text-navy-foreground/50">
              Updated {new Date(review.updated_at).toLocaleString()}
              {review.completed_at
                ? ` · Completed ${new Date(review.completed_at).toLocaleString()}`
                : ""}
            </p>
          ) : null}
        </section>

        <details className="rounded-lg border border-dashed border-border/80 bg-muted/[0.08] px-4 py-3">
          <summary className="cursor-pointer text-[12px] font-medium text-foreground">
            Developer details
          </summary>
          <div className="mt-4 space-y-4">
            <p className="font-mono text-[10px] text-muted-foreground">{statement.id}</p>
            <CompositionSourcesSection
              sources={composition.compositionSources}
              lawFragments={composition.compositionLawFragments}
              compact
              highlightedFragmentIds={highlightedLawFragmentIds}
              highlightedPropositionIds={highlightedPropositionIds}
            />
            <StatementIncorporationPanels statement={statement} />
            <div className="rw-panel-journey">
              <p className="mb-4 text-center text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                Provenance journey
              </p>

              <section className="rw-panel-journey-inner">
                <div>
                  <h3 className="text-[12px] font-medium text-foreground">
                    Used to build this statement
                  </h3>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    These sources contributed to the statement wording.
                  </p>
                </div>

                <div className="space-y-2">
                  <h4 className={STAGE_LABEL}>Law</h4>
                  <LawFragmentPanel
                    fragments={composition.compositionLawFragments}
                    missingById={review.fragment_missing_proposition}
                    coverageGapById={review.fragment_coverage_gap}
                    onToggleMissing={toggleFragmentMissing}
                    onToggleCoverageGap={toggleCoverageGap}
                    highlightedFragmentIds={highlightedLawFragmentIds}
                  />
                </div>

                <JourneyArrow />

                <div className="space-y-2">
                  <h4 className={STAGE_LABEL}>Propositions</h4>
                  <PropositionPanel
                    propositions={compositionPropositions}
                    issuesById={review.proposition_issues}
                    onToggleIssue={togglePropositionIssue}
                    highlightedPropositionIds={highlightedPropositionIds}
                  />
                </div>
              </section>

              <JourneyArrow />

              <section className="space-y-2">
                <h3 className={STAGE_LABEL}>Statement</h3>
                <div className="rounded-lg border border-border/75 bg-background px-3 py-3">
                  <StatementCompositionHighlight
                    segments={compositionSegments}
                    selectedSegmentId={selectedCompositionSegmentId}
                    onSelectSegment={setSelectedCompositionSegmentId}
                    showSegmentDetail={false}
                  />
                  {composition.fragments.some((fragment) => fragment.derived) ? (
                    <p className="mt-2 text-[10px] italic text-muted-foreground">
                      Some spans inferred from export text when explicit fragment maps are missing
                    </p>
                  ) : null}
                </div>
              </section>

              <AssessmentContextSection
                contexts={assessmentContext}
                contextAssessments={review.context_assessments}
                onToggleFlag={toggleContextAssessmentFlag}
                showControls
                highlightedContextLocators={highlightedContextLocators}
              />
              {hasTypedLegalContext(typedLegalContext) ? (
                <TypedLegalContextSection sections={typedLegalContext} showDeveloperFields />
              ) : null}
            </div>
          </div>
        </details>
        </div>

        <div className="hidden lg:block">
          <LegalContextPanel
            references={workspaceReferences}
            selectedReferenceId={selectedInlineReferenceId}
            onSelectReference={handleWorkspaceSelectReference}
            onRemoveReference={handleRemoveWorkspaceReference}
            propositionById={propositionById}
          />
        </div>
      </div>
    </div>
  );
}
