import { displaySourceExcerpt, formatExcerptForDisplay, joinExcerptParts } from "@/lib/excerpt-display";
import {
  EXPORT_FIELD_UNAVAILABLE,
  buildStatementRecipe,
  type CompositionBuildContext,
  type SourceFragmentRow,
} from "@/lib/law-statements-composition";
import type { LawStatementRow, PropositionRow } from "@/lib/law-statements-index";
import { buildContextRequirementResolutions } from "@/lib/context-locator-resolution";
import {
  buildWorkbenchComposition,
} from "@/lib/review-workbench-views";

export type ExcerptCorruptionKind =
  | "locator_label_bleed"
  | "glued_list_marker"
  | "internal_word_space"
  | "missing_boundary_space";

export type ExcerptCorruptionFinding = {
  kind: ExcerptCorruptionKind;
  match: string;
  index: number;
};

export type ExcerptProvenanceStage =
  | "source_fragment_extraction"
  | "evidence_quote_generation"
  | "statement_recipe_source_excerpt"
  | "excerpt_assembly"
  | "display_normalisation";

export type ExcerptProvenanceStep = {
  stage: ExcerptProvenanceStage;
  field: string;
  text: string;
  findings: ExcerptCorruptionFinding[];
};

export type ExcerptProvenanceRecord = {
  id: string;
  surface: string;
  propositionId?: string;
  fragmentId?: string;
  fragmentLocator?: string;
  steps: ExcerptProvenanceStep[];
  earliestCorruptionStage: ExcerptProvenanceStage | "none";
  finalDisplayText: string;
  displayStillCorrupt: boolean;
};

const LIST_MARKER_VERBS =
  "make|calculate|record|use|ensure|produce|comply|establish|maintain|undertake|ascertain|spread|keep|notify|submit|prepare|provide|take|send|apply|determine|measure|sample|store|update|mark|show|correspond|complete|rely|plough|sow|assess";

const GLUED_LIST_MARKER_RE = new RegExp(
  `(^|[\\s—–.(]|(?<=\\)))([a-z])(${LIST_MARKER_VERBS})`,
  "gi",
);

const LOCATOR_BLEED_RE = /(?:^|\s)(\d{2,})([A-Z])/g;
const GLUED_SUBPARA_RE = /(?:^|\s)(\d+)\.([A-Z])/g;
const INTERNAL_WORD_SPACE_RE = /\b([a-z]) ([a-z]{3,})\b/gi;
const MISSING_BOUNDARY_RE = /[\d)—–]([A-Za-z])/g;

const STAGE_ORDER: ExcerptProvenanceStage[] = [
  "source_fragment_extraction",
  "evidence_quote_generation",
  "statement_recipe_source_excerpt",
  "excerpt_assembly",
  "display_normalisation",
];

export function detectExcerptCorruption(text: string): ExcerptCorruptionFinding[] {
  const trimmed = text.trim();
  if (!trimmed) {
    return [];
  }

  const findings: ExcerptCorruptionFinding[] = [];
  const seen = new Set<string>();

  const push = (kind: ExcerptCorruptionKind, match: string, index: number) => {
    const key = `${kind}:${match}:${index}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    findings.push({ kind, match, index });
  };

  for (const match of trimmed.matchAll(LOCATOR_BLEED_RE)) {
    const full = match[0].trim();
    if (full) {
      push("locator_label_bleed", full, match.index ?? 0);
    }
  }

  for (const match of trimmed.matchAll(GLUED_SUBPARA_RE)) {
    push("locator_label_bleed", match[0].trim(), match.index ?? 0);
  }

  for (const match of trimmed.matchAll(GLUED_LIST_MARKER_RE)) {
    const glued = `${match[2] ?? ""}${match[3] ?? ""}`;
    if (glued.length >= 3) {
      push("glued_list_marker", glued, match.index ?? 0);
    }
  }

  if (/\band[b-z][a-z]{3,}/i.test(trimmed)) {
    const match = trimmed.match(/\band[b-z][a-z]{3,}/i);
    if (match) {
      push("glued_list_marker", match[0], match.index ?? 0);
    }
  }

  for (const match of trimmed.matchAll(INTERNAL_WORD_SPACE_RE)) {
    const left = match[1] ?? "";
    const right = match[2] ?? "";
    const joined = `${left}${right}`.toLowerCase();
    if (joined.length >= 5 && /^(manure|holding|spread|record|assess)/.test(joined)) {
      push("internal_word_space", match[0], match.index ?? 0);
    }
  }

  for (const match of trimmed.matchAll(MISSING_BOUNDARY_RE)) {
    const boundary = match[0];
    if (
      boundary &&
      !findings.some((finding) => finding.match.includes(boundary)) &&
      !/^\d+\.\d/.test(boundary)
    ) {
      push("missing_boundary_space", boundary, match.index ?? 0);
    }
  }

  return findings.sort((left, right) => left.index - right.index);
}

export function earliestCorruptionStage(
  steps: readonly ExcerptProvenanceStep[],
): ExcerptProvenanceStage | "none" {
  for (const stage of STAGE_ORDER) {
    const step = steps.find((row) => row.stage === stage);
    if (step && step.findings.length > 0) {
      return stage;
    }
  }
  return "none";
}

function sourceExcerptPartsForProposition(
  proposition: PropositionRow | undefined,
  fragmentById: CompositionBuildContext["fragmentById"],
): string[] {
  const parts: string[] = [];
  const fragmentId = proposition?.source_fragment_id?.trim();
  if (fragmentId) {
    const fragmentText = fragmentById.get(fragmentId)?.fragment_text?.trim();
    if (fragmentText) {
      parts.push(fragmentText);
    }
  }
  if (parts.length === 0) {
    const evidenceQuote = proposition?.extraction_debug_meta?.evidence_quote?.trim();
    if (evidenceQuote) {
      parts.push(evidenceQuote);
    }
  }
  return parts;
}

function assembleExcerpt(parts: readonly string[], fallback: string): string {
  const trimmed = parts.map((part) => part.trim()).filter(Boolean);
  if (trimmed.length === 0) {
    return fallback;
  }
  if (trimmed.length === 1) {
    return trimmed[0]!;
  }
  return joinExcerptParts(trimmed);
}

function buildRecord(input: {
  id: string;
  surface: string;
  propositionId?: string;
  fragmentId?: string;
  fragmentLocator?: string;
  steps: ExcerptProvenanceStep[];
  finalDisplayText: string;
}): ExcerptProvenanceRecord {
  const displayFindings = detectExcerptCorruption(input.finalDisplayText);
  return {
    ...input,
    earliestCorruptionStage: earliestCorruptionStage(input.steps),
    displayStillCorrupt: displayFindings.length > 0,
  };
}

export function tracePropositionExcerptProvenance(input: {
  proposition: PropositionRow;
  fragment?: SourceFragmentRow;
  recipeSourceExcerpt?: string;
}): ExcerptProvenanceRecord {
  const fragmentText = input.fragment?.fragment_text?.trim() ?? "";
  const evidenceQuote = input.proposition.extraction_debug_meta?.evidence_quote?.trim() ?? "";
  const recipeExcerpt = input.recipeSourceExcerpt?.trim() ?? "";
  const assemblyParts = sourceExcerptPartsForProposition(
    input.proposition,
    new Map(input.fragment?.id ? [[input.fragment.id, input.fragment]] : []),
  );
  const assembled =
    assemblyParts.length > 0
      ? assembleExcerpt(assemblyParts, recipeExcerpt || EXPORT_FIELD_UNAVAILABLE)
      : recipeExcerpt || EXPORT_FIELD_UNAVAILABLE;
  const finalDisplayText = displaySourceExcerpt(assembled, EXPORT_FIELD_UNAVAILABLE);

  const steps: ExcerptProvenanceStep[] = [
    {
      stage: "source_fragment_extraction",
      field: "fragment_text",
      text: fragmentText,
      findings: detectExcerptCorruption(fragmentText),
    },
    {
      stage: "evidence_quote_generation",
      field: "extraction_debug_meta.evidence_quote",
      text: evidenceQuote,
      findings: detectExcerptCorruption(evidenceQuote),
    },
    {
      stage: "statement_recipe_source_excerpt",
      field: "statement_recipe.source_excerpt",
      text: recipeExcerpt,
      findings: detectExcerptCorruption(recipeExcerpt),
    },
    {
      stage: "excerpt_assembly",
      field: "assembled_excerpt",
      text: assembled,
      findings: detectExcerptCorruption(assembled),
    },
    {
      stage: "display_normalisation",
      field: "displaySourceExcerpt",
      text: finalDisplayText,
      findings: detectExcerptCorruption(finalDisplayText),
    },
  ];

  return buildRecord({
    id: `proposition:${input.proposition.id}`,
    surface: "proposition.sourceExcerpt",
    propositionId: input.proposition.id,
    fragmentId: input.fragment?.id ?? input.proposition.source_fragment_id,
    fragmentLocator: input.fragment?.locator ?? input.proposition.fragment_locator,
    steps,
    finalDisplayText,
  });
}

export function buildWorkbenchExcerptProvenance(input: {
  statement: LawStatementRow;
  context: CompositionBuildContext;
  sourceFragments?: SourceFragmentRow[];
}): ExcerptProvenanceRecord[] {
  const composition = buildWorkbenchComposition(input.statement, input.context);
  const contextResolutions = buildContextRequirementResolutions(input.statement, {
    sourceFragments: input.sourceFragments ?? Array.from(input.context.fragmentById.values()),
    propositionById: input.context.propositionById,
    fragmentById: input.context.fragmentById,
  });

  const records: ExcerptProvenanceRecord[] = [];
  const recipeByPropositionId = new Map<string, string>();
  for (const row of composition.recipe) {
    for (const propositionId of row.supporting_proposition_ids) {
      if (!recipeByPropositionId.has(propositionId)) {
        recipeByPropositionId.set(propositionId, row.source_excerpt);
      }
    }
  }

  for (const proposition of composition.propositions) {
    const propositionRow = input.context.propositionById.get(proposition.propositionId);
    if (!propositionRow) {
      continue;
    }
    const fragmentId = propositionRow.source_fragment_id?.trim();
    const fragment = fragmentId ? input.context.fragmentById.get(fragmentId) : undefined;
    records.push(
      tracePropositionExcerptProvenance({
        proposition: propositionRow,
        fragment,
        recipeSourceExcerpt: recipeByPropositionId.get(proposition.propositionId),
      }),
    );
  }

  for (const [index, fragment] of composition.lawFragments.entries()) {
    const raw = composition.recipe.find(
      (row) =>
        row.source_excerpt !== EXPORT_FIELD_UNAVAILABLE &&
        displaySourceExcerpt(row.source_excerpt, EXPORT_FIELD_UNAVAILABLE) === fragment.sourceExcerpt,
    );
    const rawText = raw?.source_excerpt ?? "";
    records.push(
      buildRecord({
        id: `law-fragment:${index}`,
        surface: "lawFragment.sourceExcerpt",
        steps: [
          {
            stage: "statement_recipe_source_excerpt",
            field: "statement_recipe.source_excerpt",
            text: rawText,
            findings: detectExcerptCorruption(rawText),
          },
          {
            stage: "display_normalisation",
            field: "displaySourceExcerpt",
            text: fragment.sourceExcerpt,
            findings: detectExcerptCorruption(fragment.sourceExcerpt),
          },
        ],
        finalDisplayText: fragment.sourceExcerpt,
      }),
    );
  }

  appendAssessmentContextRecords(records, contextResolutions, input.context.fragmentById);

  return records;
}

function traceContextFragmentProvenance(
  fragmentId: string,
  locator: string,
  fragmentById: Map<string, SourceFragmentRow>,
  surface: string,
  id: string,
): ExcerptProvenanceRecord {
  const rawText = fragmentById.get(fragmentId)?.fragment_text?.trim() ?? "";
  const finalDisplayText = displaySourceExcerpt(rawText, EXPORT_FIELD_UNAVAILABLE);
  return buildRecord({
    id,
    surface,
    fragmentId,
    fragmentLocator: locator,
    steps: [
      {
        stage: "source_fragment_extraction",
        field: "fragment_text",
        text: rawText,
        findings: detectExcerptCorruption(rawText),
      },
      {
        stage: "excerpt_assembly",
        field: "context_locator_resolution.fragment_excerpt",
        text: rawText,
        findings: detectExcerptCorruption(rawText),
      },
      {
        stage: "display_normalisation",
        field: "displaySourceExcerpt",
        text: finalDisplayText,
        findings: detectExcerptCorruption(finalDisplayText),
      },
    ],
    finalDisplayText,
  });
}

function appendAssessmentContextRecords(
  records: ExcerptProvenanceRecord[],
  contextResolutions: ReturnType<typeof buildContextRequirementResolutions>,
  fragmentById: Map<string, SourceFragmentRow>,
): void {
  for (const [contextIndex, context] of contextResolutions.entries()) {
    for (const [fragmentIndex, fragment] of context.fragments.entries()) {
      records.push(
        traceContextFragmentProvenance(
          fragment.fragmentId,
          fragment.locator,
          fragmentById,
          "assessmentContext.fragments.excerpt",
          `assessment-context:${contextIndex}:${fragmentIndex}`,
        ),
      );
    }
    for (const [childIndex, child] of (context.children ?? []).entries()) {
      for (const [fragmentIndex, fragment] of child.fragments.entries()) {
        records.push(
          traceContextFragmentProvenance(
            fragment.fragmentId,
            fragment.locator,
            fragmentById,
            "assessmentContext.children.fragments.excerpt",
            `assessment-context:${contextIndex}:child:${childIndex}:${fragmentIndex}`,
          ),
        );
      }
    }
  }
}

export function logWorkbenchExcerptProvenance(
  records: readonly ExcerptProvenanceRecord[],
  logger: Pick<Console, "group" | "groupEnd" | "log"> = console,
): void {
  for (const record of records) {
    logger.group(`${record.surface} (${record.id})`);
    logger.log("fragmentLocator:", record.fragmentLocator ?? "(none)");
    logger.log("earliestCorruptionStage:", record.earliestCorruptionStage);
    logger.log("displayStillCorrupt:", record.displayStillCorrupt);
    for (const step of record.steps) {
      logger.group(`${step.stage} :: ${step.field}`);
      logger.log("text:", step.text);
      logger.log("findings:", step.findings);
      logger.groupEnd();
    }
    logger.log("finalDisplayText:", record.finalDisplayText);
    logger.groupEnd();
  }
}

export function summarizeExcerptCorruption(
  records: readonly ExcerptProvenanceRecord[],
): {
  corruption_origin: ExcerptProvenanceStage | "none";
  affected_fields: string[];
  records_with_residual_display_corruption: number;
} {
  const origins = new Set<ExcerptProvenanceStage>();
  const fields = new Set<string>();
  let residual = 0;

  for (const record of records) {
    if (record.earliestCorruptionStage !== "none") {
      origins.add(record.earliestCorruptionStage);
      const firstCorrupt = record.steps.find((step) => step.findings.length > 0);
      if (firstCorrupt) {
        fields.add(firstCorrupt.field);
      }
    }
    if (record.displayStillCorrupt) {
      residual += 1;
    }
  }

  const corruption_origin =
    STAGE_ORDER.find((stage) => origins.has(stage)) ?? ("none" as const);

  return {
    corruption_origin,
    affected_fields: Array.from(fields).sort(),
    records_with_residual_display_corruption: residual,
  };
}

export { formatExcerptForDisplay };
