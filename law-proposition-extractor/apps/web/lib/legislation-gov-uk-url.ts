/**
 * Build legislation.gov.uk HTML deep-links from Law Proposition Extractor source_url + fragment locators.
 *
 * source_url is usually the XML endpoint (`…/data.xml`); we strip that and append a
 * provision path derived from canonical (`article:10:paragraph:1`) or free-text
 * (`Article 10(1)`, `regulation 4(1)`) locators.
 */

const LEGISLATION_HOST = /(^|\.)legislation\.gov\.uk$/i;

const PROVISION_TYPES = new Set([
  "article",
  "section",
  "regulation",
  "schedule",
  "annex",
  "part",
  "chapter",
]);

const XML_TAIL_RE = /\/(?:data\.(?:xml|xht|htm|html)|contents\/data\.(?:xml|xht))$/i;

export function legislationDocumentBaseUrl(sourceUrl: string | null | undefined): string | null {
  const raw = String(sourceUrl ?? "").trim();
  if (!raw) {
    return null;
  }
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    return null;
  }
  if (!LEGISLATION_HOST.test(parsed.hostname)) {
    return null;
  }
  let path = parsed.pathname.replace(XML_TAIL_RE, "");
  path = path.replace(/\/+$/, "");
  if (!path || path === "/") {
    return null;
  }
  return `${parsed.origin}${path}`;
}

function normalizeAnnexId(value: string): string {
  const trimmed = value.trim();
  if (/^[ivxlcdm]+$/i.test(trimmed)) {
    return trimmed.toUpperCase();
  }
  return trimmed;
}

function normalizeProvisionId(type: string, value: string): string {
  if (type === "annex") {
    return normalizeAnnexId(value);
  }
  return value.trim();
}

type ProvisionRef = {
  type: string;
  id: string;
  paragraph?: string;
};

export type LegislationContextCrumb = {
  label: string;
  href: string | null;
};

function provisionFromCanonicalLocator(locator: string): ProvisionRef | null {
  const parts = locator
    .trim()
    .toLowerCase()
    .split(":")
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length < 2) {
    return null;
  }

  let type: string | null = null;
  let id: string | null = null;
  let paragraph: string | undefined;

  for (let i = 0; i < parts.length - 1; i += 1) {
    const key = parts[i]!;
    const value = parts[i + 1]!;
    if (key === "list" || key === "fragment") {
      break;
    }
    if (PROVISION_TYPES.has(key) && type === null) {
      type = key;
      id = value;
      i += 1;
      continue;
    }
    if (key === "paragraph" && type !== null) {
      paragraph = value;
      break;
    }
  }

  if (!type || !id) {
    return null;
  }
  return { type, id: normalizeProvisionId(type, id), paragraph };
}

function provisionFromFreeTextLocator(locator: string): ProvisionRef | null {
  const text = locator.trim();
  if (!text) {
    return null;
  }

  const articleLike =
    /^(article|section|regulation|reg\.?|schedule|annex|part|chapter)\s+([0-9]+[a-z]?|[ivxlcdm]+)\b/i.exec(
      text,
    );
  if (!articleLike) {
    return null;
  }

  let type = articleLike[1]!.toLowerCase().replace(/\.$/, "");
  if (type === "reg") {
    type = "regulation";
  }
  const id = normalizeProvisionId(type, articleLike[2]!);

  const after = text.slice(articleLike[0].length);
  const para = /^\s*\(\s*([0-9]+[a-z]?)\s*\)/i.exec(after);
  const paraWord = /^\s*,?\s*paragraph\s+([0-9]+[a-z]?)\b/i.exec(after);

  return {
    type,
    id,
    paragraph: para?.[1] ?? paraWord?.[1],
  };
}

export function provisionRefFromLocator(locator: string | null | undefined): ProvisionRef | null {
  const raw = String(locator ?? "").trim();
  if (!raw || raw.toLowerCase() === "document:full") {
    return null;
  }
  if (raw.includes(":")) {
    return provisionFromCanonicalLocator(raw) ?? provisionFromFreeTextLocator(raw);
  }
  return provisionFromFreeTextLocator(raw);
}

export function provisionPathFromLocator(locator: string | null | undefined): string | null {
  const ref = provisionRefFromLocator(locator);
  if (!ref) {
    return null;
  }

  const base = `/${ref.type}/${encodeURIComponent(ref.id)}`;
  if (!ref.paragraph) {
    return base;
  }

  // Schedules use an explicit /paragraph/ segment; articles/regs/sections use /N/M.
  if (ref.type === "schedule") {
    return `${base}/paragraph/${encodeURIComponent(ref.paragraph)}`;
  }
  return `${base}/${encodeURIComponent(ref.paragraph)}`;
}

/**
 * Deep-link to the underlying provision on legislation.gov.uk.
 * Falls back to the instrument root when the locator cannot be mapped.
 */
export function legislationProvisionUrl(
  sourceUrl: string | null | undefined,
  locator: string | null | undefined,
): string | null {
  const base = legislationDocumentBaseUrl(sourceUrl);
  if (!base) {
    return null;
  }
  const path = provisionPathFromLocator(locator);
  return path ? `${base}${path}` : base;
}

function titleCaseProvisionType(type: string): string {
  if (!type) {
    return type;
  }
  return type.charAt(0).toUpperCase() + type.slice(1);
}

function provisionPathForRef(ref: ProvisionRef, includeParagraph: boolean): string {
  const base = `/${ref.type}/${encodeURIComponent(ref.id)}`;
  if (!includeParagraph || !ref.paragraph) {
    return base;
  }
  if (ref.type === "schedule") {
    return `${base}/paragraph/${encodeURIComponent(ref.paragraph)}`;
  }
  return `${base}/${encodeURIComponent(ref.paragraph)}`;
}

/**
 * Hierarchical crumbs: instrument → article/section/… → paragraph.
 * Each crumb links to legislation.gov.uk when `sourceUrl` is a legis URL.
 */
export function legislationContextCrumbs(input: {
  sourceUrl?: string | null;
  instrumentLabel?: string | null;
  locator?: string | null;
}): LegislationContextCrumb[] {
  const base = legislationDocumentBaseUrl(input.sourceUrl);
  const instrumentLabel = String(input.instrumentLabel ?? "").trim() || "Legislation";
  const crumbs: LegislationContextCrumb[] = [
    {
      label: instrumentLabel,
      href: base,
    },
  ];

  const ref = provisionRefFromLocator(input.locator);
  if (!ref) {
    return crumbs;
  }

  crumbs.push({
    label: `${titleCaseProvisionType(ref.type)} ${ref.id}`,
    href: base ? `${base}${provisionPathForRef(ref, false)}` : null,
  });

  if (ref.paragraph) {
    crumbs.push({
      label: `Paragraph ${ref.paragraph}`,
      href: base ? `${base}${provisionPathForRef(ref, true)}` : null,
    });
  }

  return crumbs;
}
