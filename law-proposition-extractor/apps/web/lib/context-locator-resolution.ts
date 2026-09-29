import { formatExcerptForDisplay } from "@/lib/excerpt-display";
import type { SourceFragmentRow } from "@/lib/law-statements-composition";
import {
  isResolvedTypedContext,
  isTypedContextKind,
  type LawStatementRow,
  type PropositionRow,
  type RequiredContextEntry,
} from "@/lib/law-statements-index";

const LOCATOR_KINDS = ["regulation", "schedule", "article", "part", "annex", "paragraph"] as const;
type LocatorKind = (typeof LOCATOR_KINDS)[number];

const REGULATION_LOCATOR_RE =
  /^(?<kind>regulation|schedule|article|paragraph|annex|part)\s*:?\s*(?<num>\d+[a-z]?)(?:\s*\((?<sub>[^)]+)\))?$/i;

const COLON_PATH_RE =
  /^(?<parentKind>regulation|schedule|article|part|annex):(?<parentNum>\d+[a-z]?):(?<childKind>paragraph):(?<childNum>\d+[a-z]?)(?:\((?<childSub>[^)]+)\))?$/i;

const NESTED_COLON_PARAGRAPH_PATH_RE =
  /^(?<parentKind>regulation|schedule|article|part|annex):(?<parentNum>\d+[a-z]?):paragraph:(?<paragraphRest>.+)$/i;

const NESTED_NUM_TOKEN_RE = /^(\d+[a-z]?)(?:\((.+)\))?$/i;

const INSTRUMENT_PARENTHETICAL_RE =
  /^(?<kind>regulation|schedule|article|part)\s+(?<num>\d+[a-z]?)\((?<inner>.+)\)$/i;

const SCHEDULE_PARAGRAPH_TEXT_RE =
  /^(?:schedule|sch\.?)\s*(?<schedule>\d+[a-z]?)(?:\s*[,;]?\s*|\s+)(?:para(?:graph)?s?\s+)(?<paragraph>\d+[a-z]?)(?:\s*\((?<sub>.+)\))?$/i;

const REGULATION_SUB_TEXT_RE =
  /^(?:regulation|reg\.?)\s*(?<regulation>\d+[a-z]?)(?:\s*\((?<sub>[^)]+)\))?$/i;

const BARE_PARAGRAPH_RE =
  /^(?:para(?:graph)?s?)\s+(?<num>\d+[a-z]?)(?:\s*\((?<sub>.+)\))?$/i;

const PARAGRAPH_RANGE_RE =
  /^(?:para(?:graph)?s?)\s+(?<from>\d+[a-z]?)\s*(?:to|–|-)\s*(?<to>\d+[a-z]?)$/i;

const SUB_PARAGRAPH_RE = /^sub-?para(?:graph)?s?\s*\((?<sub>[^)]+)\)$/i;

const PAREN_PARAGRAPH_RE = /^(?:para(?:graph)?s?)\s*\((?<sub>[^)]+)\)$/i;

const PART_OF_SCHEDULE_TEXT_RE =
  /^part\s+(?<part>\d+[a-z]?)\s+of\s+(?:the\s+)?(?:schedule|sch\.?)\s*(?<schedule>\d+[a-z]?)$/i;

const PARTS_OF_SCHEDULE_TEXT_RE =
  /^parts\s+(?<parts>.+?)\s+of\s+(?:the\s+)?(?:schedule|sch\.?)\s*(?<schedule>\d+[a-z]?)$/i;

const YEAR_LIKE_RE = /^(19|20)\d{2}$/;

const EXTERNAL_INSTRUMENT_LOCATOR_RE =
  /\b(?:regulation|reg\.?|article|schedule|part)\s+\d+[a-z]?(?:\s*\([^)]+\))?\s+of\s+the\s+/i;

const STRUCTURAL_CONTAINER_KINDS = new Set(["regulation", "schedule", "article", "part", "annex"]);

const INSTRUMENT_SUB_KINDS = new Set(["regulation", "article", "schedule"]);

export type LocatorSegment = {
  kind: LocatorKind | string;
  num: string;
  sub?: string | null;
};

export type LocatorStructuralContext = {
  sourceRecordId?: string | null;
  segments: LocatorSegment[];
};

export type ParsedLocatorReference =
  | {
      kind: "single";
      display: string;
      segments: LocatorSegment[];
    }
  | {
      kind: "range";
      display: string;
      from: number;
      to: number;
      segmentKind: "paragraph";
      inheritedParent?: LocatorSegment | null;
    };

export type ContextRequirementReason = "not found" | "ambiguous" | "external reference";

export type ResolvedContextFragment = {
  fragmentId: string;
  locator: string;
  excerpt: string;
};

export type ResolvedLocatorChild = {
  locator: string;
  resolved: boolean;
  reason?: ContextRequirementReason;
  fragments: ResolvedContextFragment[];
};

export type ContextRequirementResolution = {
  locator: string;
  exportResolutionStatus: string;
  resolved: boolean;
  reason?: ContextRequirementReason;
  resolutionMode?: "exact" | "container" | "partial";
  fragments: ResolvedContextFragment[];
  inheritedContextLabel?: string;
  resolvedLocator?: string;
  unresolvedChild?: string;
  children?: ResolvedLocatorChild[];
};

export type LocatorResolutionReport = {
  locator: string;
  primarySourceRecordId: string | null;
  parsedLocator: ParsedLocatorReference | null;
  structuralContext: LocatorStructuralContext | null;
  candidateFragmentLocators: string[];
  outcome: {
    exportResolutionStatus: string;
    resolved: boolean;
    reason?: ContextRequirementReason;
    resolutionMode?: ContextRequirementResolution["resolutionMode"];
    resolvedLocator?: string;
    unresolvedChild?: string;
    matchedFragmentIds: string[];
  };
};

export type ContainerLocatorTarget = {
  display: string;
  segments: LocatorSegment[];
};

function isLocatorKind(value: string): value is LocatorKind {
  return (LOCATOR_KINDS as readonly string[]).includes(value);
}

function segmentKey(segment: LocatorSegment): string {
  const sub = segment.sub ? `(${segment.sub})` : "";
  return `${segment.kind} ${segment.num}${sub}`.toLowerCase();
}

function capitalizeLocatorKind(kind: string): string {
  return kind.charAt(0).toUpperCase() + kind.slice(1);
}

function formatContainerLocatorLabel(segments: LocatorSegment[]): string {
  return segments
    .map((segment) => `${capitalizeLocatorKind(segment.kind)} ${segment.num}${segment.sub ? `(${segment.sub})` : ""}`)
    .join(", ");
}

function formatContainerChildLabel(
  parentSegments: LocatorSegment[],
  childSegment: LocatorSegment,
): string {
  const parentLabel = formatContainerLocatorLabel(parentSegments);
  const childLabel = `${capitalizeLocatorKind(childSegment.kind)} ${childSegment.num}${childSegment.sub ? `(${childSegment.sub})` : ""}`;
  return `${parentLabel}, ${childLabel}`;
}

function isStructuralContainerKind(kind: string): boolean {
  return STRUCTURAL_CONTAINER_KINDS.has(kind);
}

function parsePartNumberList(text: string): string[] {
  return text
    .split(/\s*(?:,|and|or)\s*/i)
    .map((part) => part.trim().toLowerCase())
    .filter((part) => /^\d+[a-z]?$/.test(part));
}

function parseNestedNumToken(token: string): { num: string; sub: string | null } | null {
  const match = String(token ?? "")
    .trim()
    .toLowerCase()
    .match(NESTED_NUM_TOKEN_RE);
  if (!match) {
    return null;
  }
  const sub = match[2]?.trim();
  return { num: match[1]!, sub: sub ? sub : null };
}

function formatNestedNumToken(num: string, sub: string | null | undefined): string {
  return sub ? `${num}(${sub})` : num;
}

function paragraphPathMatchesPrefix(
  fragNum: string,
  fragSub: string | null | undefined,
  prefixNum: string,
  prefixSub: string | null | undefined,
): boolean {
  const fragLabel = formatNestedNumToken(fragNum.toLowerCase(), fragSub?.toLowerCase() ?? null);
  const prefixLabel = formatNestedNumToken(prefixNum.toLowerCase(), prefixSub?.toLowerCase() ?? null);
  if (fragLabel === prefixLabel) {
    return true;
  }
  if (!prefixSub) {
    return fragLabel === prefixNum.toLowerCase() || fragLabel.startsWith(`${prefixNum.toLowerCase()}(`);
  }
  return fragLabel.startsWith(`${prefixLabel}(`);
}

function segmentMatchesPrefix(candidate: LocatorSegment, prefix: LocatorSegment): boolean {
  if (candidate.kind !== prefix.kind || candidate.num !== prefix.num) {
    return false;
  }
  if (prefix.kind === "paragraph") {
    return paragraphPathMatchesPrefix(candidate.num, candidate.sub, prefix.num, prefix.sub);
  }
  return prefix.sub == null || candidate.sub === prefix.sub;
}

function parseParentheticalInstrumentSegments(kind: string, num: string, inner: string): LocatorSegment[] {
  const normalizedKind = kind.toLowerCase();
  const normalizedNum = num.toLowerCase();
  const normalizedInner = inner.trim().toLowerCase();
  if (normalizedKind === "schedule") {
    const parsed = parseNestedNumToken(normalizedInner);
    const paraNum = parsed?.num ?? normalizedInner;
    const paraSub = parsed?.sub ?? null;
    return [
      { kind: "schedule", num: normalizedNum },
      { kind: "paragraph", num: paraNum, sub: paraSub },
    ];
  }
  if (!normalizedInner.includes("(")) {
    return [{ kind: normalizedKind, num: normalizedNum, sub: normalizedInner }];
  }
  const parsed = parseNestedNumToken(normalizedInner);
  if (parsed) {
    return [
      { kind: normalizedKind, num: normalizedNum },
      { kind: "paragraph", num: parsed.num, sub: parsed.sub },
    ];
  }
  return [{ kind: normalizedKind, num: normalizedNum, sub: normalizedInner }];
}

function parseColonParagraphPathSegments(raw: string): LocatorSegment[] | null {
  const nested = raw.match(NESTED_COLON_PARAGRAPH_PATH_RE);
  if (!nested?.groups) {
    return null;
  }
  const parsed = parseNestedNumToken(nested.groups.paragraphRest);
  const paraNum = parsed?.num ?? nested.groups.paragraphRest.toLowerCase();
  const paraSub = parsed?.sub ?? null;
  return [
    { kind: nested.groups.parentKind.toLowerCase(), num: nested.groups.parentNum.toLowerCase() },
    { kind: "paragraph", num: paraNum, sub: paraSub },
  ];
}

export function parseColonLocatorSegments(locator: string | null | undefined): LocatorSegment[] | null {
  const raw = String(locator ?? "")
    .trim()
    .toLowerCase()
    .split("|chunk:")[0]
    ?.trim();
  if (!raw?.includes(":")) {
    return null;
  }

  const nestedParagraphPath = parseColonParagraphPathSegments(raw);
  if (nestedParagraphPath) {
    return nestedParagraphPath;
  }

  const paragraphPath = raw.match(COLON_PATH_RE);
  if (paragraphPath?.groups) {
    return [
      { kind: paragraphPath.groups.parentKind, num: paragraphPath.groups.parentNum },
      {
        kind: "paragraph",
        num: paragraphPath.groups.childNum,
        sub: paragraphPath.groups.childSub?.trim() ?? null,
      },
    ];
  }

  const tokens = raw.split(":");
  if (tokens.length < 2 || tokens.length % 2 !== 0) {
    return null;
  }

  const segments: LocatorSegment[] = [];
  for (let index = 0; index < tokens.length; index += 2) {
    const kind = tokens[index]!;
    const numToken = tokens[index + 1]!;
    if (!isLocatorKind(kind)) {
      return null;
    }
    const parsedNum = parseNestedNumToken(numToken);
    if (!parsedNum) {
      return null;
    }
    segments.push({
      kind,
      num: parsedNum.num,
      sub: parsedNum.sub,
    });
  }
  return segments.length > 0 ? segments : null;
}

function locatorSegmentPath(locator: string): LocatorSegment[] | null {
  return parseColonLocatorSegments(locator) ?? parseLocatorStructuralContext(locator)?.segments ?? null;
}

function segmentPathHasPrefix(path: LocatorSegment[], prefix: LocatorSegment[]): boolean {
  if (path.length < prefix.length) {
    return false;
  }
  return prefix.every((segment, index) => {
    const candidate = path[index];
    return candidate !== undefined && segmentMatchesPrefix(candidate, segment);
  });
}

function segmentPathIsDescendant(path: LocatorSegment[], prefix: LocatorSegment[]): boolean {
  if (!segmentPathHasPrefix(path, prefix) || path.length < prefix.length) {
    return false;
  }
  if (path.length === prefix.length) {
    const lastPath = path[path.length - 1];
    const lastPrefix = prefix[prefix.length - 1];
    if (!lastPath || !lastPrefix || lastPath.kind !== "paragraph" || lastPrefix.kind !== "paragraph") {
      return false;
    }
    const fragLabel = formatNestedNumToken(lastPath.num, lastPath.sub);
    const prefixLabel = formatNestedNumToken(lastPrefix.num, lastPrefix.sub);
    return fragLabel !== prefixLabel && fragLabel.startsWith(`${prefixLabel}(`);
  }
  return true;
}

export function parseContainerLocatorTargets(locator: string | null | undefined): ContainerLocatorTarget[] | null {
  const raw = String(locator ?? "").trim();
  if (!raw) {
    return null;
  }

  const partsOfSchedule = raw.match(PARTS_OF_SCHEDULE_TEXT_RE);
  if (partsOfSchedule?.groups) {
    const schedule = partsOfSchedule.groups.schedule.toLowerCase();
    const partNums = parsePartNumberList(partsOfSchedule.groups.parts);
    if (partNums.length < 2) {
      return null;
    }
    const parent = { kind: "schedule", num: schedule };
    return partNums.map((part) => ({
      display: formatContainerChildLabel([parent], { kind: "part", num: part }),
      segments: [parent, { kind: "part", num: part }],
    }));
  }

  const partOfSchedule = raw.match(PART_OF_SCHEDULE_TEXT_RE);
  if (partOfSchedule?.groups) {
    const schedule = partOfSchedule.groups.schedule.toLowerCase();
    const part = partOfSchedule.groups.part.toLowerCase();
    const parent = { kind: "schedule", num: schedule };
    return [
      {
        display: formatContainerChildLabel([parent], { kind: "part", num: part }),
        segments: [parent, { kind: "part", num: part }],
      },
    ];
  }

  const colonSegments = parseColonLocatorSegments(raw);
  if (colonSegments) {
    const last = colonSegments[colonSegments.length - 1];
    if (
      last &&
      (last.kind === "part" ||
        (colonSegments.length === 1 && isStructuralContainerKind(last.kind)))
    ) {
      return [{ display: formatContainerLocatorLabel(colonSegments), segments: colonSegments }];
    }
  }

  const parsed = parseLocatorReference(raw);
  if (parsed?.kind === "single" && parsed.segments.length === 1) {
    const segment = parsed.segments[0];
    if (segment && isStructuralContainerKind(segment.kind)) {
      return [{ display: formatContainerLocatorLabel(parsed.segments), segments: parsed.segments }];
    }
  }

  return null;
}

function groupFragmentsByImmediateChild(
  containerSegments: LocatorSegment[],
  fragments: ResolvedContextFragment[],
): ResolvedLocatorChild[] {
  const groups = new Map<string, ResolvedLocatorChild>();

  for (const fragment of fragments) {
    const path = locatorSegmentPath(fragment.locator);
    if (!path || !segmentPathHasPrefix(path, containerSegments)) {
      continue;
    }

    let key: string;
    let childLocator: string;
    if (path.length === containerSegments.length) {
      key = "__self__";
      childLocator = formatContainerLocatorLabel(containerSegments);
    } else {
      const childSegments = path.slice(0, containerSegments.length + 1);
      const childSegment = childSegments[childSegments.length - 1]!;
      key = childSegments.map((segment) => `${segment.kind}:${segment.num}`).join("/");
      childLocator = formatContainerChildLabel(containerSegments, childSegment);
    }

    const existing = groups.get(key);
    if (existing) {
      existing.fragments.push(fragment);
      continue;
    }
    groups.set(key, {
      locator: childLocator,
      resolved: true,
      fragments: [fragment],
    });
  }

  return Array.from(groups.values());
}

function matchFragmentsForContainerTarget(
  sourceRecordId: string,
  target: ContainerLocatorTarget,
  sourceFragments: SourceFragmentRow[],
): ResolvedContextFragment[] {
  const matches: ResolvedContextFragment[] = [];
  const seen = new Set<string>();

  for (const fragment of sourceFragments) {
    if (String(fragment.source_record_id ?? "").trim() !== sourceRecordId) {
      continue;
    }
    const fragmentLocator = String(fragment.locator ?? "").trim();
    if (!fragmentLocator) {
      continue;
    }

    const path = locatorSegmentPath(fragmentLocator);
    const matchesTarget =
      (path && segmentPathHasPrefix(path, target.segments)) ||
      locatorMatchesTarget(fragmentLocator, buildCanonicalLocator(target.segments));
    if (!matchesTarget) {
      continue;
    }

    const fragmentId = fragmentRowId(fragment);
    if (!fragmentId || seen.has(fragmentId)) {
      continue;
    }
    seen.add(fragmentId);
    matches.push({
      fragmentId,
      locator: fragmentLocator,
      excerpt: fragmentExcerpt(fragment),
    });
  }

  return matches;
}

function resolveContainerLocatorTargets(
  targets: ContainerLocatorTarget[],
  options: {
    sourceRecordId: string | null;
    sourceFragments: SourceFragmentRow[];
  },
): ContextRequirementResolution | null {
  if (!options.sourceRecordId || targets.length === 0) {
    return null;
  }

  if (targets.length === 1) {
    const target = targets[0]!;
    const matches = matchFragmentsForContainerTarget(
      options.sourceRecordId,
      target,
      options.sourceFragments,
    );
    if (matches.length === 0) {
      return null;
    }
    if (matches.length === 1) {
      return {
        locator: "",
        exportResolutionStatus: "",
        resolved: true,
        resolutionMode: "exact",
        fragments: matches,
      };
    }

    const children =
      target.segments.length === 1 && isStructuralContainerKind(target.segments[0]!.kind)
        ? groupFragmentsByImmediateChild(target.segments, matches)
        : [
            {
              locator: target.display,
              resolved: true,
              fragments: matches,
            },
          ];

    if (children.length === 0) {
      return null;
    }

    return {
      locator: "",
      exportResolutionStatus: "",
      resolved: true,
      resolutionMode: "container",
      fragments: matches,
      children,
      resolvedLocator: children.map((child) => child.locator).join(", "),
    };
  }

  const children: ResolvedLocatorChild[] = targets.map((target) => {
    const fragments = matchFragmentsForContainerTarget(
      options.sourceRecordId!,
      target,
      options.sourceFragments,
    );
    return {
      locator: target.display,
      resolved: fragments.length > 0,
      reason: fragments.length > 0 ? undefined : ("not found" as const),
      fragments,
    };
  });
  const resolvedChildren = children.filter((child) => child.resolved);
  if (resolvedChildren.length === 0) {
    return null;
  }

  return {
    locator: "",
    exportResolutionStatus: "",
    resolved: resolvedChildren.length === children.length,
    resolutionMode: "container",
    reason: resolvedChildren.length === children.length ? undefined : "not found",
    fragments: resolvedChildren.flatMap((child) => child.fragments),
    children,
    resolvedLocator: children.map((child) => child.locator).join(", "),
  };
}

function isYearLike(num: string): boolean {
  return YEAR_LIKE_RE.test(num.trim());
}

export function parseLocatorStructuralContext(
  locator: string | null | undefined,
): LocatorStructuralContext | null {
  const raw = String(locator ?? "").trim();
  if (!raw) {
    return null;
  }

  const colonSegments = parseColonLocatorSegments(raw);
  if (colonSegments) {
    return { segments: colonSegments };
  }

  const colonPath = raw.match(COLON_PATH_RE);
  if (colonPath?.groups) {
    const segments: LocatorSegment[] = [
      { kind: colonPath.groups.parentKind.toLowerCase(), num: colonPath.groups.parentNum.toLowerCase() },
      {
        kind: "paragraph",
        num: colonPath.groups.childNum.toLowerCase(),
        sub: colonPath.groups.childSub?.trim().toLowerCase() ?? null,
      },
    ];
    return { segments };
  }

  const scheduleParagraph = raw.match(SCHEDULE_PARAGRAPH_TEXT_RE);
  if (scheduleParagraph?.groups) {
    return {
      segments: [
        { kind: "schedule", num: scheduleParagraph.groups.schedule.toLowerCase() },
        {
          kind: "paragraph",
          num: scheduleParagraph.groups.paragraph.toLowerCase(),
          sub: scheduleParagraph.groups.sub?.trim().toLowerCase() ?? null,
        },
      ],
    };
  }

  const regulationSub = raw.match(REGULATION_SUB_TEXT_RE);
  if (regulationSub?.groups) {
    const segment: LocatorSegment = {
      kind: "regulation",
      num: regulationSub.groups.regulation.toLowerCase(),
      sub: regulationSub.groups.sub?.trim().toLowerCase() ?? null,
    };
    return { segments: [segment] };
  }

  const norm = normalizeCrossReferenceLocator(raw);
  const instrumentParenthetical = norm.match(INSTRUMENT_PARENTHETICAL_RE);
  if (instrumentParenthetical?.groups) {
    return {
      segments: parseParentheticalInstrumentSegments(
        instrumentParenthetical.groups.kind,
        instrumentParenthetical.groups.num,
        instrumentParenthetical.groups.inner,
      ),
    };
  }

  const parts = locatorParts(norm);
  if (parts) {
    return {
      segments: [
        {
          kind: parts.kind,
          num: parts.num,
          sub: parts.sub,
        },
      ],
    };
  }

  const colonBase = raw
    .toLowerCase()
    .split("|chunk:")[0]
    ?.trim()
    .match(/^(regulation|schedule|article|part|annex):(\d+[a-z]?)$/);
  if (colonBase) {
    return {
      segments: [{ kind: colonBase[1]!, num: colonBase[2]! }],
    };
  }

  return null;
}

export function formatInheritedContextLabel(context: LocatorStructuralContext | null): string | undefined {
  if (!context?.segments?.length) {
    return undefined;
  }
  const parent = context.segments[0];
  if (!parent) {
    return undefined;
  }
  const labelKind = parent.kind.charAt(0).toUpperCase() + parent.kind.slice(1);
  const sub = parent.sub ? `(${parent.sub})` : "";
  return `resolved within ${labelKind} ${parent.num}${sub}`;
}

function parentSegmentForInheritance(context: LocatorStructuralContext): LocatorSegment | null {
  if (context.segments.length === 0) {
    return null;
  }
  if (context.segments.length === 1) {
    return context.segments[0] ?? null;
  }
  const first = context.segments[0];
  if (!first) {
    return null;
  }
  if (first.kind === "schedule" || first.kind === "regulation" || first.kind === "article" || first.kind === "part") {
    return first;
  }
  return context.segments[context.segments.length - 2] ?? first;
}

function buildCanonicalLocator(segments: LocatorSegment[]): string {
  if (segments.length === 0) {
    return "";
  }
  if (segments.length === 1) {
    const only = segments[0]!;
    if (only.sub) {
      return `${only.kind} ${only.num}(${only.sub})`;
    }
    return `${only.kind} ${only.num}`;
  }

  const parent = segments[0]!;
  const child = segments[segments.length - 1]!;
  if (
    (parent.kind === "schedule" || parent.kind === "regulation" || parent.kind === "article" || parent.kind === "part") &&
    child.kind === "paragraph"
  ) {
    if (child.sub) {
      return `${parent.kind} ${parent.num}(${child.num}(${child.sub}))`;
    }
    return `${parent.kind} ${parent.num}(${child.num})`;
  }

  return segments.map((segment) => segmentKey(segment)).join(" ");
}

function expandNumericRange(from: number, to: number): number[] {
  if (!Number.isFinite(from) || !Number.isFinite(to)) {
    return [];
  }
  const start = Math.min(from, to);
  const end = Math.max(from, to);
  if (end - start > 50) {
    return [];
  }
  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

export function parseLocatorReference(text: string | null | undefined): ParsedLocatorReference | null {
  const raw = String(text ?? "").trim();
  if (!raw) {
    return null;
  }

  const scheduleParagraph = raw.match(SCHEDULE_PARAGRAPH_TEXT_RE);
  if (scheduleParagraph?.groups) {
    return {
      kind: "single",
      display: raw,
      segments: [
        { kind: "schedule", num: scheduleParagraph.groups.schedule.toLowerCase() },
        {
          kind: "paragraph",
          num: scheduleParagraph.groups.paragraph.toLowerCase(),
          sub: scheduleParagraph.groups.sub?.trim().toLowerCase() ?? null,
        },
      ],
    };
  }

  const regulationSub = raw.match(REGULATION_SUB_TEXT_RE);
  if (regulationSub?.groups) {
    return {
      kind: "single",
      display: raw,
      segments: [
        {
          kind: "regulation",
          num: regulationSub.groups.regulation.toLowerCase(),
          sub: regulationSub.groups.sub?.trim().toLowerCase() ?? null,
        },
      ],
    };
  }

  const range = raw.match(PARAGRAPH_RANGE_RE);
  if (range?.groups) {
    const from = Number.parseInt(range.groups.from, 10);
    const to = Number.parseInt(range.groups.to, 10);
    if (!isYearLike(range.groups.from) && !isYearLike(range.groups.to) && expandNumericRange(from, to).length > 0) {
      return {
        kind: "range",
        display: raw,
        from,
        to,
        segmentKind: "paragraph",
      };
    }
  }

  const subParagraph = raw.match(SUB_PARAGRAPH_RE);
  if (subParagraph?.groups) {
    return {
      kind: "single",
      display: raw,
      segments: [{ kind: "sub-paragraph", num: subParagraph.groups.sub.trim().toLowerCase() }],
    };
  }

  const parenParagraph = raw.match(PAREN_PARAGRAPH_RE);
  if (parenParagraph?.groups) {
    return {
      kind: "single",
      display: raw,
      segments: [{ kind: "paragraph", num: parenParagraph.groups.sub.trim().toLowerCase() }],
    };
  }

  const bareParagraph = raw.match(BARE_PARAGRAPH_RE);
  if (bareParagraph?.groups && !isYearLike(bareParagraph.groups.num)) {
    return {
      kind: "single",
      display: raw,
      segments: [
        {
          kind: "paragraph",
          num: bareParagraph.groups.num.toLowerCase(),
          sub: bareParagraph.groups.sub?.trim().toLowerCase() ?? null,
        },
      ],
    };
  }

  const norm = normalizeCrossReferenceLocator(raw);
  const parts = locatorParts(norm);
  if (parts && !isYearLike(parts.num)) {
    return {
      kind: "single",
      display: raw,
      segments: [{ kind: parts.kind, num: parts.num, sub: parts.sub }],
    };
  }

  return null;
}

export function applyStructuralContextToReference(
  context: LocatorStructuralContext | null,
  reference: ParsedLocatorReference,
): ParsedLocatorReference {
  if (!context || context.segments.length === 0) {
    return reference;
  }

  if (reference.kind === "range") {
    const parent = parentSegmentForInheritance(context);
    return {
      ...reference,
      inheritedParent: parent,
    };
  }

  const refSegment = reference.segments[0];
  if (!refSegment) {
    return reference;
  }

  if (refSegment.kind !== "paragraph" && refSegment.kind !== "sub-paragraph" && isLocatorKind(refSegment.kind)) {
    return reference;
  }

  const parent = parentSegmentForInheritance(context);
  if (!parent) {
    return reference;
  }

  if (refSegment.kind === "sub-paragraph" || (refSegment.kind === "paragraph" && parent.kind === "regulation")) {
    if (parent.kind === "regulation" || parent.kind === "article") {
      return {
        kind: "single",
        display: reference.display,
        segments: [{ kind: parent.kind, num: parent.num, sub: refSegment.num }],
      };
    }
  }

  if (refSegment.kind === "paragraph") {
    if (parent.kind === "schedule" || parent.kind === "regulation" || parent.kind === "article" || parent.kind === "part") {
      return {
        kind: "single",
        display: reference.display,
        segments: [
          parent,
          {
            kind: "paragraph",
            num: refSegment.num,
            sub: refSegment.sub ?? null,
          },
        ],
      };
    }
  }

  return reference;
}

export function expandParsedLocatorReference(reference: ParsedLocatorReference): ParsedLocatorReference[] {
  if (reference.kind === "single") {
    return [reference];
  }

  const numbers = expandNumericRange(reference.from, reference.to);
  const parent = reference.inheritedParent ?? null;
  return numbers.map((num) => ({
    kind: "single" as const,
    display: `paragraph ${num}`,
    segments: parent
      ? [parent, { kind: "paragraph" as const, num: String(num), sub: null }]
      : [{ kind: "paragraph" as const, num: String(num), sub: null }],
  }));
}

export function resolveLocatorTargets(
  locatorText: string,
  context: LocatorStructuralContext | null,
): string[] {
  const parsed = parseLocatorReference(locatorText);
  if (!parsed) {
    return [locatorText];
  }

  const contextualised =
    parsed.kind === "range"
      ? applyStructuralContextToReference(context, parsed)
      : applyStructuralContextToReference(context, parsed);

  const expanded = expandParsedLocatorReference(contextualised);
  const targets = expanded
    .map((entry) => buildCanonicalLocator(entry.segments))
    .filter((entry) => entry.trim().length > 0);

  return targets.length > 0 ? targets : [locatorText];
}

export function normalizeCrossReferenceLocator(locator: string | null | undefined): string {
  const raw = String(locator ?? "")
    .trim()
    .toLowerCase();
  if (!raw) {
    return "";
  }
  let base = raw.split("|chunk:")[0]?.trim() ?? "";
  base = base.replace(/\s+/g, " ");

  const nestedColonPath = parseColonParagraphPathSegments(base);
  if (nestedColonPath) {
    return buildCanonicalLocator(nestedColonPath);
  }

  const colonPath = base.match(COLON_PATH_RE);
  if (colonPath?.groups) {
    const sub = colonPath.groups.childSub?.trim().toLowerCase();
    if (sub) {
      return `${colonPath.groups.parentKind} ${colonPath.groups.parentNum}(${colonPath.groups.childNum}(${sub}))`;
    }
    return `${colonPath.groups.parentKind} ${colonPath.groups.parentNum}(${colonPath.groups.childNum})`;
  }

  const scheduleParagraph = base.match(SCHEDULE_PARAGRAPH_TEXT_RE);
  if (scheduleParagraph?.groups) {
    const sub = scheduleParagraph.groups.sub?.trim().toLowerCase();
    if (sub) {
      return `schedule ${scheduleParagraph.groups.schedule}(${scheduleParagraph.groups.paragraph}(${sub}))`;
    }
    return `schedule ${scheduleParagraph.groups.schedule}(${scheduleParagraph.groups.paragraph})`;
  }

  const colonMatch = base.match(/^(regulation|schedule|article|paragraph|annex|part):(.+)$/);
  if (colonMatch) {
    const kind = colonMatch[1]!;
    const rest = colonMatch[2]!.trim();
    const paragraphMatch = rest.match(/^(\d+[a-z]?):paragraph:(.+)$/);
    if (paragraphMatch) {
      const parsed = parseNestedNumToken(paragraphMatch[2]!);
      const paraNum = parsed?.num ?? paragraphMatch[2]!.toLowerCase();
      const paraSub = parsed?.sub ?? null;
      return buildCanonicalLocator([
        { kind, num: paragraphMatch[1]!.toLowerCase() },
        { kind: "paragraph", num: paraNum, sub: paraSub },
      ]);
    }
    const subMatch = rest.match(/^(\d+[a-z]?)(?:\(([^)]+)\))?$/);
    if (subMatch) {
      const num = subMatch[1]!;
      const sub = subMatch[2];
      if (sub) {
        return `${kind} ${num}(${sub.trim()})`;
      }
      return `${kind} ${num}`;
    }
  }

  const paraAlias = base.match(/^para(?:graph)?s?\s+(\d+[a-z]?)(?:\s*\((.+)\))?$/i);
  if (paraAlias) {
    const sub = paraAlias[2]?.trim().toLowerCase();
    if (sub) {
      return `paragraph ${paraAlias[1]!.toLowerCase()}(${sub})`;
    }
    return `paragraph ${paraAlias[1]!.toLowerCase()}`;
  }

  const spaceBase = base.replace(/:/g, " ");
  const spaceMatch = spaceBase.match(REGULATION_LOCATOR_RE);
  if (spaceMatch?.groups) {
    const kind = spaceMatch.groups.kind.toLowerCase();
    const num = spaceMatch.groups.num.toLowerCase();
    const sub = spaceMatch.groups.sub;
    if (sub) {
      return `${kind} ${num}(${sub.trim().toLowerCase()})`;
    }
    return `${kind} ${num}`;
  }
  return base;
}

function locatorParts(
  locator: string,
): { kind: string; num: string; sub: string | null } | null {
  const norm = normalizeCrossReferenceLocator(locator);
  const match = norm.match(REGULATION_LOCATOR_RE);
  if (!match?.groups) {
    return null;
  }
  return {
    kind: match.groups.kind.toLowerCase(),
    num: match.groups.num.toLowerCase(),
    sub: match.groups.sub?.trim().toLowerCase() ?? null,
  };
}

function crossFormInstrumentSubMatch(
  fragmentPath: LocatorSegment[],
  targetPath: LocatorSegment[],
): boolean {
  if (targetPath.length !== 1) {
    return false;
  }
  const target = targetPath[0];
  if (!target?.sub || !INSTRUMENT_SUB_KINDS.has(target.kind)) {
    return false;
  }

  const fragmentRegulation = fragmentPath.find(
    (segment) => segment.kind === target.kind && segment.num === target.num,
  );
  if (!fragmentRegulation) {
    return false;
  }

  const fragmentParagraph = fragmentPath.find((segment) => segment.kind === "paragraph");
  if (fragmentParagraph) {
    return (
      fragmentParagraph.num === target.sub &&
      (fragmentParagraph.sub == null || fragmentParagraph.sub === target.sub)
    );
  }

  return fragmentRegulation.sub === target.sub;
}

export function locatorMatchesTarget(fragmentLocator: string, targetLocator: string): boolean {
  const propNorm = normalizeCrossReferenceLocator(fragmentLocator);
  const targetNorm = normalizeCrossReferenceLocator(targetLocator);
  if (!propNorm || !targetNorm) {
    return false;
  }
  if (propNorm === targetNorm) {
    return true;
  }

  const propPath = parseLocatorStructuralContext(fragmentLocator);
  const targetPath = parseLocatorStructuralContext(targetLocator);
  if (propPath && targetPath) {
    const propCanonical = buildCanonicalLocator(propPath.segments);
    const targetCanonical = buildCanonicalLocator(targetPath.segments);
    if (propCanonical && targetCanonical && propCanonical === targetCanonical) {
      return true;
    }
    if (segmentPathHasPrefix(propPath.segments, targetPath.segments)) {
      return true;
    }
    if (crossFormInstrumentSubMatch(propPath.segments, targetPath.segments)) {
      return true;
    }
  }

  const propParts = locatorParts(propNorm);
  const targetParts = locatorParts(targetNorm);
  if (propParts === null || targetParts === null) {
    return propNorm.startsWith(`${targetNorm}(`) || propNorm.startsWith(`${targetNorm} `);
  }
  if (propParts.kind !== targetParts.kind || propParts.num !== targetParts.num) {
    return false;
  }
  if (targetParts.sub === null) {
    return true;
  }
  if (propParts.kind === "paragraph") {
    return paragraphPathMatchesPrefix(propParts.num, propParts.sub, targetParts.num, targetParts.sub);
  }
  return propParts.sub === targetParts.sub;
}

function formatUnresolvedChildLabel(sub: string): string {
  return `paragraph (${sub})`;
}

function isExternalInstrumentLocator(locator: string): boolean {
  return EXTERNAL_INSTRUMENT_LOCATOR_RE.test(locator);
}

function instrumentSubReference(parsed: ParsedLocatorReference): LocatorSegment | null {
  if (parsed.kind !== "single" || parsed.segments.length !== 1) {
    return null;
  }
  const segment = parsed.segments[0];
  if (!segment?.sub || !INSTRUMENT_SUB_KINDS.has(segment.kind)) {
    return null;
  }
  return segment;
}

function searchTargetsForInstrumentSub(segment: LocatorSegment): string[] {
  const parent = buildCanonicalLocator([{ kind: segment.kind, num: segment.num, sub: null }]);
  if (!segment.sub) {
    return [parent];
  }
  const colonParagraphChild = `${segment.kind}:${segment.num}:paragraph:${segment.sub}`;
  const exact = buildCanonicalLocator([segment]);
  const paragraphChild = buildCanonicalLocator([
    { kind: segment.kind, num: segment.num, sub: null },
    { kind: "paragraph", num: segment.sub, sub: null },
  ]);
  return Array.from(new Set([colonParagraphChild, exact, paragraphChild, parent]));
}

export function listCandidateFragmentLocators(
  sourceRecordId: string | null,
  locator: string,
  sourceFragments: SourceFragmentRow[],
): string[] {
  if (!sourceRecordId) {
    return [];
  }

  const parsed = parseLocatorReference(locator);
  const targets = new Set<string>([locator, normalizeCrossReferenceLocator(locator)]);
  if (parsed) {
    const subSegment = instrumentSubReference(parsed);
    if (subSegment) {
      for (const target of searchTargetsForInstrumentSub(subSegment)) {
        targets.add(target);
      }
    } else if (parsed.kind === "single") {
      targets.add(buildCanonicalLocator(parsed.segments));
    }
  }

  const candidates = new Set<string>();
  for (const fragment of sourceFragments) {
    if (String(fragment.source_record_id ?? "").trim() !== sourceRecordId) {
      continue;
    }
    const fragmentLocator = String(fragment.locator ?? "").trim();
    if (!fragmentLocator) {
      continue;
    }
    candidates.add(fragmentLocator);
    for (const target of targets) {
      if (locatorMatchesTarget(fragmentLocator, target)) {
        candidates.add(fragmentLocator);
      }
    }
  }

  return Array.from(candidates).sort((left, right) => left.localeCompare(right));
}

function resolveInstrumentSubLocator(
  locator: string,
  options: {
    sourceRecordId: string | null;
    sourceFragments: SourceFragmentRow[];
    inheritedContextLabel?: string;
    exportResolutionStatus: string;
  },
): ContextRequirementResolution | null {
  const parsed = parseLocatorReference(locator);
  const segment = parsed ? instrumentSubReference(parsed) : null;
  if (!segment || !options.sourceRecordId) {
    return null;
  }

  const targets = searchTargetsForInstrumentSub(segment);
  const exactTarget = targets[0]!;
  const parentTarget = targets[targets.length - 1]!;

  for (const target of targets.slice(0, -1)) {
    const exactMatches = matchFragmentsInSource(
      options.sourceRecordId,
      target,
      options.sourceFragments,
    );
    if (exactMatches.length === 1) {
      return {
        locator,
        exportResolutionStatus: options.exportResolutionStatus,
        resolved: true,
        resolutionMode: "exact",
        fragments: exactMatches,
        inheritedContextLabel: options.inheritedContextLabel,
        resolvedLocator: target,
      };
    }
    if (exactMatches.length > 1) {
      return {
        locator,
        exportResolutionStatus: options.exportResolutionStatus,
        resolved: false,
        reason: "ambiguous",
        fragments: exactMatches,
        inheritedContextLabel: options.inheritedContextLabel,
        resolvedLocator: target,
      };
    }
  }

  const parentMatches = matchParentOnlyFragmentsInSource(
    options.sourceRecordId,
    parentTarget,
    options.sourceFragments,
  );
  if (parentMatches.length === 1) {
    return {
      locator,
      exportResolutionStatus: "partially_resolved",
      resolved: true,
      resolutionMode: "partial",
      fragments: parentMatches,
      inheritedContextLabel: options.inheritedContextLabel,
      resolvedLocator: parentTarget,
      unresolvedChild: formatUnresolvedChildLabel(segment.sub!),
    };
  }
  if (parentMatches.length > 1) {
    return {
      locator,
      exportResolutionStatus: options.exportResolutionStatus,
      resolved: false,
      reason: "ambiguous",
      fragments: parentMatches,
      inheritedContextLabel: options.inheritedContextLabel,
      resolvedLocator: parentTarget,
    };
  }

  return null;
}

function fragmentRowId(fragment: SourceFragmentRow): string {
  return String(fragment.id ?? fragment.fragment_id ?? "").trim();
}

function fragmentExcerpt(fragment: SourceFragmentRow): string {
  return formatExcerptForDisplay(String(fragment.fragment_text ?? "").trim(), "");
}

function fragmentsForPropositionIds(
  propositionIds: string[],
  propositionById: Map<string, PropositionRow>,
  fragmentById: Map<string, SourceFragmentRow>,
): ResolvedContextFragment[] {
  const seen = new Set<string>();
  const resolved: ResolvedContextFragment[] = [];
  for (const propositionId of propositionIds) {
    const fragmentId = propositionById.get(propositionId)?.source_fragment_id?.trim();
    if (!fragmentId || seen.has(fragmentId)) {
      continue;
    }
    const fragment = fragmentById.get(fragmentId);
    if (!fragment) {
      continue;
    }
    seen.add(fragmentId);
    resolved.push({
      fragmentId,
      locator: String(fragment.locator ?? propositionById.get(propositionId)?.fragment_locator ?? "").trim(),
      excerpt: fragmentExcerpt(fragment),
    });
  }
  return resolved;
}

function isExactSegmentPathMatch(path: LocatorSegment[], targetSegments: LocatorSegment[]): boolean {
  if (path.length !== targetSegments.length) {
    return false;
  }
  return targetSegments.every((target, index) => {
    const candidate = path[index];
    if (!candidate || candidate.kind !== target.kind || candidate.num !== target.num) {
      return false;
    }
    if (target.kind === "paragraph") {
      return (
        formatNestedNumToken(candidate.num, candidate.sub) ===
        formatNestedNumToken(target.num, target.sub)
      );
    }
    return target.sub == null || candidate.sub === target.sub;
  });
}

function matchFragmentsBySegmentPath(
  sourceRecordId: string,
  targetSegments: LocatorSegment[],
  sourceFragments: SourceFragmentRow[],
): ResolvedContextFragment[] {
  const targetCanonical = buildCanonicalLocator(targetSegments);
  const matches: ResolvedContextFragment[] = [];
  const seen = new Set<string>();
  for (const fragment of sourceFragments) {
    if (String(fragment.source_record_id ?? "").trim() !== sourceRecordId) {
      continue;
    }
    const fragmentLocator = String(fragment.locator ?? "").trim();
    if (!fragmentLocator) {
      continue;
    }
    const path = locatorSegmentPath(fragmentLocator);
    const matchesTarget =
      (path && segmentPathHasPrefix(path, targetSegments)) ||
      locatorMatchesTarget(fragmentLocator, targetCanonical);
    if (!matchesTarget) {
      continue;
    }
    const fragmentId = fragmentRowId(fragment);
    if (!fragmentId || seen.has(fragmentId)) {
      continue;
    }
    seen.add(fragmentId);
    matches.push({
      fragmentId,
      locator: fragmentLocator,
      excerpt: fragmentExcerpt(fragment),
    });
  }
  return matches;
}

function matchPropositionsBySegmentPath(
  sourceRecordId: string,
  targetSegments: LocatorSegment[],
  propositionById: Map<string, PropositionRow>,
): string[] {
  const targetCanonical = buildCanonicalLocator(targetSegments);
  const matched: string[] = [];
  const seen = new Set<string>();
  for (const [propId, proposition] of propositionById) {
    if (String(proposition.source_record_id ?? "").trim() !== sourceRecordId) {
      continue;
    }
    const propLocator = String(proposition.fragment_locator ?? "").trim();
    if (!propLocator) {
      continue;
    }
    const path = locatorSegmentPath(propLocator);
    const matchesTarget =
      (path && segmentPathHasPrefix(path, targetSegments)) ||
      locatorMatchesTarget(propLocator, targetCanonical);
    if (!matchesTarget || seen.has(propId)) {
      continue;
    }
    seen.add(propId);
    matched.push(propId);
  }
  return matched;
}

function resolveContextualParagraphTarget(
  targetSegments: LocatorSegment[],
  options: {
    sourceRecordId: string;
    sourceFragments: SourceFragmentRow[];
    propositionById: Map<string, PropositionRow>;
    resolvedLocator: string;
  },
): Pick<
  ContextRequirementResolution,
  "resolved" | "resolutionMode" | "fragments" | "resolvedLocator"
> | null {
  const exactFragments = matchFragmentsBySegmentPath(
    options.sourceRecordId,
    targetSegments,
    options.sourceFragments,
  ).filter((fragment) => {
    const path = locatorSegmentPath(fragment.locator);
    return Boolean(path && isExactSegmentPathMatch(path, targetSegments));
  });
  const exactPropIds = matchPropositionsBySegmentPath(
    options.sourceRecordId,
    targetSegments,
    options.propositionById,
  ).filter((propId) => {
    const propLocator = options.propositionById.get(propId)?.fragment_locator ?? "";
    const path = locatorSegmentPath(String(propLocator));
    return Boolean(path && isExactSegmentPathMatch(path, targetSegments));
  });

  if (exactFragments.length === 1) {
    return {
      resolved: true,
      resolutionMode: "exact",
      fragments: exactFragments,
      resolvedLocator: options.resolvedLocator,
    };
  }

  const containerFragments = matchFragmentsBySegmentPath(
    options.sourceRecordId,
    targetSegments,
    options.sourceFragments,
  );
  const containerPropIds = matchPropositionsBySegmentPath(
    options.sourceRecordId,
    targetSegments,
    options.propositionById,
  );
  if (containerFragments.length === 0 && containerPropIds.length === 0) {
    return null;
  }

  const syntheticFragments = [...containerFragments];
  const existingLocators = new Set(syntheticFragments.map((fragment) => fragment.locator));
  for (const propId of containerPropIds) {
    const propLocator = String(options.propositionById.get(propId)?.fragment_locator ?? "").trim();
    if (propLocator && !existingLocators.has(propLocator)) {
      syntheticFragments.push({
        fragmentId: propId,
        locator: propLocator,
        excerpt: "",
      });
      existingLocators.add(propLocator);
    }
  }

  const mode: ContextRequirementResolution["resolutionMode"] =
    syntheticFragments.length > 1 ||
    syntheticFragments.some((fragment) => {
      const path = locatorSegmentPath(fragment.locator);
      return Boolean(path && segmentPathIsDescendant(path, targetSegments));
    })
      ? "container"
      : "exact";

  return {
    resolved: true,
    resolutionMode: mode,
    fragments: syntheticFragments,
    resolvedLocator: options.resolvedLocator,
  };
}

function matchBareParagraphFragmentsInSource(
  sourceRecordId: string,
  paragraphNum: string,
  paragraphSub: string | null | undefined,
  sourceFragments: SourceFragmentRow[],
): ResolvedContextFragment[] {
  const matches: ResolvedContextFragment[] = [];
  const seen = new Set<string>();
  for (const fragment of sourceFragments) {
    if (String(fragment.source_record_id ?? "").trim() !== sourceRecordId) {
      continue;
    }
    const fragmentLocator = String(fragment.locator ?? "").trim();
    const path = parseLocatorStructuralContext(fragmentLocator);
    const paragraph = path?.segments.find((segment) => segment.kind === "paragraph");
    const prefixSegment: LocatorSegment = {
      kind: "paragraph",
      num: paragraphNum.toLowerCase(),
      sub: paragraphSub?.toLowerCase() ?? null,
    };
    if (!paragraph || !segmentMatchesPrefix(paragraph, prefixSegment)) {
      continue;
    }
    const fragmentId = fragmentRowId(fragment);
    if (!fragmentId || seen.has(fragmentId)) {
      continue;
    }
    seen.add(fragmentId);
    matches.push({
      fragmentId,
      locator: fragmentLocator,
      excerpt: fragmentExcerpt(fragment),
    });
  }
  return matches;
}

function matchParentOnlyFragmentsInSource(
  sourceRecordId: string,
  parentLocator: string,
  sourceFragments: SourceFragmentRow[],
): ResolvedContextFragment[] {
  const parentPath = parseLocatorStructuralContext(parentLocator);
  if (!parentPath) {
    return matchFragmentsInSource(sourceRecordId, parentLocator, sourceFragments);
  }
  return matchFragmentsInSource(sourceRecordId, parentLocator, sourceFragments).filter(
    (fragment) => {
      const path = locatorSegmentPath(fragment.locator);
      return Boolean(path && path.length === parentPath.segments.length);
    },
  );
}

function matchFragmentsInSource(
  sourceRecordId: string,
  locator: string,
  sourceFragments: SourceFragmentRow[],
): ResolvedContextFragment[] {
  const matches: ResolvedContextFragment[] = [];
  const seen = new Set<string>();
  for (const fragment of sourceFragments) {
    if (String(fragment.source_record_id ?? "").trim() !== sourceRecordId) {
      continue;
    }
    const fragmentLocator = String(fragment.locator ?? "").trim();
    if (!fragmentLocator || !locatorMatchesTarget(fragmentLocator, locator)) {
      continue;
    }
    const fragmentId = fragmentRowId(fragment);
    if (!fragmentId || seen.has(fragmentId)) {
      continue;
    }
    seen.add(fragmentId);
    matches.push({
      fragmentId,
      locator: fragmentLocator,
      excerpt: fragmentExcerpt(fragment),
    });
  }
  return matches;
}

function resolveSingleLocatorTarget(
  targetLocator: string,
  options: {
    sourceRecordId: string | null;
    sourceFragments: SourceFragmentRow[];
    propositionById: Map<string, PropositionRow>;
    fragmentById: Map<string, SourceFragmentRow>;
  },
): {
  resolved: boolean;
  reason?: ContextRequirementReason;
  fragments: ResolvedContextFragment[];
} {
  const internalMatches =
    options.sourceRecordId && targetLocator.trim()
      ? matchFragmentsInSource(options.sourceRecordId, targetLocator, options.sourceFragments)
      : [];

  if (internalMatches.length === 1) {
    return { resolved: true, fragments: internalMatches };
  }
  if (internalMatches.length > 1) {
    return { resolved: false, reason: "ambiguous", fragments: internalMatches };
  }

  return { resolved: false, reason: "not found", fragments: [] };
}

function isExternalContextEntry(entry: {
  kind?: string;
  resolution_status?: string;
}): boolean {
  const status = String(entry.resolution_status ?? "").trim();
  if (status === "external_reference") {
    return true;
  }
  const kind = String(entry.kind ?? "").trim().toLowerCase();
  return kind.startsWith("external_");
}

function reasonFromExportStatus(status: string): ContextRequirementReason {
  if (status === "ambiguous") {
    return "ambiguous";
  }
  return "not found";
}

function isBareRelativeReference(locator: string): boolean {
  const parsed = parseLocatorReference(locator);
  if (!parsed) {
    return false;
  }
  if (parsed.kind === "range") {
    return true;
  }
  const segment = parsed.segments[0];
  if (!segment) {
    return false;
  }
  return segment.kind === "paragraph" || segment.kind === "sub-paragraph";
}

export function resolveContextRequirement(
  entry: NonNullable<LawStatementRow["required_context"]>[number],
  options: {
    sourceRecordId: string | null;
    structuralContext?: LocatorStructuralContext | null;
    sourceFragments: SourceFragmentRow[];
    propositionById: Map<string, PropositionRow>;
    fragmentById: Map<string, SourceFragmentRow>;
  },
): ContextRequirementResolution {
  const locator = String(entry.locator ?? "").trim() || "unknown locator";
  const exportResolutionStatus = String(entry.resolution_status ?? "").trim() || "unknown";
  const exportPropositionIds = (entry.proposition_ids ?? []).map((id) => String(id).trim()).filter(Boolean);
  const structuralContext = options.structuralContext ?? null;
  const inheritedContextLabel = formatInheritedContextLabel(structuralContext);

  // Typed relationship context already resolved by effective-law composition.
  if (isResolvedTypedContext(entry as RequiredContextEntry)) {
    const fragments = fragmentsForPropositionIds(
      exportPropositionIds,
      options.propositionById,
      options.fragmentById,
    );
    const canonical = String(
      (entry as RequiredContextEntry).target_canonical_locator ?? "",
    ).trim();
    return {
      locator,
      exportResolutionStatus: "resolved",
      resolved: true,
      resolutionMode: "exact",
      fragments,
      inheritedContextLabel:
        (entry as RequiredContextEntry).inherited_via_group && canonical
          ? `Resolved through local structure · ${canonical}`
          : "Resolved through local structure",
      resolvedLocator: canonical || undefined,
    };
  }

  // Typed entry with relationship but missing target — surface as unresolved warning, not ambiguity.
  if (
    isTypedContextKind((entry as RequiredContextEntry).kind) &&
    String((entry as RequiredContextEntry).relationship_id ?? "").trim() &&
    exportPropositionIds.length === 0
  ) {
    return {
      locator,
      exportResolutionStatus,
      resolved: false,
      reason: "not found",
      fragments: [],
      inheritedContextLabel: "Typed relationship target missing",
    };
  }

  if (isExternalContextEntry(entry)) {
    return {
      locator,
      exportResolutionStatus,
      resolved: false,
      reason: "external reference",
      fragments: [],
    };
  }

  const containerTargets = !isBareRelativeReference(locator)
    ? parseContainerLocatorTargets(locator)
    : null;
  if (containerTargets && options.sourceRecordId) {
    const containerResolution = resolveContainerLocatorTargets(containerTargets, {
      sourceRecordId: options.sourceRecordId,
      sourceFragments: options.sourceFragments,
    });
    if (containerResolution) {
      return {
        ...containerResolution,
        locator,
        exportResolutionStatus,
        inheritedContextLabel,
      };
    }
  }

  const directMatches =
    options.sourceRecordId && locator !== "unknown locator"
      ? matchFragmentsInSource(options.sourceRecordId, locator, options.sourceFragments)
      : [];

  if (directMatches.length === 1 && !isBareRelativeReference(locator)) {
    return {
      locator,
      exportResolutionStatus,
      resolved: true,
      resolutionMode: "exact",
      fragments: directMatches,
      inheritedContextLabel,
    };
  }
  if (directMatches.length > 1 && !isBareRelativeReference(locator)) {
    const fallbackContainerTargets = containerTargets ?? parseContainerLocatorTargets(locator);
    if (fallbackContainerTargets) {
      const containerResolution = resolveContainerLocatorTargets(fallbackContainerTargets, {
        sourceRecordId: options.sourceRecordId,
        sourceFragments: options.sourceFragments,
      });
      if (containerResolution?.resolved) {
        return {
          ...containerResolution,
          locator,
          exportResolutionStatus,
          inheritedContextLabel,
        };
      }
    }
    return {
      locator,
      exportResolutionStatus,
      resolved: false,
      reason: "ambiguous",
      fragments: directMatches,
      inheritedContextLabel,
    };
  }

  if (
    !isBareRelativeReference(locator) &&
    isExternalInstrumentLocator(locator) &&
    directMatches.length === 0
  ) {
    return {
      locator,
      exportResolutionStatus,
      resolved: false,
      reason: "external reference",
      fragments: [],
      inheritedContextLabel,
    };
  }

  if (!isBareRelativeReference(locator) && directMatches.length === 0) {
    const instrumentSubResolution = resolveInstrumentSubLocator(locator, {
      sourceRecordId: options.sourceRecordId,
      sourceFragments: options.sourceFragments,
      inheritedContextLabel,
      exportResolutionStatus,
    });
    if (instrumentSubResolution) {
      return instrumentSubResolution;
    }
  }

  const parsed = parseLocatorReference(locator);
  const shouldApplyContext =
    structuralContext &&
    structuralContext.segments.length > 0 &&
    (isBareRelativeReference(locator) || parsed?.kind === "range");

  if (shouldApplyContext) {
    const contextualised = parsed
      ? applyStructuralContextToReference(structuralContext, parsed)
      : null;
    const expanded = contextualised ? expandParsedLocatorReference(contextualised) : [];
    const targetLocators =
      expanded.length > 0
        ? expanded.map((entryRef) => buildCanonicalLocator(entryRef.segments))
        : resolveLocatorTargets(locator, structuralContext);

    if (targetLocators.length > 1) {
      const children: ResolvedLocatorChild[] = targetLocators.map((targetLocator) => {
        const childResolution = resolveSingleLocatorTarget(targetLocator, options);
        return {
          locator: targetLocator,
          resolved: childResolution.resolved,
          reason: childResolution.reason,
          fragments: childResolution.fragments,
        };
      });
      const resolvedChildren = children.filter((child) => child.resolved);
      const ambiguousChildren = children.filter((child) => child.reason === "ambiguous");
      const allResolved = children.length > 0 && resolvedChildren.length === children.length;
      const fragments = resolvedChildren.flatMap((child) => child.fragments);
      return {
        locator,
        exportResolutionStatus,
        resolved: allResolved,
        reason: allResolved
          ? undefined
          : ambiguousChildren.length > 0
            ? "ambiguous"
            : "not found",
        fragments,
        inheritedContextLabel,
        resolvedLocator: targetLocators.join(", "),
        children,
      };
    }

    const resolvedLocator = targetLocators[0] ?? locator;
    const targetSegments =
      expanded[0]?.segments ??
      parseLocatorStructuralContext(resolvedLocator)?.segments ??
      [];
    if (targetSegments.length > 0 && options.sourceRecordId) {
      const contextualResolution = resolveContextualParagraphTarget(targetSegments, {
        sourceRecordId: options.sourceRecordId,
        sourceFragments: options.sourceFragments,
        propositionById: options.propositionById,
        resolvedLocator,
      });
      if (contextualResolution) {
        return {
          locator,
          exportResolutionStatus,
          inheritedContextLabel,
          ...contextualResolution,
        };
      }
    }

    const contextualMatches =
      options.sourceRecordId && resolvedLocator
        ? matchFragmentsInSource(options.sourceRecordId, resolvedLocator, options.sourceFragments)
        : [];

    if (contextualMatches.length === 1) {
      return {
        locator,
        exportResolutionStatus,
        resolved: true,
        fragments: contextualMatches,
        inheritedContextLabel,
        resolvedLocator,
      };
    }
    if (contextualMatches.length > 1) {
      return {
        locator,
        exportResolutionStatus,
        resolved: true,
        resolutionMode: "container",
        fragments: contextualMatches,
        inheritedContextLabel,
        resolvedLocator,
      };
    }
  }

  if (!shouldApplyContext) {
    const bareReference = parseLocatorReference(locator);
    const bareParagraph =
      bareReference?.kind === "single" && bareReference.segments[0]?.kind === "paragraph"
        ? bareReference.segments[0]
        : null;
    if (bareParagraph && options.sourceRecordId) {
      const bareMatches = matchBareParagraphFragmentsInSource(
        options.sourceRecordId,
        bareParagraph.num,
        bareParagraph.sub,
        options.sourceFragments,
      );
      if (bareMatches.length === 1) {
        return {
          locator,
          exportResolutionStatus,
          resolved: true,
          fragments: bareMatches,
        };
      }
      if (bareMatches.length > 1) {
        return {
          locator,
          exportResolutionStatus,
          resolved: false,
          reason: "ambiguous",
          fragments: bareMatches,
        };
      }
    }
  }

  const exportFragments = fragmentsForPropositionIds(
    exportPropositionIds,
    options.propositionById,
    options.fragmentById,
  );
  if (exportFragments.length > 0) {
    return {
      locator,
      exportResolutionStatus,
      resolved: true,
      fragments: exportFragments,
      inheritedContextLabel,
    };
  }

  if (exportResolutionStatus === "resolved") {
    return {
      locator,
      exportResolutionStatus,
      resolved: false,
      reason: "not found",
      fragments: [],
      inheritedContextLabel,
      resolvedLocator: shouldApplyContext ? resolveLocatorTargets(locator, structuralContext)[0] : undefined,
    };
  }

  return {
    locator,
    exportResolutionStatus,
    resolved: false,
    reason: reasonFromExportStatus(exportResolutionStatus),
    fragments: [],
    inheritedContextLabel,
  };
}

export function primarySourceRecordIdForStatement(
  statement: LawStatementRow,
  propositionById: Map<string, PropositionRow>,
): string | null {
  for (const propositionId of statement.source_proposition_ids ?? []) {
    const sourceRecordId = propositionById.get(propositionId)?.source_record_id?.trim();
    if (sourceRecordId) {
      return sourceRecordId;
    }
  }
  for (const propositionId of statement.supporting_proposition_ids ?? []) {
    const sourceRecordId = propositionById.get(propositionId)?.source_record_id?.trim();
    if (sourceRecordId) {
      return sourceRecordId;
    }
  }
  return null;
}

export function primaryFragmentLocatorForStatement(
  statement: LawStatementRow,
  propositionById: Map<string, PropositionRow>,
  fragmentById: Map<string, SourceFragmentRow>,
): string | null {
  for (const propositionId of statement.source_proposition_ids ?? []) {
    const proposition = propositionById.get(propositionId);
    const fragmentLocator = proposition?.fragment_locator?.trim();
    if (fragmentLocator) {
      return fragmentLocator;
    }
    const fragmentId = proposition?.source_fragment_id?.trim();
    if (fragmentId) {
      const fragmentLocatorFromRow = fragmentById.get(fragmentId)?.locator?.trim();
      if (fragmentLocatorFromRow) {
        return fragmentLocatorFromRow;
      }
    }
  }
  return null;
}

export function buildLocatorResolutionReport(input: {
  locator: string;
  statement: LawStatementRow;
  sourceFragments: SourceFragmentRow[];
  propositionById: Map<string, PropositionRow>;
  fragmentById: Map<string, SourceFragmentRow>;
}): LocatorResolutionReport {
  const sourceRecordId = primarySourceRecordIdForStatement(input.statement, input.propositionById);
  const primaryLocator = primaryFragmentLocatorForStatement(
    input.statement,
    input.propositionById,
    input.fragmentById,
  );
  const parsedStructuralContext = primaryLocator
    ? parseLocatorStructuralContext(primaryLocator)
    : null;
  const structuralContext = primaryLocator
    ? {
        sourceRecordId,
        segments: parsedStructuralContext?.segments ?? [],
      }
    : sourceRecordId
      ? { sourceRecordId, segments: [] as LocatorSegment[] }
      : null;

  const resolution = resolveContextRequirement(
    {
      locator: input.locator,
      resolution_status: "unresolved",
      proposition_ids: [],
    },
    {
      sourceRecordId,
      structuralContext,
      sourceFragments: input.sourceFragments,
      propositionById: input.propositionById,
      fragmentById: input.fragmentById,
    },
  );

  return {
    locator: input.locator,
    primarySourceRecordId: sourceRecordId,
    parsedLocator: parseLocatorReference(input.locator),
    structuralContext,
    candidateFragmentLocators: listCandidateFragmentLocators(
      sourceRecordId,
      input.locator,
      input.sourceFragments,
    ),
    outcome: {
      exportResolutionStatus: resolution.exportResolutionStatus,
      resolved: resolution.resolved,
      reason: resolution.reason,
      resolutionMode: resolution.resolutionMode,
      resolvedLocator: resolution.resolvedLocator,
      unresolvedChild: resolution.unresolvedChild,
      matchedFragmentIds: resolution.fragments.map((fragment) => fragment.fragmentId),
    },
  };
}

export function buildContextRequirementResolutions(
  statement: LawStatementRow,
  options: {
    sourceFragments: SourceFragmentRow[];
    propositionById: Map<string, PropositionRow>;
    fragmentById: Map<string, SourceFragmentRow>;
  },
): ContextRequirementResolution[] {
  const requiredContext = statement.required_context ?? [];
  if (requiredContext.length === 0) {
    return [];
  }
  const sourceRecordId = primarySourceRecordIdForStatement(statement, options.propositionById);
  const primaryLocator = primaryFragmentLocatorForStatement(
    statement,
    options.propositionById,
    options.fragmentById,
  );
  const parsedStructuralContext = primaryLocator
    ? parseLocatorStructuralContext(primaryLocator)
    : null;
  const structuralContext = primaryLocator
    ? {
        sourceRecordId,
        segments: parsedStructuralContext?.segments ?? [],
      }
    : sourceRecordId
      ? { sourceRecordId, segments: [] as LocatorSegment[] }
      : null;

  return requiredContext.map((entry) =>
    resolveContextRequirement(entry, {
      sourceRecordId,
      structuralContext,
      sourceFragments: options.sourceFragments,
      propositionById: options.propositionById,
      fragmentById: options.fragmentById,
    }),
  );
}
