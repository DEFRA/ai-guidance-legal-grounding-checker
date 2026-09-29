/**
 * Pure statement-level projection of decision_explanations into a Workbench view model.
 * No network calls. No heuristic reruns. No LLM-generated overview prose.
 */

import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";
import {
  STAGE_DISPLAY_TITLES,
  STAGE_TIMELINE_ORDER,
  methodLabel,
  type DecisionExplanation,
  type DecisionExplanationIndex,
  type HeuristicDefinition,
} from "@/lib/decision-explanations";
import {
  formatStructuralHeadingDisplay,
  nearestProvisionHeading,
} from "@/lib/structural-headings";

export type ExplanationAvailability =
  | "available"
  | "missing_artifact"
  | "partial"
  | "empty";

export type ExplanationEvidenceItem = {
  kind: string;
  label: string;
  value: string;
  decisionId: string;
};

export type ExplanationDecisionRef = {
  decisionId: string;
  ruleId: string;
  ruleVersion: string;
  outcome: string;
  method: string;
  methodLabel: string;
  summary: string;
  heuristicName: string | null;
  heuristicSummary: string | null;
  heuristicAvailable: boolean;
};

export type ExplanationContextGroup = {
  role: string;
  title: string;
  items: Array<{
    label: string;
    propositionId: string | null;
    decisionId: string;
    inheritedViaGroup: boolean;
  }>;
};

export type ExplanationStageView = {
  stageId: (typeof STAGE_TIMELINE_ORDER)[number];
  title: string;
  status: "present" | "unavailable" | "omitted";
  explanation: string;
  methodLabels: string[];
  decisions: ExplanationDecisionRef[];
  evidence: ExplanationEvidenceItem[];
  diagnostics: string[];
  /** Expandable relationship/composition detail blocks */
  detailBlocks: Array<{ title: string; lines: string[]; decisionIds: string[] }>;
};

export type LegislativeHeadingProjection = {
  display: string;
  kind: string | null;
  ownerLocator: string | null;
  changeIds: string[];
  commentaryRefs: string[];
  note: string;
};

export type StatementExplanationViewModel = {
  availability: ExplanationAvailability;
  legacyMessage: string | null;
  overview: string;
  stages: ExplanationStageView[];
  keyLegalLinks: string[];
  evidence: ExplanationEvidenceItem[];
  diagnostics: string[];
  /** Source-captured legislative heading (structural context; not a proposition). */
  legislativeHeading: LegislativeHeadingProjection | null;
  technicalDetails: {
    parseDiagnostics: string[];
    decisions: Array<{
      decisionId: string;
      ruleId: string;
      ruleVersion: string;
      heuristicName: string | null;
      method: string;
      subjectKind: string;
      subjectId: string;
      traceReferences: Array<{ kind: string; id: string | null; label: string | null }>;
      modelAlias: string | null;
      promptVersion: string | null;
      codeReferences: string[];
      diagnostics: string[];
    }>;
  };
  relatedDecisionIds: string[];
  contextGroups: ExplanationContextGroup[];
};

export type LegalRuleGroupRow = {
  id: string;
  member_proposition_ids?: string[];
  canonical_locator?: string | null;
  [key: string]: unknown;
};

export type LegalRuleRelationshipRow = {
  id: string;
  relationship_type?: string | null;
  source_proposition_id?: string | null;
  target_id?: string | null;
  target_kind?: string | null;
  [key: string]: unknown;
};

function trim(value: unknown): string {
  return String(value ?? "").trim();
}

function uniqueStable<T>(items: T[], keyFn: (item: T) => string): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of items) {
    const key = keyFn(item);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    out.push(item);
  }
  return out;
}

function humanizeLocator(locator: string): string {
  const text = trim(locator);
  if (!text) {
    return "unknown locator";
  }
  const article = text.match(/article:([^:]+)/i)?.[1];
  const paragraph = text.match(/paragraph:([^:]+)/i)?.[1];
  const sub = text.match(/subparagraph:([^:]+)/i)?.[1];
  const point = text.match(/point:([^:]+)/i)?.[1];
  const sentence = text.match(/sentence:([^:]+)/i)?.[1];
  const parts: string[] = [];
  if (article) {
    parts.push(`Article ${article}`);
  }
  if (paragraph) {
    parts.push(`paragraph ${paragraph}`);
  }
  if (sub) {
    parts.push(`(${sub})`);
  }
  if (point) {
    parts.push(`(${point})`);
  }
  if (sentence && !sub && !point) {
    parts.push(`sentence ${sentence}`);
  }
  return parts.length > 0 ? parts.join(" ") : text;
}

function pathLabel(path: string): string {
  return path.replace(/-/g, "-");
}

function evidenceOf(decision: DecisionExplanation, kind: string): string[] {
  return decision.evidence
    .filter((row) => row.kind === kind)
    .map((row) => trim(row.value) || trim(row.id))
    .filter(Boolean);
}

function firstEvidence(decision: DecisionExplanation, kind: string): string | null {
  return evidenceOf(decision, kind)[0] ?? null;
}

function metaStr(decision: DecisionExplanation, key: string): string | null {
  const value = decision.metadata?.[key];
  const text = trim(value);
  return text || null;
}

function metaBool(decision: DecisionExplanation, key: string): boolean {
  return decision.metadata?.[key] === true;
}

function metaList(decision: DecisionExplanation, key: string): string[] {
  const value = decision.metadata?.[key];
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => trim(item)).filter(Boolean);
}

function fragmentLocator(
  fragmentById: Map<string, SourceFragmentRow>,
  fragmentId: string | null | undefined,
): string | null {
  if (!fragmentId) {
    return null;
  }
  const row = fragmentById.get(fragmentId);
  return trim(row?.locator) || null;
}

function paragraphLocator(locator: string): string | null {
  const match = locator.match(/^(article:[^:]+:paragraph:[^:]+)/i);
  return match?.[1] ?? null;
}

function articleLocator(locator: string): string | null {
  const match = locator.match(/^(article:[^:]+)/i);
  return match?.[1] ?? null;
}

function propLabel(
  propositionById: Map<string, PropositionRow>,
  propositionId: string,
): string {
  const prop = propositionById.get(propositionId);
  const locator = trim(prop?.fragment_locator);
  if (locator) {
    return humanizeLocator(locator);
  }
  const label = trim(prop?.label ?? prop?.short_name);
  return label || propositionId;
}

function toDecisionRef(
  decision: DecisionExplanation,
  heuristics: Map<string, HeuristicDefinition>,
): ExplanationDecisionRef {
  const heuristic = heuristics.get(decision.rule_id) ?? null;
  return {
    decisionId: decision.id,
    ruleId: decision.rule_id,
    ruleVersion: decision.rule_version,
    outcome: decision.outcome,
    method: String(decision.method),
    methodLabel: methodLabel(String(decision.method)),
    summary: decision.summary,
    heuristicName: heuristic?.name ?? null,
    heuristicSummary: heuristic?.plain_english_summary ?? null,
    heuristicAvailable: heuristic != null,
  };
}

function groundedEvidence(
  decisions: DecisionExplanation[],
  kinds: string[],
): ExplanationEvidenceItem[] {
  const allow = new Set(kinds);
  const items: ExplanationEvidenceItem[] = [];
  for (const decision of decisions) {
    for (const row of decision.evidence) {
      if (!allow.has(row.kind)) {
        continue;
      }
      const value = trim(row.value) || trim(row.id);
      if (!value) {
        continue;
      }
      // Never surface absolute filesystem paths.
      if (/^file:\/\//i.test(value) || /^\/(?:Users|home|var|tmp)\//.test(value)) {
        continue;
      }
      items.push({
        kind: row.kind,
        label: trim(row.label) || row.kind,
        value,
        decisionId: decision.id,
      });
    }
  }
  return uniqueStable(items, (item) => `${item.decisionId}:${item.kind}:${item.value}`);
}

function collectRelatedSelection(params: {
  index: DecisionExplanationIndex;
  proposition: PropositionRow;
  fragmentById: Map<string, SourceFragmentRow>;
}): DecisionExplanation[] {
  const fragmentId = trim(params.proposition.source_fragment_id);
  const locator =
    fragmentLocator(params.fragmentById, fragmentId) ||
    trim(params.proposition.fragment_locator);
  if (!locator) {
    return [];
  }
  const paragraph = paragraphLocator(locator) ?? locator;
  const article = articleLocator(locator);
  const related: DecisionExplanation[] = [];

  const required =
    params.index.bySourceLocator.get(paragraph)?.filter(
      (d) =>
        d.stage === "selection" &&
        d.rule_id === "selection.required_locator" &&
        d.outcome === "selected_for_extraction",
    ) ?? [];
  related.push(...required);

  if (article) {
    const parentSkip =
      params.index.bySourceLocator.get(article)?.filter(
        (d) =>
          d.stage === "selection" &&
          d.rule_id === "selection.prefer_required_children" &&
          d.outcome === "not_selected_for_extraction",
      ) ?? [];
    related.push(...parentSkip);
  }

  // Focus-selected descendants skipped because this paragraph covered them.
  for (const decision of params.index.byStage.get("selection") ?? []) {
    if (decision.rule_id !== "selection.prefer_required_ancestor") {
      continue;
    }
    const labelledPreferred = decision.evidence.find(
      (row) =>
        row.kind === "source_locator" && trim(row.label) === "Preferred ancestor locator",
    );
    const ancestor = trim(labelledPreferred?.value);
    if (ancestor === paragraph || ancestor === locator) {
      related.push(decision);
    }
  }

  // Also include focus-term selection for the same fragment when present.
  if (fragmentId) {
    for (const decision of params.index.bySourceFragmentId.get(fragmentId) ?? []) {
      if (decision.stage === "selection" && decision.rule_id === "selection.focus_term_match") {
        related.push(decision);
      }
    }
  }

  return uniqueStable(related, (d) => d.id);
}

function collectComposition(params: {
  index: DecisionExplanationIndex;
  propositionId: string;
}): DecisionExplanation[] {
  return (params.index.byPropositionId.get(params.propositionId) ?? []).filter(
    (d) =>
      d.stage === "extraction" &&
      d.subject_kind === "proposition" &&
      d.subject_id === params.propositionId &&
      d.rule_id.startsWith("structured_list."),
  );
}

function collectClassification(params: {
  index: DecisionExplanationIndex;
  propositionId: string;
}): DecisionExplanation[] {
  return (params.index.byPropositionId.get(params.propositionId) ?? []).filter(
    (d) =>
      d.stage === "classification" &&
      d.subject_kind === "proposition" &&
      d.subject_id === params.propositionId,
  );
}

function collectGrouping(params: {
  index: DecisionExplanationIndex;
  propositionId: string;
  groups: LegalRuleGroupRow[];
}): DecisionExplanation[] {
  const groupIds = params.groups
    .filter((group) => (group.member_proposition_ids ?? []).includes(params.propositionId))
    .map((group) => group.id);
  const out: DecisionExplanation[] = [];
  for (const groupId of groupIds) {
    for (const decision of params.index.byLegalRuleGroupId.get(groupId) ?? []) {
      if (decision.stage === "grouping") {
        out.push(decision);
      }
    }
  }
  // Fallback via proposition membership index.
  for (const decision of params.index.byPropositionId.get(params.propositionId) ?? []) {
    if (
      decision.stage === "grouping" &&
      metaList(decision, "member_proposition_ids").includes(params.propositionId)
    ) {
      out.push(decision);
    }
  }
  return uniqueStable(out, (d) => d.id);
}

function collectRelationships(params: {
  index: DecisionExplanationIndex;
  propositionId: string;
  groups: LegalRuleGroupRow[];
}): DecisionExplanation[] {
  const out: DecisionExplanation[] = [];

  for (const decision of params.index.byStage.get("relationship") ?? []) {
    if (decision.rule_id === "relationship.prefer_group_target") {
      continue;
    }
    const sourceProp =
      metaStr(decision, "source_proposition_id") ||
      firstEvidence(decision, "source_proposition_id");
    if (sourceProp === params.propositionId) {
      out.push(decision);
    }
  }

  const relationshipIds = new Set(out.map((d) => d.subject_id));
  for (const decision of params.index.byStage.get("relationship") ?? []) {
    if (decision.rule_id !== "relationship.prefer_group_target") {
      continue;
    }
    const relatedRel =
      decision.subject_id ||
      firstEvidence(decision, "relationship_id") ||
      metaStr(decision, "legal_rule_relationship_id");
    if (relatedRel && relationshipIds.has(relatedRel)) {
      out.push(decision);
    }
  }

  return uniqueStable(out, (d) => d.id);
}

function collectEffectiveLaw(params: {
  index: DecisionExplanationIndex;
  statementId: string;
  propositionId: string;
}): DecisionExplanation[] {
  const byStatement = params.index.byEffectiveLawStatementId.get(params.statementId) ?? [];
  return uniqueStable(
    byStatement.filter((d) => {
      const receiving =
        metaStr(d, "receiving_proposition_id") ||
        firstEvidence(d, "receiving_proposition_id");
      // Statement-bound decisions for this statement; prefer receiving prop match when present.
      if (receiving && receiving !== params.propositionId) {
        return false;
      }
      return d.stage === "effective_law";
    }),
    (d) => d.id,
  );
}

function collectProvenance(params: {
  index: DecisionExplanationIndex;
  proposition: PropositionRow;
}): DecisionExplanation[] {
  const snapshotId = trim(params.proposition.source_snapshot_id);
  if (!snapshotId) {
    return [];
  }
  const provenance = (params.index.byStage.get("provenance") ?? []).filter(
    (d) =>
      d.subject_id === snapshotId ||
      metaStr(d, "source_snapshot_id") === snapshotId ||
      firstEvidence(d, "source_snapshot_id") === snapshotId,
  );
  // Outstanding status is a source_effect-stage rule but belongs in the version panel.
  const outstanding = (params.index.byStage.get("source_effect") ?? []).filter(
    (d) =>
      d.rule_id === "source_effect.classify_outstanding_status" &&
      (d.subject_id === snapshotId ||
        metaStr(d, "source_snapshot_id") === snapshotId ||
        firstEvidence(d, "source_snapshot_id") === snapshotId),
  );
  return uniqueStable([...provenance, ...outstanding], (d) => d.id);
}

function collectSourceEffect(params: {
  index: DecisionExplanationIndex;
  statementId: string;
}): DecisionExplanation[] {
  const byStatement = params.index.byEffectiveLawStatementId.get(params.statementId) ?? [];
  const relevance = byStatement.filter(
    (d) =>
      d.stage === "source_effect" &&
      (d.rule_id === "source_effect.link_exact_fragment" ||
        d.rule_id === "source_effect.inherit_from_structural_ancestor" ||
        d.rule_id === "source_effect.exclude_unrelated_fragment"),
  );
  const effectIds = new Set(
    relevance
      .map((d) => metaStr(d, "effect_id") || firstEvidence(d, "effect_id"))
      .filter((id): id is string => Boolean(id)),
  );
  const consumption = (params.index.byStage.get("source_effect") ?? []).filter(
    (d) =>
      d.rule_id === "source_effect.assess_independent_consumption" &&
      effectIds.has(d.subject_id),
  );
  // Prefer positive relevance + consumption; keep exclusions but they stay concise in stage text.
  return uniqueStable([...relevance, ...consumption], (d) => d.id);
}

function buildOverview(params: {
  proposition: PropositionRow;
  classification: DecisionExplanation | null;
  composition: DecisionExplanation | null;
  grouping: DecisionExplanation[];
  relationships: DecisionExplanation[];
  effectiveLaw: DecisionExplanation[];
  fragmentLocator: string | null;
}): string {
  const effect =
    metaStr(params.classification ?? ({} as DecisionExplanation), "legal_effect_type") ||
    trim(params.proposition.legal_effect_type) ||
    "unknown";
  const locator = params.fragmentLocator
    ? humanizeLocator(params.fragmentLocator)
    : "its source provision";
  const path = params.composition
    ? metaStr(params.composition, "structured_list_path")
    : null;

  const sentences: string[] = [];

  if (path) {
    const parts = path.split("-");
    const stem = parts[0] ? `paragraph ${parts[0]}` : "its governing stem";
    const branch = parts[1] ? `branch (${parts[1]})` : null;
    const leaf = parts[2] ? `terminal point (${parts[2]})` : null;
    const composed = [stem, branch, leaf].filter(Boolean).join(", ");
    sentences.push(
      `Law Proposition Extractor formed this ${effect === "derogation" ? "derogation" : "rule"} from the ${composed} (path ${pathLabel(path)}).`,
    );
  } else {
    sentences.push(
      `Law Proposition Extractor extracted this rule from ${locator}, which the case explicitly required.`,
    );
  }

  if (effect === "prohibition") {
    sentences.push("The proposition was classified as a prohibition.");
  } else if (effect === "derogation") {
    sentences.push("It was classified as a derogation.");
  } else if (effect === "obligation") {
    sentences.push("It was classified as an obligation.");
  } else if (effect && effect !== "unknown") {
    sentences.push(`It was classified as a ${effect.replace(/_/g, " ")}.`);
  }

  const group = params.grouping[0] ?? null;
  if (group) {
    const members = metaList(group, "member_proposition_ids");
    const canonical = metaStr(group, "canonical_locator");
    if (canonical && members.length > 1) {
      sentences.push(
        `It belongs to a ${members.length}-rule group representing ${humanizeLocator(canonical)}.`,
      );
    }
  }

  const exceptionRel = params.relationships.find(
    (d) =>
      d.rule_id === "relationship.infer_exception_to" ||
      metaStr(d, "relationship_type") === "exception_to",
  );
  if (exceptionRel && effect === "derogation") {
    const target = metaStr(exceptionRel, "canonical_target_locator");
    if (target) {
      sentences.push(
        `It was linked as an exception to the rules in ${humanizeLocator(target)}.`,
      );
    }
  }

  const triggerRel = params.relationships.find(
    (d) =>
      d.rule_id === "relationship.infer_triggered_by" ||
      metaStr(d, "relationship_type") === "triggered_by",
  );
  if (triggerRel) {
    const target = metaStr(triggerRel, "canonical_target_locator");
    const triggers = params.effectiveLaw.filter(
      (d) => d.rule_id === "effective_law.attach_trigger_condition",
    );
    if (target) {
      sentences.push(
        `Its reference to ${humanizeLocator(target)} was interpreted as a trigger` +
          (triggers.length > 0
            ? `, so ${triggers.length} trigger condition${triggers.length === 1 ? "" : "s"} are shown.`
            : "."),
      );
    }
  }

  const exceptions = params.effectiveLaw.filter(
    (d) => d.rule_id === "effective_law.attach_applicable_exception",
  );
  if (exceptions.length > 0 && !path) {
    sentences.push(
      `${exceptions.length} applicable exception${exceptions.length === 1 ? "" : "s"} ${exceptions.length === 1 ? "is" : "are"} attached as typed context.`,
    );
  }

  return sentences.join(" ");
}

function stageExplanation(
  stageId: (typeof STAGE_TIMELINE_ORDER)[number],
  decisions: DecisionExplanation[],
  propositionById: Map<string, PropositionRow>,
): { explanation: string; detailBlocks: ExplanationStageView["detailBlocks"] } {
  const detailBlocks: ExplanationStageView["detailBlocks"] = [];
  if (decisions.length === 0) {
    return { explanation: "No decision recorded for this stage.", detailBlocks };
  }

  if (stageId === "selection") {
    const lines = decisions.map((d) => {
      const loc = firstEvidence(d, "source_locator");
      if (d.rule_id === "selection.required_locator") {
        return `${loc ? humanizeLocator(loc) : "A fragment"} was explicitly required by the run configuration.`;
      }
      if (d.rule_id === "selection.prefer_required_children") {
        return `${loc ? humanizeLocator(loc) : "A wider parent"} was not separately extracted because selected children covered it.`;
      }
      if (d.rule_id === "selection.prefer_required_ancestor") {
        const terms = evidenceOf(d, "matched_focus_term");
        const preferred = d.evidence.find(
          (row) => trim(row.label) === "Preferred ancestor locator",
        );
        return (
          `${loc ? humanizeLocator(loc) : "A focus-selected descendant"} was skipped because required ancestor ` +
          `${preferred ? humanizeLocator(trim(preferred.value)) : "coverage"} already covered its terminals` +
          (terms.length ? ` (focus terms: ${terms.join(", ")})` : "") +
          "."
        );
      }
      return d.summary;
    });
    return { explanation: lines.join(" "), detailBlocks };
  }

  if (stageId === "extraction") {
    const d = decisions[0]!;
    const path = metaStr(d, "structured_list_path");
    const origin = metaStr(d, "candidate_origin");
    const method = metaStr(d, "structural_decision_method") || String(d.method);
    const lines = [
      path ? `Structured-list path ${pathLabel(path)}.` : null,
      origin === "llm"
        ? "Frontier model proposed the extraction content."
        : origin
          ? `Candidate origin: ${origin}.`
          : null,
      method === "deterministic" || d.method === "deterministic"
        ? "Deterministic structured-list logic composed the stem, branch and leaf."
        : `Composition method: ${methodLabel(method)}.`,
    ].filter(Boolean) as string[];
    return { explanation: lines.join(" "), detailBlocks };
  }

  if (stageId === "classification") {
    const d = decisions[0]!;
    const effect = metaStr(d, "legal_effect_type") || d.outcome.replace(/^classified_as_/, "");
    const basis = metaStr(d, "winning_basis");
    const cue = firstEvidence(d, "matched_cue") || firstEvidence(d, "cue_text");
    return {
      explanation:
        `Final legal effect: ${effect.replace(/_/g, " ")}` +
        (basis ? `; winning basis: ${basis.replace(/_/g, " ")}` : "") +
        (cue ? `; cue: “${cue}”` : "") +
        `. Method: ${methodLabel(String(d.method))}.`,
      detailBlocks,
    };
  }

  if (stageId === "grouping") {
    const d = decisions[0]!;
    const members = metaList(d, "member_proposition_ids");
    const canonical = metaStr(d, "canonical_locator");
    return {
      explanation:
        `These propositions were grouped because they came from the same reliable source paragraph` +
        (canonical ? ` (${humanizeLocator(canonical)})` : "") +
        `. Grouping is structural and does not prove the propositions are legally identical.` +
        (members.length ? ` Members: ${members.map((id) => propLabel(propositionById, id)).join("; ")}.` : ""),
      detailBlocks,
    };
  }

  if (stageId === "relationship") {
    const infer = decisions.filter((d) => d.decision_type === "infer" || d.rule_id.includes("infer_"));
    const targets = decisions.filter((d) => d.rule_id === "relationship.prefer_group_target");
    const lines: string[] = [];
    for (const d of infer) {
      const relType = metaStr(d, "relationship_type") || "relationship";
      const cue = firstEvidence(d, "cue_text");
      const canonical = metaStr(d, "canonical_target_locator");
      const ordinary = evidenceOf(d, "unselected_ordinary_reference");
      lines.push(
        `${relType.replace(/_/g, " ")} inferred` +
          (cue ? ` from cue “${cue}”` : "") +
          (canonical ? `; canonical target ${humanizeLocator(canonical)}` : "") +
          ".",
      );
      if (ordinary.length > 0) {
        lines.push(
          `Ordinary reference${ordinary.length === 1 ? "" : "s"} retained (not typed targets): ${ordinary.join(", ")}.`,
        );
      }
      const target = targets.find((t) => {
        const relId = firstEvidence(t, "relationship_id");
        return !relId || relId === d.subject_id;
      });
      if (target) {
        const members = metaList(target, "member_proposition_ids");
        const groupLocator = metaStr(target, "canonical_target_locator");
        detailBlocks.push({
          title:
            relType === "exception_to"
              ? "Exception relationship inferred"
              : relType === "triggered_by"
                ? "Trigger relationship inferred"
                : "Relationship inferred",
          lines: [
            `Targeted ${groupLocator ? humanizeLocator(groupLocator) : "rule"} group`,
            members.length
              ? `Members: ${members.map((id) => propLabel(propositionById, id)).join("; ")}`
              : "Members unavailable",
            `Relationship id retained under Technical details`,
          ],
          decisionIds: [d.id, target.id],
        });
      }
    }
    if (lines.length === 0) {
      lines.push(decisions.map((d) => d.summary).join(" "));
    }
    return { explanation: lines.join(" "), detailBlocks };
  }

  if (stageId === "provenance") {
    const classify = decisions.find((d) => d.rule_id === "provenance.classify_manifestation");
    const asOf = decisions.find((d) => d.rule_id === "provenance.preserve_as_of_unknown");
    const outstanding = decisions.find(
      (d) => d.rule_id === "source_effect.classify_outstanding_status",
    );
    const lines: string[] = [];
    if (classify) {
      const type =
        metaStr(classify, "manifestation_type") ||
        classify.outcome.replace(/^classified_as_/, "");
      const basis =
        metaStr(classify, "manifestation_basis") ||
        firstEvidence(classify, "winning_evidence_basis") ||
        "unavailable";
      lines.push(
        `Consumed snapshot classified as ${type.replace(/_/g, " ")} (basis: ${basis.replace(/_/g, " ")}).`,
      );
      lines.push(
        "This records how the authority labelled the text — not that Law Proposition Extractor applied all amendments.",
      );
    }
    if (asOf) {
      lines.push(
        "No legal as-of date was established; retrieval and source revision dates are shown separately.",
      );
    }
    if (outstanding) {
      const status =
        metaStr(outstanding, "outstanding_effects_status") || outstanding.outcome;
      if (status === "source_reports_present") {
        lines.push("The consumed source reports outstanding/unapplied effects.");
      } else if (status === "source_reports_none") {
        lines.push("The consumed source explicitly reports no outstanding effects.");
      } else {
        lines.push("Outstanding-effects status was not established from source metadata (unknown, not none).");
      }
    }
    lines.push("See the Source version panel for full manifestation evidence.");
    return { explanation: lines.join(" "), detailBlocks };
  }

  if (stageId === "source_effect") {
    const exact = decisions.filter((d) => d.rule_id === "source_effect.link_exact_fragment");
    const inherited = decisions.filter(
      (d) => d.rule_id === "source_effect.inherit_from_structural_ancestor",
    );
    const excluded = decisions.filter(
      (d) => d.rule_id === "source_effect.exclude_unrelated_fragment",
    );
    const consumption = decisions.filter(
      (d) => d.rule_id === "source_effect.assess_independent_consumption",
    );
    const lines: string[] = [];
    for (const d of exact) {
      const label = metaStr(d, "annotation_label") || firstEvidence(d, "annotation_label") || "annotation";
      const loc = firstEvidence(d, "linked_locator");
      lines.push(
        `${label}: exact fragment link` +
          (loc ? ` to ${humanizeLocator(loc)}` : "") +
          ".",
      );
      detailBlocks.push({
        title: `${label} (exact)`,
        lines: [
          d.summary,
          "Source annotation is not proof of independent application or verification.",
        ],
        decisionIds: [d.id],
      });
    }
    for (const d of inherited) {
      const label = metaStr(d, "annotation_label") || firstEvidence(d, "annotation_label") || "annotation";
      const ancestor =
        metaStr(d, "ancestor_locator") || firstEvidence(d, "ancestor_locator");
      lines.push(
        `${label}: inherited from structural ancestor` +
          (ancestor ? ` ${humanizeLocator(ancestor)}` : "") +
          ".",
      );
      detailBlocks.push({
        title: `${label} (inherited)`,
        lines: [
          d.summary,
          "Source annotation is not proof of independent application or verification.",
        ],
        decisionIds: [d.id],
      });
    }
    for (const d of excluded.slice(0, 2)) {
      lines.push(d.summary);
    }
    for (const d of consumption) {
      const status = metaStr(d, "independent_consumption_status") || d.outcome;
      lines.push(`Independent consumption: ${status.replace(/_/g, " ")}.`);
    }
    if (lines.length === 0) {
      lines.push("No source-change annotations were recorded as relevant to this statement.");
    } else {
      lines.push(
        "Detailed effect cards remain in the Source change annotations panel — not duplicated here.",
      );
    }
    return { explanation: lines.join(" "), detailBlocks };
  }

  // effective_law
  const attachments = decisions.filter((d) => d.decision_type === "attach");
  const suppressions = decisions.filter(
    (d) => d.rule_id === "effective_law.prefer_typed_context_over_generic_locator",
  );
  const byKind = new Map<string, DecisionExplanation[]>();
  for (const d of attachments) {
    const kind = metaStr(d, "context_kind") || "context";
    const list = byKind.get(kind) ?? [];
    list.push(d);
    byKind.set(kind, list);
  }
  const lines: string[] = [];
  for (const [kind, rows] of byKind) {
    const inherited = rows.filter((d) => metaBool(d, "inherited_via_group")).length;
    const title =
      kind === "applicable_exception"
        ? "Applicable exceptions"
        : kind === "exception_target"
          ? "Exception targets"
          : kind === "trigger_condition"
            ? "Trigger conditions"
            : kind.replace(/_/g, " ");
    lines.push(
      `${title} (${rows.length})` +
        (inherited > 0 ? `; ${inherited} inherited through a rule group` : "") +
        ".",
    );
    detailBlocks.push({
      title: `${title} (${rows.length})`,
      lines: rows.map((d) => {
        const ctxProp = metaStr(d, "context_proposition_id");
        return ctxProp ? propLabel(propositionById, ctxProp) : d.outcome;
      }),
      decisionIds: rows.map((d) => d.id),
    });
  }
  for (const d of suppressions) {
    const locator = metaStr(d, "generic_locator") || firstEvidence(d, "generic_locator");
    lines.push(
      `Generic context “${locator ?? "locator"}” was suppressed as duplicative of typed context.` +
        ` Unrelated ordinary references were not removed.`,
    );
  }
  const direction = attachments
    .map((d) => metaStr(d, "expansion_direction"))
    .find((value) => value);
  if (direction) {
    lines.push(`Expansion direction: ${direction.replace(/_/g, " ")}.`);
  }
  return { explanation: lines.join(" "), detailBlocks };
}

function buildContextGroups(
  effectiveLaw: DecisionExplanation[],
  propositionById: Map<string, PropositionRow>,
): ExplanationContextGroup[] {
  const byKind = new Map<string, DecisionExplanation[]>();
  for (const d of effectiveLaw) {
    if (d.decision_type !== "attach") {
      continue;
    }
    const kind = metaStr(d, "context_kind") || "context";
    const list = byKind.get(kind) ?? [];
    list.push(d);
    byKind.set(kind, list);
  }
  const groups: ExplanationContextGroup[] = [];
  for (const [kind, rows] of byKind) {
    const title =
      kind === "applicable_exception"
        ? `Applicable exceptions (${rows.length})`
        : kind === "exception_target"
          ? `Exception targets (${rows.length})`
          : kind === "trigger_condition"
            ? `Trigger conditions (${rows.length})`
            : `${kind.replace(/_/g, " ")} (${rows.length})`;
    groups.push({
      role: kind,
      title,
      items: rows.map((d) => {
        const propId = metaStr(d, "context_proposition_id");
        return {
          label: propId ? propLabel(propositionById, propId) : d.outcome,
          propositionId: propId,
          decisionId: d.id,
          inheritedViaGroup: metaBool(d, "inherited_via_group"),
        };
      }),
    });
  }
  return groups;
}

function buildKeyLegalLinks(params: {
  relationships: DecisionExplanation[];
  grouping: DecisionExplanation[];
  effectiveLaw: DecisionExplanation[];
  propositionById: Map<string, PropositionRow>;
}): string[] {
  const links: string[] = [];
  for (const d of params.relationships) {
    if (d.rule_id.includes("infer_")) {
      const rel = metaStr(d, "relationship_type");
      const target = metaStr(d, "canonical_target_locator");
      if (rel && target) {
        links.push(`${rel.replace(/_/g, " ")} → ${humanizeLocator(target)}`);
      }
      for (const ordinary of evidenceOf(d, "unselected_ordinary_reference")) {
        links.push(`Ordinary reference (not typed target): ${ordinary}`);
      }
    }
    if (d.rule_id === "relationship.prefer_group_target") {
      const members = metaList(d, "member_proposition_ids");
      if (members.length) {
        links.push(
          `Target group members: ${members.map((id) => propLabel(params.propositionById, id)).join("; ")}`,
        );
      }
    }
  }
  for (const d of params.grouping) {
    const members = metaList(d, "member_proposition_ids");
    const canonical = metaStr(d, "canonical_locator");
    if (canonical) {
      links.push(
        `Rule group (${humanizeLocator(canonical)}): ${members.map((id) => propLabel(params.propositionById, id)).join("; ")}`,
      );
    }
  }
  const exceptions = params.effectiveLaw.filter(
    (d) => d.rule_id === "effective_law.attach_applicable_exception",
  );
  if (exceptions.length) {
    links.push(
      `Applicable exceptions: ${exceptions
        .map((d) => {
          const id = metaStr(d, "context_proposition_id");
          return id ? propLabel(params.propositionById, id) : d.id;
        })
        .join("; ")}`,
    );
  }
  return uniqueStable(links, (line) => line);
}

export function buildStatementExplanationViewModel(params: {
  statement: LawStatementRow;
  proposition: PropositionRow | null;
  propositionById: Map<string, PropositionRow>;
  fragmentById: Map<string, SourceFragmentRow>;
  legalRuleGroups?: LegalRuleGroupRow[];
  legalRuleRelationships?: LegalRuleRelationshipRow[];
  decisionIndex: DecisionExplanationIndex;
  heuristics: Map<string, HeuristicDefinition>;
}): StatementExplanationViewModel {
  const emptyTechnical = {
    parseDiagnostics: [...params.decisionIndex.parseDiagnostics],
    decisions: [] as StatementExplanationViewModel["technicalDetails"]["decisions"],
  };

  if (!params.decisionIndex.artifactPresent) {
    return {
      availability: "missing_artifact",
      legacyMessage:
        "Detailed decision explanations were not recorded for this run. Source evidence and legal context remain available.",
      overview: "",
      stages: [],
      keyLegalLinks: [],
      evidence: [],
      diagnostics: [],
      legislativeHeading: null,
      technicalDetails: emptyTechnical,
      relatedDecisionIds: [],
      contextGroups: [],
    };
  }

  if (!params.proposition) {
    return {
      availability: "partial",
      legacyMessage: null,
      overview: "No source proposition is linked to this statement, so decision explanations cannot be projected.",
      stages: [],
      keyLegalLinks: [],
      evidence: [],
      diagnostics: ["missing_source_proposition"],
      legislativeHeading: null,
      technicalDetails: emptyTechnical,
      relatedDecisionIds: [],
      contextGroups: [],
    };
  }

  const propositionId = params.proposition.id;
  const groups = params.legalRuleGroups ?? [];
  const selection = collectRelatedSelection({
    index: params.decisionIndex,
    proposition: params.proposition,
    fragmentById: params.fragmentById,
  });
  const composition = collectComposition({
    index: params.decisionIndex,
    propositionId,
  });
  const classification = collectClassification({
    index: params.decisionIndex,
    propositionId,
  });
  const grouping = collectGrouping({
    index: params.decisionIndex,
    propositionId,
    groups,
  });
  const relationships = collectRelationships({
    index: params.decisionIndex,
    propositionId,
    groups,
  });
  const effectiveLaw = collectEffectiveLaw({
    index: params.decisionIndex,
    statementId: params.statement.id,
    propositionId,
  });
  const provenance = collectProvenance({
    index: params.decisionIndex,
    proposition: params.proposition,
  });
  const sourceEffect = collectSourceEffect({
    index: params.decisionIndex,
    statementId: params.statement.id,
  });

  const relatedByStage: Record<(typeof STAGE_TIMELINE_ORDER)[number], DecisionExplanation[]> = {
    provenance,
    selection,
    extraction: composition,
    classification,
    grouping,
    relationship: relationships,
    effective_law: effectiveLaw,
    source_effect: sourceEffect,
  };

  const stages: ExplanationStageView[] = [];
  for (const stageId of STAGE_TIMELINE_ORDER) {
    const decisions = relatedByStage[stageId];
    // Omit structured-list stage entirely for ordinary sentences (no composition).
    if (stageId === "extraction" && decisions.length === 0) {
      continue;
    }
    const status: ExplanationStageView["status"] =
      decisions.length > 0 ? "present" : "unavailable";
    const built = stageExplanation(stageId, decisions, params.propositionById);
    const methods = uniqueStable(
      decisions.map((d) => methodLabel(String(d.method))),
      (m) => m,
    );
    stages.push({
      stageId,
      title: STAGE_DISPLAY_TITLES[stageId],
      status,
      explanation:
        status === "unavailable"
          ? "No decision explanation was recorded for this stage."
          : built.explanation,
      methodLabels: methods,
      decisions: decisions.map((d) => toDecisionRef(d, params.heuristics)),
      evidence: groundedEvidence(decisions, [
        "source_locator",
        "matched_focus_term",
        "matched_cue",
        "cue_text",
        "structured_list_path",
        "canonical_target_locator",
        "canonical_locator",
        "unselected_ordinary_reference",
        "generic_locator",
        "coverage_basis",
        "original_selection_reason",
        "composition_basis",
        "group_member_proposition_id",
        "context_kind",
        "typed_context_kind",
        "fragment_locator",
        "winning_basis",
        "legal_effect_type",
        "manifestation_type",
        "winning_evidence_basis",
        "requested_as_of_date",
        "resolved_as_of_date",
        "source_revision_date",
        "retrieved_at",
        "relevance_basis",
        "ancestor_locator",
        "linked_locator",
        "independent_consumption_status",
        "outstanding_effects_status",
        "structural_boundary",
      ]),
      diagnostics: decisions.flatMap((d) => d.diagnostics),
      detailBlocks: built.detailBlocks,
    });
  }

  const allRelated = uniqueStable(
    [
      ...provenance,
      ...selection,
      ...composition,
      ...classification,
      ...grouping,
      ...relationships,
      ...effectiveLaw,
      ...sourceEffect,
    ],
    (d) => d.id,
  );

  const overview = buildOverview({
    proposition: params.proposition,
    classification: classification[0] ?? null,
    composition: composition[0] ?? null,
    grouping,
    relationships,
    effectiveLaw,
    fragmentLocator:
      fragmentLocator(params.fragmentById, params.proposition.source_fragment_id) ||
      trim(params.proposition.fragment_locator) ||
      null,
  });

  const sourceFragment =
    (params.proposition.source_fragment_id &&
      params.fragmentById.get(params.proposition.source_fragment_id)) ||
    null;
  const nearestHeading = nearestProvisionHeading(sourceFragment, params.fragmentById);
  const legislativeHeading: LegislativeHeadingProjection | null = nearestHeading
    ? {
        display: formatStructuralHeadingDisplay(
          nearestHeading.number_label,
          nearestHeading.heading_text,
        ),
        kind: nearestHeading.kind ? String(nearestHeading.kind) : null,
        ownerLocator: nearestHeading.owner_locator ?? null,
        changeIds: Array.isArray(nearestHeading.change_ids)
          ? nearestHeading.change_ids.map(String)
          : [],
        commentaryRefs: Array.isArray(nearestHeading.commentary_refs)
          ? nearestHeading.commentary_refs.map(String)
          : [],
        note:
          "This heading is source-provided structural context. It was available to extraction but was not treated as a standalone legal proposition.",
      }
    : null;

  const presentStages = stages.filter((s) => s.status === "present");
  const availability: ExplanationAvailability =
    presentStages.length === 0
      ? "empty"
      : presentStages.length < stages.filter((s) => s.stageId !== "extraction" || s.status === "present").length
        ? "partial"
        : "available";

  return {
    availability,
    legacyMessage: null,
    overview,
    stages,
    keyLegalLinks: buildKeyLegalLinks({
      relationships,
      grouping,
      effectiveLaw,
      propositionById: params.propositionById,
    }),
    evidence: groundedEvidence(allRelated, [
      "source_locator",
      "matched_focus_term",
      "matched_cue",
      "cue_text",
      "structured_list_path",
      "canonical_target_locator",
      "unselected_ordinary_reference",
      "generic_locator",
    ]),
    diagnostics: [
      ...params.decisionIndex.parseDiagnostics,
      ...allRelated.flatMap((d) => d.diagnostics),
    ],
    legislativeHeading,
    technicalDetails: {
      parseDiagnostics: [...params.decisionIndex.parseDiagnostics],
      decisions: allRelated.map((d) => ({
        decisionId: d.id,
        ruleId: d.rule_id,
        ruleVersion: d.rule_version,
        heuristicName: params.heuristics.get(d.rule_id)?.name ?? null,
        method: String(d.method),
        subjectKind: String(d.subject_kind),
        subjectId: d.subject_id,
        traceReferences: d.trace_references.map((row) => ({
          kind: row.kind,
          id: row.id ?? null,
          label: row.label ?? null,
        })),
        modelAlias: d.model_alias ?? null,
        promptVersion: d.prompt_version ?? null,
        codeReferences: d.code_references.filter((ref) => !/^file:\/\//i.test(ref)),
        diagnostics: d.diagnostics,
      })),
    },
    relatedDecisionIds: allRelated.map((d) => d.id),
    contextGroups: buildContextGroups(effectiveLaw, params.propositionById),
  };
}
