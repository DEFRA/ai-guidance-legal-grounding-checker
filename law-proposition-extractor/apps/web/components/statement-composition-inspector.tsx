"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  buildCompositionPropositionGroups,
  buildCoverageChecks,
  buildCoverageWarningItems,
  buildStatementFragments,
  buildStatementRecipe,
  EXPORT_FIELD_UNAVAILABLE,
  recipeRowsForFragment,
  SUPPORT_STATUS_CLASS,
  type CoverageWarningItem,
  type CoverageWarningSeverity,
  type SourceFragmentRow,
  type StatementFragmentView,
  type StatementRecipeRow,
} from "@/lib/law-statements-composition";
import {
  buildReviewerAssessmentExport,
  COMPOSITION_REVIEW_ISSUE_OPTIONS,
  downloadReviewerAssessmentExport,
  emptyReviewerAssessment,
  hasReviewerInput,
  INSPECTOR_REVIEW_MODES,
  loadReviewerAssessment,
  loadRunReviewerAssessments,
  MISSING_FROM_STATEMENT_OPTIONS,
  REVIEWER_RATING_OPTIONS,
  saveReviewerAssessment,
  type CompositionReviewIssue,
  type InspectorReviewMode,
  type MissingFromStatementAnswer,
  type ReviewerRating,
  type StatementReviewerAssessment,
} from "@/lib/law-statements-reviewer-state";
import {
  presentationRoleLabel,
  type LawStatementRow,
  type PropositionRow,
  type SourceRow,
  type StatementQualityAssessment,
} from "@/lib/law-statements-index";

const META_CHIP_CLASS =
  "rounded border border-border/70 bg-muted/80 px-2 py-0.5 font-mono text-[11px] leading-5 text-foreground/85";

const WARN_CHIP_CLASS =
  "rounded border border-amber-700/35 bg-amber-950/10 px-2 py-0.5 text-[10px] font-medium text-amber-950 dark:text-amber-100";

const PANEL_LABEL =
  "text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground";

const NA_CLASS = "italic text-muted-foreground";

const SELECT_CLASS =
  "w-full rounded border border-border/80 bg-background px-2 py-1 text-[12px] outline-none focus:border-primary";

const TEXTAREA_CLASS =
  "w-full rounded border border-border/80 bg-background px-2 py-1.5 text-[12px] outline-none focus:border-primary";

const HIGHLIGHT_FRAGMENT_CLASS =
  "border-priguidance-discovery/70 bg-priguidance-discovery/10 ring-1 ring-priguidance-discovery/30";

const HIGHLIGHT_ROW_CLASS = "bg-priguidance-discovery/10 ring-1 ring-inset ring-priguidance-discovery/25";

const COVERAGE_SEVERITY_CLASS: Record<CoverageWarningSeverity, string> = {
  gap: "border-red-700/35 bg-red-950/10",
  warning: "border-amber-700/35 bg-amber-950/10",
  unknown: "border-border/70 bg-muted/30",
  ok: "border-emerald-700/35 bg-emerald-950/10",
};

function RatingField(props: {
  label: string;
  value: ReviewerRating;
  onChange: (value: ReviewerRating) => void;
}): JSX.Element {
  const { label, value, onChange } = props;
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="uppercase tracking-wide text-muted-foreground">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as ReviewerRating)}
        className={SELECT_CLASS}
      >
        {REVIEWER_RATING_OPTIONS.map((option) => (
          <option key={option.value || "unreviewed"} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function ReviewModeSwitcher(props: {
  mode: InspectorReviewMode;
  onChange: (mode: InspectorReviewMode) => void;
}): JSX.Element {
  const { mode, onChange } = props;
  return (
    <div
      className="inline-flex rounded-lg border border-border/80 bg-muted/30 p-0.5"
      role="tablist"
      aria-label="Composition inspector review mode"
    >
      {INSPECTOR_REVIEW_MODES.map((option) => {
        const active = mode === option.value;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(option.value)}
            className={`rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors ${
              active
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function RecipeTable(props: {
  rows: StatementRecipeRow[];
  recipeRowNotes: Record<string, string>;
  highlightedRowIds: Set<string>;
  onRecipeRowNoteChange: (rowId: string, note: string) => void;
  compact?: boolean;
}): JSX.Element {
  const { rows, recipeRowNotes, highlightedRowIds, onRecipeRowNoteChange, compact = false } = props;

  if (rows.length === 0) {
    return <p className={`text-sm ${NA_CLASS}`}>{EXPORT_FIELD_UNAVAILABLE}</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border/80">
      <table className="min-w-full border-collapse text-left text-[12px]">
        <thead className="bg-muted/40 text-[10px] uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="border-b border-border/70 px-2 py-2 font-semibold">Statement fragment</th>
            <th className="border-b border-border/70 px-2 py-2 font-semibold">Proposition ids</th>
            <th className="border-b border-border/70 px-2 py-2 font-semibold">Proposition text</th>
            <th className="border-b border-border/70 px-2 py-2 font-semibold">Source locator</th>
            <th className="border-b border-border/70 px-2 py-2 font-semibold">Source excerpt</th>
            <th className="border-b border-border/70 px-2 py-2 font-semibold">Support</th>
            {!compact ? (
              <th className="border-b border-border/70 px-2 py-2 font-semibold">Reviewer notes</th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const highlighted = highlightedRowIds.has(row.rowId);
            return (
              <tr
                key={row.rowId}
                className={`align-top odd:bg-background even:bg-muted/[0.12] ${
                  highlighted ? HIGHLIGHT_ROW_CLASS : ""
                }`}
              >
                <td className="border-b border-border/50 px-2 py-2 leading-relaxed">
                  {row.statement_fragment === EXPORT_FIELD_UNAVAILABLE ? (
                    <span className={NA_CLASS}>{row.statement_fragment}</span>
                  ) : (
                    row.statement_fragment
                  )}
                </td>
                <td className="border-b border-border/50 px-2 py-2 font-mono text-[11px]">
                  {row.supporting_proposition_ids.map((propositionId) => (
                    <div key={propositionId}>
                      <Link
                        href={`/propositions?search=${encodeURIComponent(propositionId)}`}
                        className="text-primary underline-offset-2 hover:underline"
                      >
                        {propositionId}
                      </Link>
                    </div>
                  ))}
                </td>
                <td className="border-b border-border/50 px-2 py-2 leading-relaxed">
                  {row.proposition_text === EXPORT_FIELD_UNAVAILABLE ? (
                    <span className={NA_CLASS}>{row.proposition_text}</span>
                  ) : (
                    row.proposition_text
                  )}
                </td>
                <td className="border-b border-border/50 px-2 py-2 font-mono text-[11px]">
                  {row.source_locator === EXPORT_FIELD_UNAVAILABLE ? (
                    <span className={NA_CLASS}>{row.source_locator}</span>
                  ) : (
                    row.source_locator
                  )}
                </td>
                <td
                  className={`max-w-[16rem] border-b border-border/50 px-2 py-2 leading-relaxed ${
                    highlighted ? "bg-priguidance-discovery/5" : ""
                  }`}
                >
                  {row.source_excerpt === EXPORT_FIELD_UNAVAILABLE ? (
                    <span className={NA_CLASS}>{row.source_excerpt}</span>
                  ) : (
                    <span className={highlighted ? "" : "line-clamp-6"}>{row.source_excerpt}</span>
                  )}
                </td>
                <td className="border-b border-border/50 px-2 py-2">
                  <span
                    className={`inline-flex rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${SUPPORT_STATUS_CLASS[row.support_status]}`}
                  >
                    {row.support_status}
                  </span>
                </td>
                {!compact ? (
                  <td className="min-w-[10rem] border-b border-border/50 px-2 py-2">
                    <textarea
                      value={recipeRowNotes[row.rowId] ?? ""}
                      onChange={(event) => onRecipeRowNoteChange(row.rowId, event.target.value)}
                      rows={3}
                      placeholder="Local reviewer notes"
                      className={TEXTAREA_CLASS}
                    />
                  </td>
                ) : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FragmentList(props: {
  fragments: StatementFragmentView[];
  selectedFragmentId: string | null;
  onSelectFragment: (fragmentId: string) => void;
}): JSX.Element {
  const { fragments, selectedFragmentId, onSelectFragment } = props;
  return (
    <div className="space-y-2">
      {fragments.map((fragment) => {
        const selected = selectedFragmentId === fragment.id;
        return (
          <button
            key={fragment.id}
            type="button"
            onClick={() => onSelectFragment(fragment.id)}
            className={`w-full rounded-md border px-3 py-2 text-left text-sm leading-relaxed transition-colors ${
              selected
                ? HIGHLIGHT_FRAGMENT_CLASS
                : "border-border/75 bg-muted/[0.18] hover:border-priguidance-discovery/40"
            }`}
          >
            <p>{fragment.text}</p>
            {fragment.derived ? (
              <p className={`mt-1 text-[10px] ${NA_CLASS}`}>
                Derived from export text (no explicit fragment map)
              </p>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

function CoverageWarningChecklist(props: {
  items: CoverageWarningItem[];
  missingFromStatement: Record<string, MissingFromStatementAnswer>;
  onMissingFromStatementChange: (itemId: string, value: MissingFromStatementAnswer) => void;
}): JSX.Element {
  const { items, missingFromStatement, onMissingFromStatementChange } = props;

  if (items.length === 0) {
    return <p className={`text-sm ${NA_CLASS}`}>{EXPORT_FIELD_UNAVAILABLE}</p>;
  }

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div
          key={item.id}
          className={`rounded-md border px-3 py-2 ${COVERAGE_SEVERITY_CLASS[item.severity]}`}
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="space-y-1">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {item.category.replaceAll("_", " ")} · {item.label}
              </p>
              <p
                className={`text-[12px] leading-relaxed ${
                  item.detail === EXPORT_FIELD_UNAVAILABLE ? NA_CLASS : "text-foreground"
                }`}
              >
                {item.detail}
              </p>
              {!item.fromExport && item.detail !== EXPORT_FIELD_UNAVAILABLE ? (
                <p className={`text-[10px] ${NA_CLASS}`}>Inferred from current export</p>
              ) : null}
            </div>
            <label className="min-w-[12rem] flex-shrink-0 text-[11px]">
              <span className="mb-1 block uppercase tracking-wide text-muted-foreground">
                Missing from statement?
              </span>
              <select
                value={missingFromStatement[item.id] ?? ""}
                onChange={(event) =>
                  onMissingFromStatementChange(
                    item.id,
                    event.target.value as MissingFromStatementAnswer,
                  )
                }
                className={SELECT_CLASS}
              >
                {MISSING_FROM_STATEMENT_OPTIONS.map((option) => (
                  <option key={option.value || "unreviewed"} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
      ))}
    </div>
  );
}

function CompositionStack(props: {
  groups: ReturnType<typeof buildCompositionPropositionGroups>;
  wrongPropositionIds: string[];
  onToggleWrongProposition: (propositionId: string) => void;
}): JSX.Element {
  const { groups, wrongPropositionIds, onToggleWrongProposition } = props;

  if (groups.length === 0) {
    return <p className={`text-sm ${NA_CLASS}`}>{EXPORT_FIELD_UNAVAILABLE}</p>;
  }

  return (
    <div className="space-y-4">
      {groups.map((group) => (
        <div key={group.sourceLocator} className="rounded-lg border border-border/80">
          <header className="border-b border-border/70 bg-muted/30 px-3 py-2">
            <p className={PANEL_LABEL}>Source locator</p>
            <p className="font-mono text-[12px]">
              {group.sourceLocator === EXPORT_FIELD_UNAVAILABLE ? (
                <span className={NA_CLASS}>{group.sourceLocator}</span>
              ) : (
                group.sourceLocator
              )}
            </p>
          </header>
          <ol className="relative space-y-0 px-3 py-2">
            {group.items.map((item, index) => {
              const markedWrong = wrongPropositionIds.includes(item.propositionId);
              return (
                <li
                  key={`${item.recipeRowId}-${item.propositionId}`}
                  className={`relative border-l-2 py-2 pl-4 ${
                    markedWrong ? "border-red-500/70 bg-red-950/5" : "border-priguidance-discovery/30"
                  }`}
                >
                  {index < group.items.length - 1 ? (
                    <span className="absolute -left-[5px] top-4 h-2 w-2 rounded-full bg-priguidance-discovery/50" />
                  ) : (
                    <span className="absolute -left-[5px] top-4 h-2 w-2 rounded-full bg-primary" />
                  )}
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="space-y-1">
                      <div className="flex flex-wrap gap-2">
                        <span className={META_CHIP_CLASS}>{item.roleLabel}</span>
                        <span
                          className={`inline-flex rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${SUPPORT_STATUS_CLASS[item.supportStatus]}`}
                        >
                          {item.supportStatus}
                        </span>
                      </div>
                      <p className="font-mono text-[11px] text-primary">
                        <Link
                          href={`/propositions?search=${encodeURIComponent(item.propositionId)}`}
                          className="underline-offset-2 hover:underline"
                        >
                          {item.propositionId}
                        </Link>
                      </p>
                      <p className="text-[12px] leading-relaxed">{item.propositionText}</p>
                      {item.sourceExcerpt !== EXPORT_FIELD_UNAVAILABLE ? (
                        <p className="text-[11px] leading-relaxed text-muted-foreground">
                          {item.sourceExcerpt}
                        </p>
                      ) : null}
                    </div>
                    <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={markedWrong}
                        onChange={() => onToggleWrongProposition(item.propositionId)}
                      />
                      Wrong proposition
                    </label>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      ))}
    </div>
  );
}

function CompositionReviewControls(props: {
  issues: CompositionReviewIssue[];
  missingPropositionNote: string;
  onToggleIssue: (issue: CompositionReviewIssue) => void;
  onMissingPropositionNoteChange: (note: string) => void;
}): JSX.Element {
  const { issues, missingPropositionNote, onToggleIssue, onMissingPropositionNoteChange } = props;

  return (
    <div className="space-y-3 rounded-md border border-border/70 bg-muted/[0.12] p-3">
      <p className={PANEL_LABEL}>Merge assessment</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {COMPOSITION_REVIEW_ISSUE_OPTIONS.map((option) => {
          const checked = issues.includes(option.value);
          return (
            <label
              key={option.value}
              className="flex items-center gap-2 rounded border border-border/60 bg-background px-2 py-1.5 text-[12px]"
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => onToggleIssue(option.value)}
              />
              {option.label}
            </label>
          );
        })}
      </div>
      {issues.includes("missing_proposition_needed") ? (
        <label className="flex flex-col gap-1 text-xs">
          <span className="uppercase tracking-wide text-muted-foreground">
            Missing proposition note
          </span>
          <textarea
            value={missingPropositionNote}
            onChange={(event) => onMissingPropositionNoteChange(event.target.value)}
            rows={3}
            placeholder="Which proposition should be included?"
            className={TEXTAREA_CLASS}
          />
        </label>
      ) : null}
    </div>
  );
}

export function StatementCompositionInspector(props: {
  runId: string;
  statement: LawStatementRow;
  quality: StatementQualityAssessment | null;
  isPropositionMatcherCandidate: boolean;
  propositionById: Map<string, PropositionRow>;
  sourceById: Map<string, SourceRow>;
  fragmentById: Map<string, SourceFragmentRow>;
  sourceCompletenessByPropositionId: Map<string, string>;
}): JSX.Element {
  const {
    runId,
    statement,
    quality,
    isPropositionMatcherCandidate,
    propositionById,
    sourceById,
    fragmentById,
    sourceCompletenessByPropositionId,
  } = props;

  const [assessment, setAssessment] = useState<StatementReviewerAssessment>(() =>
    emptyReviewerAssessment(),
  );
  const [selectedFragmentId, setSelectedFragmentId] = useState<string | null>(null);

  useEffect(() => {
    setAssessment(loadReviewerAssessment(runId, statement.id));
    setSelectedFragmentId(null);
  }, [runId, statement.id]);

  const persistAssessment = useCallback(
    (next: StatementReviewerAssessment) => {
      setAssessment(next);
      saveReviewerAssessment(runId, statement.id, next);
    },
    [runId, statement.id],
  );

  const updateAssessmentField = useCallback(
    <K extends keyof StatementReviewerAssessment>(field: K, value: StatementReviewerAssessment[K]) => {
      persistAssessment({
        ...assessment,
        [field]: value,
      });
    },
    [assessment, persistAssessment],
  );

  const fragments = useMemo(
    () => buildStatementFragments(statement, propositionById),
    [statement, propositionById],
  );

  const recipe = useMemo(
    () =>
      buildStatementRecipe(statement, {
        propositionById,
        sourceById,
        fragmentById,
        sourceCompletenessByPropositionId,
      }),
    [statement, propositionById, sourceById, fragmentById, sourceCompletenessByPropositionId],
  );

  const coverageChecks = useMemo(() => buildCoverageChecks(statement, recipe), [statement, recipe]);

  const coverageWarningItems = useMemo(
    () => buildCoverageWarningItems(statement, coverageChecks),
    [statement, coverageChecks],
  );

  const compositionGroups = useMemo(
    () => buildCompositionPropositionGroups(statement, recipe),
    [statement, recipe],
  );

  const selectedFragment = useMemo(
    () => fragments.find((fragment) => fragment.id === selectedFragmentId) ?? null,
    [fragments, selectedFragmentId],
  );

  const highlightedRecipeRows = useMemo(() => {
    if (!selectedFragment) {
      return new Set<string>();
    }
    return new Set(recipeRowsForFragment(selectedFragment, recipe).map((row) => row.rowId));
  }, [recipe, selectedFragment]);

  const handleExport = useCallback(() => {
    const allAssessments = loadRunReviewerAssessments(runId);
    const payload = buildReviewerAssessmentExport(runId, {
      ...allAssessments,
      [statement.id]: assessment,
    });
    downloadReviewerAssessmentExport(payload);
  }, [assessment, runId, statement.id]);

  const handleReviewModeChange = useCallback(
    (mode: InspectorReviewMode) => {
      updateAssessmentField("review_mode", mode);
    },
    [updateAssessmentField],
  );

  const handleMissingFromStatementChange = useCallback(
    (itemId: string, value: MissingFromStatementAnswer) => {
      persistAssessment({
        ...assessment,
        coverage_missing_from_statement: {
          ...assessment.coverage_missing_from_statement,
          [itemId]: value,
        },
      });
    },
    [assessment, persistAssessment],
  );

  const handleToggleCompositionIssue = useCallback(
    (issue: CompositionReviewIssue) => {
      const nextIssues = assessment.composition_issues.includes(issue)
        ? assessment.composition_issues.filter((entry) => entry !== issue)
        : [...assessment.composition_issues, issue];
      persistAssessment({
        ...assessment,
        composition_issues: nextIssues,
      });
    },
    [assessment, persistAssessment],
  );

  const handleToggleWrongProposition = useCallback(
    (propositionId: string) => {
      const nextIds = assessment.wrong_proposition_ids.includes(propositionId)
        ? assessment.wrong_proposition_ids.filter((id) => id !== propositionId)
        : [...assessment.wrong_proposition_ids, propositionId];
      const nextIssues = assessment.composition_issues.includes("wrong_proposition_included")
        ? assessment.composition_issues
        : [...assessment.composition_issues, "wrong_proposition_included"];
      persistAssessment({
        ...assessment,
        wrong_proposition_ids: nextIds,
        composition_issues: nextIssues,
      });
    },
    [assessment, persistAssessment],
  );

  const reviewMode = assessment.review_mode;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ReviewModeSwitcher mode={reviewMode} onChange={handleReviewModeChange} />
        <button
          type="button"
          onClick={handleExport}
          className="rounded border border-border/80 bg-muted/40 px-2 py-1 text-[11px] font-medium hover:bg-muted/70"
        >
          Export assessments JSON
        </button>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.4fr)_minmax(0,0.9fr)]">
        <section className="space-y-3 rounded-lg border border-border/80 bg-background p-3">
          <header className="space-y-1">
            <h3 className={PANEL_LABEL}>Selected statement</h3>
            <p className="font-mono text-[10px] text-muted-foreground">{statement.id}</p>
          </header>

          {reviewMode === "evidence" ? (
            <div className="space-y-2">
              <p className={PANEL_LABEL}>Statement fragments</p>
              <FragmentList
                fragments={fragments}
                selectedFragmentId={selectedFragmentId}
                onSelectFragment={setSelectedFragmentId}
              />
              {selectedFragment ? (
                <p className="text-[11px] text-muted-foreground">
                  {highlightedRecipeRows.size} recipe row
                  {highlightedRecipeRows.size === 1 ? "" : "s"} linked to this fragment.
                </p>
              ) : (
                <p className="text-[11px] text-muted-foreground">
                  Select a fragment to highlight supporting recipe rows and source excerpts.
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm leading-relaxed text-foreground">{statement.statement_text}</p>
          )}

          <div className="flex flex-wrap gap-2">
            <span className={META_CHIP_CLASS}>{presentationRoleLabel(statement.presentation_role)}</span>
            <span className={META_CHIP_CLASS}>{statement.standalone_status}</span>
            <span className={META_CHIP_CLASS}>{statement.confidence}</span>
            {quality ? (
              <span className={META_CHIP_CLASS}>{quality.uniquePropositionCount} propositions</span>
            ) : null}
            {isPropositionMatcherCandidate ? <span className={META_CHIP_CLASS}>Proposition Matcher candidate</span> : null}
          </div>

          {quality && quality.issueLabels.length > 0 ? (
            <div className="space-y-1">
              {quality.issueLabels.map((label) => (
                <p key={label} className={WARN_CHIP_CLASS}>
                  {label}
                </p>
              ))}
            </div>
          ) : null}
        </section>

        <section className="space-y-4 rounded-lg border border-border/80 bg-background p-3">
          {reviewMode === "evidence" ? (
            <>
              <header className="space-y-1">
                <h3 className="text-base font-semibold">Evidence map</h3>
                <p className="text-[12px] text-muted-foreground">
                  Statement recipe linking final text to supporting propositions and source legal
                  text.
                </p>
              </header>
              <RecipeTable
                rows={recipe}
                recipeRowNotes={assessment.recipe_row_notes}
                highlightedRowIds={highlightedRecipeRows}
                onRecipeRowNoteChange={(rowId, note) => {
                  persistAssessment({
                    ...assessment,
                    recipe_row_notes: {
                      ...assessment.recipe_row_notes,
                      [rowId]: note,
                    },
                  });
                }}
              />
            </>
          ) : null}

          {reviewMode === "coverage" ? (
            <>
              <header className="space-y-1">
                <h3 className="text-base font-semibold">Coverage review</h3>
                <p className="text-[12px] text-muted-foreground">
                  Missing legal material — conditions, exceptions, scope, definitions,
                  cross-references, and unresolved context.
                </p>
              </header>
              <CoverageWarningChecklist
                items={coverageWarningItems}
                missingFromStatement={assessment.coverage_missing_from_statement}
                onMissingFromStatementChange={handleMissingFromStatementChange}
              />
            </>
          ) : null}

          {reviewMode === "composition" ? (
            <>
              <header className="space-y-1">
                <h3 className="text-base font-semibold">Composition review</h3>
                <p className="text-[12px] text-muted-foreground">
                  Supporting propositions grouped by source locator and role — assess whether this is
                  a good merge.
                </p>
              </header>
              <CompositionReviewControls
                issues={assessment.composition_issues}
                missingPropositionNote={assessment.missing_proposition_note}
                onToggleIssue={handleToggleCompositionIssue}
                onMissingPropositionNoteChange={(note) =>
                  updateAssessmentField("missing_proposition_note", note)
                }
              />
              <CompositionStack
                groups={compositionGroups}
                wrongPropositionIds={assessment.wrong_proposition_ids}
                onToggleWrongProposition={handleToggleWrongProposition}
              />
            </>
          ) : null}
        </section>

        <section className="space-y-4 rounded-lg border border-border/80 bg-background p-3">
          <header className="space-y-1">
            <h3 className="text-base font-semibold">Reviewer assessment</h3>
            <p className="text-[12px] text-muted-foreground">Stored locally in this browser.</p>
          </header>

          <div className="grid gap-3">
            <RatingField
              label="Accuracy"
              value={assessment.accuracy}
              onChange={(value) => updateAssessmentField("accuracy", value)}
            />
            <RatingField
              label="Completeness"
              value={assessment.completeness}
              onChange={(value) => updateAssessmentField("completeness", value)}
            />
            <RatingField
              label="Overreach"
              value={assessment.overreach}
              onChange={(value) => updateAssessmentField("overreach", value)}
            />
            <RatingField
              label="Composition quality"
              value={assessment.composition_quality}
              onChange={(value) => updateAssessmentField("composition_quality", value)}
            />
            <RatingField
              label="Proposition Matcher suitability"
              value={assessment.beatrice_suitability}
              onChange={(value) => updateAssessmentField("beatrice_suitability", value)}
            />
          </div>

          <label className="flex flex-col gap-1 text-xs">
            <span className="uppercase tracking-wide text-muted-foreground">Free text notes</span>
            <textarea
              value={assessment.free_text_notes}
              onChange={(event) => updateAssessmentField("free_text_notes", event.target.value)}
              rows={5}
              className={TEXTAREA_CLASS}
              placeholder="Overall reviewer notes for this statement"
            />
          </label>

          {hasReviewerInput(assessment) ? (
            <p className="text-[11px] text-muted-foreground">
              Last saved locally
              {assessment.updated_at ? ` at ${new Date(assessment.updated_at).toLocaleString()}` : ""}.
            </p>
          ) : null}
        </section>
      </div>
    </div>
  );
}
