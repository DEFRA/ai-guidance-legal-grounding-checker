/** @jsxImportSource react */
"use client";

import { useMemo, useState } from "react";

import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";
import type {
  DecisionExplanationIndex,
  HeuristicDefinition,
} from "@/lib/decision-explanations";
import {
  buildStatementExplanationViewModel,
  type LegalRuleGroupRow,
  type StatementExplanationViewModel,
} from "@/lib/statement-explanation";

const HELP_TEXT =
  "These explanations describe how Law Proposition Extractor processed the source and built this statement. They do not replace legal review.";

function MethodBadge(props: { label: string }): JSX.Element {
  return (
    <span className="inline-flex items-center rounded border border-border/70 bg-muted/40 px-1.5 py-0.5 text-[10px] font-medium text-foreground">
      {props.label}
      <span className="sr-only"> (method)</span>
    </span>
  );
}

function StatusText(props: { status: "present" | "unavailable" | "omitted" }): JSX.Element {
  const label =
    props.status === "present"
      ? "Recorded"
      : props.status === "unavailable"
        ? "Not recorded"
        : "Omitted";
  return <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>;
}

function StageBlock(props: {
  stage: StatementExplanationViewModel["stages"][number];
  showEvidence: boolean;
}): JSX.Element {
  const { stage, showEvidence } = props;
  const [detailsOpen, setDetailsOpen] = useState(false);
  return (
    <li className="rounded-md border border-border/70 bg-background px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-[12px] font-medium text-foreground">{stage.title}</h4>
        <StatusText status={stage.status} />
      </div>
      <p className="mt-1 text-[12px] leading-relaxed text-foreground/90">{stage.explanation}</p>
      {stage.methodLabels.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {stage.methodLabels.map((label) => (
            <MethodBadge key={label} label={label} />
          ))}
        </div>
      ) : null}
      {stage.decisions.some((d) => !d.heuristicAvailable) ? (
        <p className="mt-2 text-[11px] text-amber-800 dark:text-amber-200">
          Explanation rule metadata unavailable for one or more decisions. Decision evidence is still
          shown.
        </p>
      ) : null}
      {stage.decisions
        .filter((d) => d.heuristicAvailable && d.heuristicName)
        .slice(0, 2)
        .map((d) => (
          <div key={d.decisionId} className="mt-2 rounded border border-border/50 bg-muted/20 px-2 py-1.5">
            <p className="text-[11px] font-medium text-foreground">
              {d.heuristicName} — version {d.ruleVersion}
            </p>
            {d.heuristicSummary ? (
              <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
                {d.heuristicSummary}
              </p>
            ) : null}
          </div>
        ))}
      {stage.detailBlocks.length > 0 ? (
        <div className="mt-2 space-y-1.5">
          {stage.detailBlocks.map((block) => (
            <details key={`${block.title}-${block.decisionIds.join(",")}`} className="text-[11px]">
              <summary className="cursor-pointer font-medium text-foreground">{block.title}</summary>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-muted-foreground">
                {block.lines.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </details>
          ))}
        </div>
      ) : null}
      {showEvidence && stage.evidence.length > 0 ? (
        <div className="mt-2">
          <button
            type="button"
            className="text-[11px] text-sky-900 underline-offset-2 hover:underline dark:text-sky-100"
            aria-expanded={detailsOpen}
            onClick={() => setDetailsOpen((value) => !value)}
          >
            {detailsOpen ? "Hide evidence" : "Show evidence"}
          </button>
          {detailsOpen ? (
            <ul className="mt-1 space-y-1 text-[11px] text-muted-foreground">
              {stage.evidence.map((item) => (
                <li key={`${item.decisionId}:${item.kind}:${item.value}`}>
                  <span className="font-medium text-foreground/80">{item.label}:</span> {item.value}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {stage.diagnostics.length > 0 ? (
        <p className="mt-2 text-[11px] text-amber-800 dark:text-amber-200" role="status">
          Diagnostics: {stage.diagnostics.join("; ")}
        </p>
      ) : null}
    </li>
  );
}

export function StatementWhyPanel(props: {
  statement: LawStatementRow;
  primaryProposition: PropositionRow | null;
  propositionById: Map<string, PropositionRow>;
  fragmentById: Map<string, SourceFragmentRow>;
  decisionExplanationIndex: DecisionExplanationIndex | null;
  heuristics: Map<string, HeuristicDefinition>;
  legalRuleGroups?: LegalRuleGroupRow[];
  defaultOpen?: boolean;
}): JSX.Element {
  const {
    statement,
    primaryProposition,
    propositionById,
    fragmentById,
    decisionExplanationIndex,
    heuristics,
    legalRuleGroups = [],
    defaultOpen = false,
  } = props;
  const [open, setOpen] = useState(defaultOpen);
  const [showEvidence, setShowEvidence] = useState(false);
  const [techOpen, setTechOpen] = useState(false);

  const viewModel = useMemo(() => {
    if (!decisionExplanationIndex) {
      return null;
    }
    return buildStatementExplanationViewModel({
      statement,
      proposition: primaryProposition,
      propositionById,
      fragmentById,
      legalRuleGroups,
      decisionIndex: decisionExplanationIndex,
      heuristics,
    });
  }, [
    decisionExplanationIndex,
    statement,
    primaryProposition,
    propositionById,
    fragmentById,
    legalRuleGroups,
    heuristics,
  ]);

  return (
    <section
      className="rounded-lg border border-border/80 bg-background shadow-sm"
      data-testid="statement-why-panel"
    >
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        aria-expanded={open}
        aria-controls={`statement-why-${statement.id}`}
        onClick={() => setOpen((value) => !value)}
      >
        <div>
          <h3 className="text-[13px] font-medium text-foreground">Why did Law Proposition Extractor produce this?</h3>
          <p className="mt-0.5 text-[11px] text-muted-foreground">{HELP_TEXT}</p>
        </div>
        <span className="text-[11px] text-muted-foreground">{open ? "Hide" : "Show"}</span>
      </button>

      {open ? (
        <div
          id={`statement-why-${statement.id}`}
          className="space-y-3 border-t border-border/70 px-4 py-3"
          data-testid="statement-why-content"
        >
          {!viewModel || viewModel.availability === "missing_artifact" ? (
            <p className="text-[12px] leading-relaxed text-muted-foreground" role="status">
              {viewModel?.legacyMessage ??
                "Detailed decision explanations were not recorded for this run. Source evidence and legal context remain available."}
            </p>
          ) : (
            <>
              {viewModel.overview ? (
                <div>
                  <h4 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Overview
                  </h4>
                  <p className="mt-1 text-[13px] leading-relaxed text-foreground">
                    {viewModel.overview}
                  </p>
                </div>
              ) : null}

              {viewModel.legislativeHeading ? (
                <div data-testid="legislative-heading-context">
                  <h4 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Legislative heading
                  </h4>
                  <p className="mt-1 text-[13px] leading-relaxed text-foreground">
                    {viewModel.legislativeHeading.display}
                  </p>
                  <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
                    {viewModel.legislativeHeading.note}
                  </p>
                  {(viewModel.legislativeHeading.kind ||
                    viewModel.legislativeHeading.ownerLocator ||
                    viewModel.legislativeHeading.changeIds.length > 0 ||
                    viewModel.legislativeHeading.commentaryRefs.length > 0) && (
                    <details className="mt-1.5 text-[11px] text-muted-foreground">
                      <summary className="cursor-pointer font-medium text-foreground/80">
                        Heading technical details
                      </summary>
                      <ul className="mt-1 list-disc space-y-0.5 pl-4">
                        {viewModel.legislativeHeading.kind ? (
                          <li>Kind: {viewModel.legislativeHeading.kind}</li>
                        ) : null}
                        {viewModel.legislativeHeading.ownerLocator ? (
                          <li>Owner locator: {viewModel.legislativeHeading.ownerLocator}</li>
                        ) : null}
                        {viewModel.legislativeHeading.changeIds.length > 0 ? (
                          <li>
                            Change IDs: {viewModel.legislativeHeading.changeIds.join(", ")}
                          </li>
                        ) : null}
                        {viewModel.legislativeHeading.commentaryRefs.length > 0 ? (
                          <li>
                            Commentary refs:{" "}
                            {viewModel.legislativeHeading.commentaryRefs.join(", ")}
                          </li>
                        ) : null}
                      </ul>
                    </details>
                  )}
                </div>
              ) : null}

              {viewModel.stages.length > 0 ? (
                <div>
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <h4 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                      Stage timeline
                    </h4>
                    <button
                      type="button"
                      className="text-[11px] text-sky-900 underline-offset-2 hover:underline dark:text-sky-100"
                      onClick={() => setShowEvidence((value) => !value)}
                      aria-pressed={showEvidence}
                    >
                      {showEvidence ? "Hide evidence view" : "Evidence view"}
                    </button>
                  </div>
                  <ol className="space-y-2">
                    {viewModel.stages.map((stage) => (
                      <StageBlock key={stage.stageId} stage={stage} showEvidence={showEvidence} />
                    ))}
                  </ol>
                </div>
              ) : (
                <p className="text-[12px] text-muted-foreground" role="status">
                  No material decision explanations were found for this statement.
                </p>
              )}

              {viewModel.keyLegalLinks.length > 0 ? (
                <div>
                  <h4 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Key legal links
                  </h4>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-[12px] text-foreground/90">
                    {viewModel.keyLegalLinks.map((link) => (
                      <li key={link}>{link}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {viewModel.contextGroups.length > 0 ? (
                <div>
                  <h4 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Typed context from decisions
                  </h4>
                  <ul className="mt-1 space-y-2">
                    {viewModel.contextGroups.map((group) => (
                      <li key={group.role} className="text-[12px]">
                        <p className="font-medium">{group.title}</p>
                        <ul className="mt-0.5 list-disc pl-4 text-muted-foreground">
                          {group.items.map((item) => (
                            <li key={item.decisionId}>
                              {item.label}
                              {item.inheritedViaGroup ? " (via group)" : ""}
                            </li>
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {viewModel.diagnostics.length > 0 ? (
                <div role="status">
                  <h4 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-amber-800 dark:text-amber-200">
                    Material diagnostics
                  </h4>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-[12px] text-amber-900 dark:text-amber-100">
                    {viewModel.diagnostics.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <details
                className="rounded-md border border-dashed border-border/80 bg-muted/[0.08] px-3 py-2"
                open={techOpen}
                onToggle={(event) => setTechOpen((event.target as HTMLDetailsElement).open)}
                data-testid="statement-why-technical"
              >
                <summary className="cursor-pointer text-[12px] font-medium text-foreground">
                  Technical details
                </summary>
                <div className="mt-2 space-y-3 text-[11px] text-muted-foreground">
                  {viewModel.technicalDetails.parseDiagnostics.length > 0 ? (
                    <div>
                      <p className="font-medium text-foreground/80">Parse diagnostics</p>
                      <ul className="mt-1 list-disc pl-4">
                        {viewModel.technicalDetails.parseDiagnostics.map((line) => (
                          <li key={line}>{line}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {viewModel.technicalDetails.decisions.map((row) => (
                    <div
                      key={row.decisionId}
                      className="rounded border border-border/60 bg-background/80 px-2 py-1.5"
                      data-testid="statement-why-technical-decision"
                    >
                      <p>
                        <span className="font-medium text-foreground/80">decision ID:</span>{" "}
                        <span className="font-mono">{row.decisionId}</span>
                      </p>
                      <p>
                        <span className="font-medium text-foreground/80">rule:</span>{" "}
                        <span className="font-mono">
                          {row.ruleId}@{row.ruleVersion}
                        </span>
                        {row.heuristicName ? ` (${row.heuristicName})` : ""}
                      </p>
                      <p>
                        <span className="font-medium text-foreground/80">method:</span> {row.method}
                      </p>
                      <p>
                        <span className="font-medium text-foreground/80">subject:</span>{" "}
                        <span className="font-mono">
                          {row.subjectKind}:{row.subjectId}
                        </span>
                      </p>
                      {row.modelAlias ? (
                        <p>
                          <span className="font-medium text-foreground/80">model alias:</span>{" "}
                          {row.modelAlias}
                        </p>
                      ) : null}
                      {row.promptVersion ? (
                        <p>
                          <span className="font-medium text-foreground/80">prompt version:</span>{" "}
                          {row.promptVersion}
                        </p>
                      ) : null}
                      {row.codeReferences.length > 0 ? (
                        <p>
                          <span className="font-medium text-foreground/80">code references:</span>{" "}
                          {row.codeReferences.join("; ")}
                        </p>
                      ) : null}
                      {row.traceReferences.length > 0 ? (
                        <p>
                          <span className="font-medium text-foreground/80">trace refs:</span>{" "}
                          {row.traceReferences
                            .map((ref) => `${ref.kind}${ref.id ? `:${ref.id}` : ""}`)
                            .join("; ")}
                        </p>
                      ) : null}
                      {row.diagnostics.length > 0 ? (
                        <p role="status">
                          <span className="font-medium text-amber-800 dark:text-amber-200">
                            diagnostics:
                          </span>{" "}
                          {row.diagnostics.join("; ")}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </details>
            </>
          )}
        </div>
      ) : null}
    </section>
  );
}
