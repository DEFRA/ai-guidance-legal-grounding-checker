import { UnknownRecord, propositionSubtitleParts } from "@/components/proposition-explorer-helpers";

/** Deterministic heuristic derive of structured proposition fields (subject / rule / object / conditions) — no ML. */
export type ProvisionType =
  | "core"
  | "transitional"
  | "definition"
  | "exception"
  | "cross_reference";

/** Derived provision classification — heuristic only (keywords + temporal phrases). */
export type StructuredProposition = {
  subject: string;
  rule: string;
  object: string;
  conditions: string[];
  /** Whole core sentence kept when modal split fails (for fallback display). */
  coreRemainder: string;
  fallbackNoModal: boolean;
  provisionType: ProvisionType;
  /** Prominent labels e.g. "Valid until: 31 March 2027" — empty when none extracted. */
  temporalLabels: string[];
};

const WS = /\s+/g;

function norm(s: string): string {
  return s.trim().replace(WS, " ");
}

type RuleHit = { start: number; end: number; text: string };

/**
 * Prefer longer / more specific modality phrases before single-word modals.
 * Order determines tie-break when two patterns match at the same index (first pattern wins).
 */
const RULE_REGEXES: RegExp[] = [
  /\bdoes\s+not\s+apply\b/i,
  /\bdo\s+not\s+apply\b/i,
  /\bshall\s+not\b/i,
  /\bmust\s+not\b/i,
  /\bmay\s+not\b/i,
  /\b(?:is|are)\s+not\s+(?:allowed|authorised|authorized|permitted)\b/i,
  /\b(?:is|are)\s+(?:required|prohibited|authorised|authorized|permitted|obliged|obligated|liable)\b/i,
  /\b(?:has|have)\s+(?:no\s+)?(?:right|power)\s+to\b/i,
  /\b(?:has|have)\s+the\s+(?:right|power)\s+to\b/i,
  /\bmust\b/i,
  /\bshall\b/i,
  /\bmay\b/i,
  /\bmight\b/i,
  /\bshould\b/i,
  /\bwill\b/i,
  /\bapplies\s+to\b/i,
  /\bapplied\s+to\b/i,
  /\bdoes\s+not\s+(?:have|receive)\b/i,
];

function findEarliestRule(text: string): RuleHit | null {
  let best: RuleHit | null = null;
  for (const re of RULE_REGEXES) {
    const r = new RegExp(re.source, re.flags.includes("g") ? re.flags : `${re.flags}g`);
    r.lastIndex = 0;
    const m = r.exec(text);
    if (!m || m.index === undefined) {
      continue;
    }
    const start = m.index;
    const end = start + m[0].length;
    const hit: RuleHit = { start, end, text: text.slice(start, end) };
    if (!best || hit.start < best.start || (hit.start === best.start && hit.end > best.end)) {
      best = hit;
    }
  }
  return best;
}

/** Split trailing conditional / limiting clauses from the main operative sentence. */
function splitTailConditions(core: string): { sentence: string; conditions: string[] } {
  const t = norm(core);
  if (!t) {
    return { sentence: "", conditions: [] };
  }

  const splitters: RegExp[] = [
    /\s*,\s*subject\s+to\b/i,
    /\s*,\s*without\s+prejudice\s+to\b/i,
    /\s*,\s*where\b/i,
    /\s*,\s*if\b/i,
    /\s*,\s*unless\b/i,
    /\s*,\s*provided\s+that\b/i,
    /\s*,\s*in\s+so\s+far\s+as\b/i,
    /\s*,\s*to\s+the\s+extent\s+that\b/i,
    /\s*;\s*if\b/i,
    /\s*;\s*unless\b/i,
    /\s*;\s*where\b/i,
  ];

  let cut = -1;
  for (const re of splitters) {
    const m = re.exec(t);
    if (m && m.index >= 18) {
      if (cut === -1 || m.index < cut) {
        cut = m.index;
      }
    }
  }

  if (cut === -1) {
    return { sentence: t, conditions: [] };
  }

  const sentence = t.slice(0, cut).trim();
  let tail = t.slice(cut).replace(/^\s*,\s*/, "").trim();
  if (tail.startsWith(";")) {
    tail = tail.replace(/^\s*;\s*/, "").trim();
  }

  /** Split stacked sub-clauses conservatively */
  const parts = tail.split(/(?=,\s*(?:where|if|unless|provided\s+that)\b)/i);
  const conditions = parts.map((p) => p.trim()).filter(Boolean);
  return { sentence, conditions };
}

const MONTH_NAMES =
  /\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b/i;

/** Loose ISO or EU-style date fragments for heuristic "from/until/before" anchors. */
const DATE_TAIL =
  /\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}|\d{4}-\d{2}-\d{2}/i;

/** "from" only when tied to a calendar-looking anchor (avoids "derived from Directive …"). */
const FROM_DATE_HEAD =
  /\bfrom\s+(?:\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}|\d{4}-\d{2}-\d{2})\b/i;

/** Recognises trailing clauses that belong in temporal display, not generic Conditions. */
function looksTemporalClause(s: string): boolean {
  const x = norm(s);
  if (!x) {
    return false;
  }
  if (/\btransitional\b/i.test(x)) {
    return true;
  }
  if (/^(?:until|from|before|during)\b/i.test(x)) {
    return true;
  }
  // clause dominated by a temporal phrase (comma-separated tail often repeats "until …")
  if (/\buntil\s+/i.test(x) && DATE_TAIL.test(x)) {
    return true;
  }
  if (/\bfrom\s+/i.test(x) && DATE_TAIL.test(x)) {
    return true;
  }
  if (/\bbefore\s+/i.test(x) && DATE_TAIL.test(x)) {
    return true;
  }
  if (/\bduring\s+/i.test(x)) {
    return true;
  }
  return false;
}

function clauseMatch(regex: RegExp, text: string): string | null {
  const m = regex.exec(text);
  return m?.[1]?.trim() ? norm(m[1]) : null;
}

/**
 * Heuristic extraction of time-bound rules — no ML.
 * Patterns: until/from/before/during + phrase, or the word "transitional".
 */
export function extractTemporalProvision(fullText: string): {
  provisionType: ProvisionType;
  temporalLabels: string[];
} {
  const text = norm(fullText);
  if (!text) {
    return { provisionType: "core", temporalLabels: [] };
  }

  const labels: string[] = [];
  const seen = new Set<string>();

  const push = (line: string): void => {
    const k = line.toLowerCase();
    if (!seen.has(k)) {
      seen.add(k);
      labels.push(line);
    }
  };

  const untilPh = clauseMatch(/\buntil\s+([^.;]{3,240}?)(?=\.|;|$|\s+(?:where|if|unless)\b)/i, text);
  if (untilPh) {
    push(`Valid until: ${untilPh}`);
  }

  const fromPh = clauseMatch(
    /\bfrom\s+(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}(?:[^.;]{0,120})?|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}(?:[^.;]{0,120})?|\d{4}-\d{2}-\d{2}(?:[^.;]{0,120})?)/i,
    text
  );
  if (fromPh) {
    push(`Valid from: ${norm(fromPh)}`);
  }

  const beforePh = clauseMatch(/\bbefore\s+([^.;]{3,220}?)(?=\.|;|$|\s+(?:where|if|unless)\b)/i, text);
  if (beforePh && (DATE_TAIL.test(beforePh) || MONTH_NAMES.test(beforePh))) {
    push(`Valid before: ${beforePh}`);
  }

  const duringPh = clauseMatch(/\bduring\s+([^.;]{3,220}?)(?=\.|;|$|\s+(?:where|if|unless)\b)/i, text);
  if (duringPh) {
    push(`Applies during: ${duringPh}`);
  }

  const hasTransitionalWord = /\btransitional\b/i.test(text);
  const hasTemporalCue =
    labels.length > 0 ||
    hasTransitionalWord ||
    /\buntil\s+/i.test(text) ||
    FROM_DATE_HEAD.test(text) ||
    (/\bbefore\s+/i.test(text) && DATE_TAIL.test(text)) ||
    /\bduring\s+/i.test(text);

  if (!hasTemporalCue) {
    return { provisionType: "core", temporalLabels: [] };
  }

  // "until …" present but primary regex missed punctuation shapes — backup capture
  if (/\buntil\s+/i.test(text) && !labels.some((l) => l.startsWith("Valid until:"))) {
    const soft = clauseMatch(/\buntil\s+([^.;]{3,240})/i, text);
    if (soft) {
      push(`Valid until: ${soft}`);
    }
  }

  return { provisionType: "transitional", temporalLabels: labels };
}

/**
 * Non-transitional shape cues — ordered: definition → cross-reference → exception → core.
 * Kept separate from {@link extractTemporalProvision}: transitional wins when temporal cues apply.
 */
function inferNonTransitionalProvisionType(fullText: string): ProvisionType {
  const t = norm(fullText);
  if (!t) {
    return "core";
  }

  const definition =
    /\bshall\s+mean\b/i.test(t) ||
    /\bis\s+defined\s+as\b/i.test(t) ||
    /(?:«[^»]+»|"[^"]{1,400}")\s+means\b/i.test(t) ||
    /\bthe\s+term\s+[^.\n]{1,120}\bmeans\b/i.test(t);

  if (definition) {
    return "definition";
  }

  const crossReference =
    /\bin\s+accordance\s+with\s+(?:Article|Articles|Annex|Chapter|Section|Part|point|paragraph)\b/i.test(t) ||
    /\bin\s+accordance\s+with\s+(?:Regulation|Directive)\s*\(?/i.test(t) ||
    /\bas\s+provided\s+in\b/i.test(t) ||
    /\bas\s+laid\s+down\s+in\b/i.test(t) ||
    /\bpursuant\s+to\s+(?:Article|Annex|Chapter|paragraph|points?)\b/i.test(t) ||
    /\breference\s+to\s+(?:Article|Articles|Annex)\b/i.test(t) ||
    /\breferred\s+to\s+in\s+(?:Article|Articles|Annex)\b/i.test(t);

  if (crossReference) {
    return "cross_reference";
  }

  const exception =
    /\bby\s+way\s+of\s+derogation\b/i.test(t) ||
    /\bshall\s+not\s+apply\b/i.test(t) ||
    /\b(?:does|do)\s+not\s+apply\b/i.test(t) ||
    /\bexcept\s+(?:where|when|if|that|for|as|in|under)\b/i.test(t);

  if (exception) {
    return "exception";
  }

  return "core";
}

/** Shallow heuristic: operative sentence without trailing conditions, then modal split. */
export function deriveStructuredProposition(rawText: string): StructuredProposition {
  const full = norm(rawText);
  if (!full) {
    return {
      subject: "",
      rule: "",
      object: "",
      conditions: [],
      coreRemainder: "",
      fallbackNoModal: true,
      provisionType: "core",
      temporalLabels: [],
    };
  }

  const temporalMeta = extractTemporalProvision(full);
  const provisionType: ProvisionType =
    temporalMeta.provisionType === "transitional"
      ? "transitional"
      : inferNonTransitionalProvisionType(full);

  const { sentence, conditions } = splitTailConditions(full);
  const conditionsSansTemporal = conditions.filter((c) => !looksTemporalClause(c));

  const hit = findEarliestRule(sentence);
  if (!hit) {
    return {
      subject: "",
      rule: "",
      object: "",
      conditions: conditionsSansTemporal,
      coreRemainder: sentence,
      fallbackNoModal: true,
      provisionType,
      temporalLabels: temporalMeta.temporalLabels,
    };
  }

  const subject = sentence.slice(0, hit.start).trim().replace(/[,:;]+$/, "").trim();
  const rule = hit.text.trim();
  const object = sentence.slice(hit.end).trim().replace(/^[,:;-]\s*/, "").trim();

  return {
    subject,
    rule,
    object,
    conditions: conditionsSansTemporal,
    coreRemainder: "",
    fallbackNoModal: false,
    provisionType,
    temporalLabels: temporalMeta.temporalLabels,
  };
}

/**
 * Instrument title + article/locator line for scanning (fragment_locator / article_reference).
 */
export function buildSourceContextLine(
  oa: UnknownRecord,
  sourceTitleById: ReadonlyMap<string, string>,
  opts?: { sourceRecordId?: string }
): string {
  const sid = opts?.sourceRecordId ?? (typeof oa.source_record_id === "string" ? oa.source_record_id.trim() : "");
  const instrument = sid ? (sourceTitleById.get(sid) ?? sid) : "—";

  const { locatorLine } = propositionSubtitleParts(oa);
  const generic = new Set(["document:full", "full", "document", ""]);
  const articleSegment =
    locatorLine && !generic.has(locatorLine.toLowerCase())
      ? locatorLine
      : typeof oa.article_reference === "string" && oa.article_reference.trim()
        ? oa.article_reference.trim()
        : null;

  const parts = [instrument, articleSegment].filter((p): p is string => Boolean(p && p.trim()));
  return parts.join(" · ") || instrument;
}
