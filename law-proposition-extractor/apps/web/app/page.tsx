"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type SourceItem = {
  id: string;
  title: string;
  jurisdiction?: string;
  citation?: string;
  url?: string;
};

type PropositionItem = {
  id: string;
  text: string;
  articleReference?: string;
  legalSubject?: string;
  action?: string;
  sourceRecordId?: string;
  /** Human-readable title; durable identity remains `id` (ADR-0018). */
  label?: string;
  shortName?: string;
  /** Routing-only; not durable identity. */
  slug?: string;
  propositionKey?: string;
};

type DivergenceAssessmentItem = {
  id: string;
  divergenceType: string;
  propositionId: string;
  comparatorPropositionId: string;
  jurisdictions: string[];
  confidence: string;
  reviewStatus: string;
  rationale: string;
  operationalImpact: string;
  sourcesChecked: string[];
};

type DemoData = {
  topic: string;
  sources: SourceItem[];
  propositions: PropositionItem[];
  divergenceAssessments: DivergenceAssessmentItem[];
  narrative: string;
};

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_LAW_PROPOSITION_EXTRACTOR_API_BASE_URL ?? "http://127.0.0.1:8010"
).replace(/\/+$/, "");
const DEMO_ENDPOINT = `${API_BASE_URL}/demo`;
const DEMO_CASE_OPTIONS = ["example", "realistic"] as const;
type DemoCaseName = (typeof DEMO_CASE_OPTIONS)[number];
const META_CHIP_CLASS =
  "rounded border border-border/70 bg-muted/80 px-2 py-0.5 font-mono text-[11px] leading-5 text-foreground/85";

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function toText(value: unknown, fallback = "—"): string {
  if (typeof value === "string") {
    return value.trim() || fallback;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  if (Array.isArray(value)) {
    const joined = value
      .map((item) => toText(item, ""))
      .filter(Boolean)
      .join(", ");
    return joined || fallback;
  }

  const obj = asRecord(value);
  if (obj) {
    const preferred = obj.text ?? obj.title ?? obj.name ?? obj.description ?? obj.summary;
    if (preferred !== undefined) {
      return toText(preferred, fallback);
    }

    try {
      return JSON.stringify(obj);
    } catch {
      return fallback;
    }
  }

  return fallback;
}

function normalizeTopic(raw: Record<string, unknown>): string {
  return toText(raw.topic ?? raw.title ?? raw.subject, "No topic provided");
}

function normalizeSources(raw: Record<string, unknown>): SourceItem[] {
  const sourcesRaw = raw.sources;
  if (!Array.isArray(sourcesRaw)) {
    return [];
  }

  return sourcesRaw.map((item, index) => {
    const source = asRecord(item);
    const id = toText(source?.id ?? source?.source_id ?? index + 1, `${index + 1}`);
    return {
      id,
      title: toText(source?.title ?? source?.name ?? source?.summary, "Untitled source"),
      jurisdiction: toText(source?.jurisdiction, "").trim() || undefined,
      citation:
        toText(source?.citation ?? source?.ref ?? source?.reference, "").trim() || undefined,
      url: toText(source?.url ?? source?.link, "").trim() || undefined,
    };
  });
}

function normalizePropositions(raw: Record<string, unknown>): PropositionItem[] {
  const resolved = [raw.propositions].find((value) => Array.isArray(value));
  if (!Array.isArray(resolved)) {
    return [];
  }

  return resolved.map((item, index) => {
    const row = asRecord(item) ?? {};
    // Deprecated migration shim: read legacy payloads exported before source_record_id rename.
    const sourceRecordId = row.source_record_id ?? row.source_document_id ?? row.source_id;
    return {
      id: toText(row.id ?? row.proposition_id ?? row.assessment_id ?? index + 1, `${index + 1}`),
      text: toText(row.proposition_text ?? row.text ?? item, "No proposition text"),
      articleReference:
        toText(row.article_reference ?? row.reference ?? row.article, "").trim() || undefined,
      legalSubject: toText(row.legal_subject ?? row.subject, "").trim() || undefined,
      action: toText(row.action, "").trim() || undefined,
      sourceRecordId: toText(sourceRecordId, "").trim() || undefined,
      label: toText(row.label, "").trim() || undefined,
      shortName: toText(row.short_name ?? row.shortName, "").trim() || undefined,
      slug: toText(row.slug, "").trim() || undefined,
      propositionKey: toText(row.proposition_key ?? row.propositionKey, "").trim() || undefined,
    };
  });
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => toText(item, ""))
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeDivergenceAssessments(raw: Record<string, unknown>): DivergenceAssessmentItem[] {
  const aliases = ["divergence_assessments", "divergenceAssessments", "assessments"];
  const resolved = aliases.map((alias) => raw[alias]).find((value) => Array.isArray(value));
  if (!Array.isArray(resolved)) {
    return [];
  }

  return resolved.map((item, index) => {
    const row = asRecord(item) ?? {};
    const jurisdictionA = toText(row.jurisdiction_a ?? row.jurisdictionA, "").trim();
    const jurisdictionB = toText(row.jurisdiction_b ?? row.jurisdictionB, "").trim();
    const providedJurisdictions = toStringArray(row.jurisdictions);
    const jurisdictions =
      providedJurisdictions.length > 0
        ? providedJurisdictions
        : [jurisdictionA, jurisdictionB].filter(Boolean);

    return {
      id: toText(row.id ?? row.assessment_id ?? index + 1, `${index + 1}`),
      divergenceType: toText(row.divergence_type ?? row.divergenceType, "unknown"),
      propositionId: toText(
        row.proposition_id ?? row.propositionId ?? row.primary_proposition_id,
        "—"
      ),
      comparatorPropositionId: toText(
        row.comparator_proposition_id ??
          row.comparatorPropositionId ??
          row.secondary_proposition_id,
        "—"
      ),
      jurisdictions,
      confidence: toText(row.confidence, "—"),
      reviewStatus: toText(row.review_status ?? row.reviewStatus, "—"),
      rationale: toText(row.rationale, "No rationale provided"),
      operationalImpact: toText(
        row.operational_impact ?? row.operationalImpact,
        "No operational impact provided"
      ),
      sourcesChecked: toStringArray(row.sources_checked ?? row.sourcesChecked),
    };
  });
}

function normalizeNarrative(raw: Record<string, unknown>): string {
  return toText(raw.narrative ?? raw.summary ?? raw.synthesis, "No narrative provided");
}

function normalizeDemoData(input: unknown): DemoData {
  const raw = asRecord(input) ?? {};
  return {
    topic: normalizeTopic(raw),
    sources: normalizeSources(raw),
    propositions: normalizePropositions(raw),
    divergenceAssessments: normalizeDivergenceAssessments(raw),
    narrative: normalizeNarrative(raw),
  };
}

function formatDivergenceTypeLabel(rawDivergenceType: string): string {
  const normalized = rawDivergenceType.trim();
  if (!normalized) {
    return "Unknown";
  }

  return normalized
    .split("_")
    .map((segment) => segment.trim())
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" / ");
}

function EmptyState({ message }: { message: string }): JSX.Element {
  return <p className="text-sm text-muted-foreground">{message}</p>;
}

function LoadingCard({ title }: { title: string }): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          <div className="h-4 w-4/5 animate-pulse rounded bg-muted" />
          <div className="h-4 w-2/3 animate-pulse rounded bg-muted" />
          <div className="h-4 w-3/4 animate-pulse rounded bg-muted" />
        </div>
      </CardContent>
    </Card>
  );
}

export default function HomePage(): JSX.Element {
  const [selectedCaseName, setSelectedCaseName] = useState<DemoCaseName>(DEMO_CASE_OPTIONS[0]);
  const [data, setData] = useState<DemoData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<string | null>(null);
  const demoEndpointForCase = useMemo(
    () => `${DEMO_ENDPOINT}?case_name=${encodeURIComponent(selectedCaseName)}`,
    [selectedCaseName]
  );

  useEffect(() => {
    const controller = new AbortController();

    const load = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch(demoEndpointForCase, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });

        if (!response.ok) {
          throw new Error(`Request failed (${response.status})`);
        }

        const payload: unknown = await response.json();
        const normalized = normalizeDemoData(payload);
        setData(normalized);
        setSelectedAssessmentId(normalized.divergenceAssessments[0]?.id ?? null);
      } catch (loadError) {
        if (controller.signal.aborted) {
          return;
        }
        const message = loadError instanceof Error ? loadError.message : "Unknown fetch error";
        setError(message);
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    };

    void load();

    return () => {
      controller.abort();
    };
  }, [demoEndpointForCase]);

  const selectedAssessment = useMemo(() => {
    if (!data || !selectedAssessmentId) {
      return null;
    }
    return data.divergenceAssessments.find((item) => item.id === selectedAssessmentId) ?? null;
  }, [data, selectedAssessmentId]);

  const linkedPropositionIds = useMemo(() => {
    if (!selectedAssessment) {
      return new Set<string>();
    }
    return new Set(
      [selectedAssessment.propositionId, selectedAssessment.comparatorPropositionId].filter(Boolean)
    );
  }, [selectedAssessment]);

  const linkedPropositions = useMemo(() => {
    if (!data || !selectedAssessment) {
      return [];
    }
    return data.propositions.filter((item) => linkedPropositionIds.has(item.id));
  }, [data, linkedPropositionIds, selectedAssessment]);

  const linkedPrimaryProposition = useMemo(() => {
    if (!selectedAssessment) {
      return null;
    }
    return linkedPropositions.find((item) => item.id === selectedAssessment.propositionId) ?? null;
  }, [linkedPropositions, selectedAssessment]);

  const linkedComparatorProposition = useMemo(() => {
    if (!selectedAssessment) {
      return null;
    }
    return (
      linkedPropositions.find((item) => item.id === selectedAssessment.comparatorPropositionId) ??
      null
    );
  }, [linkedPropositions, selectedAssessment]);

  const linkedSourceIds = useMemo(() => {
    if (!selectedAssessment) {
      return new Set<string>();
    }
    return new Set(selectedAssessment.sourcesChecked.map((item) => item.trim()).filter(Boolean));
  }, [selectedAssessment]);

  const linkedSources = useMemo(() => {
    if (!data || !selectedAssessment) {
      return [];
    }

    const byId = data.sources.filter((source) => linkedSourceIds.has(source.id));
    if (byId.length > 0) {
      return byId;
    }

    return data.sources.filter((source) => {
      const citation = source.citation?.trim();
      return citation ? linkedSourceIds.has(citation) : false;
    });
  }, [data, linkedSourceIds, selectedAssessment]);

  const sectionTitles = useMemo(
    () => ["Topic", "Sources", "Propositions", "Divergence assessments", "Narrative"],
    []
  );

  return (
    <main className="mx-auto min-h-screen w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-6 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-3xl font-semibold tracking-tight">Analysis workbench</h1>
          <div className="flex items-center gap-2">
            <span className="rounded border border-priguidance-discovery/70 bg-priguidance-discovery/[0.12] px-2 py-1 text-[11px] font-medium text-primary">
              Analysis
            </span>
            <Link
              href="/propositions"
              className="rounded border border-border/80 bg-background px-2 py-1 text-[11px] font-medium text-foreground/80 hover:bg-accent/50"
            >
              Propositions
            </Link>
            <Link
              href="/statements"
              className="rounded border border-border/80 bg-background px-2 py-1 text-[11px] font-medium text-foreground/80 hover:bg-accent/50"
            >
              Review workbench
            </Link>
            <Link
              href="/review-analysis"
              className="rounded border border-border/80 bg-background px-2 py-1 text-[11px] font-medium text-foreground/80 hover:bg-accent/50"
            >
              Review analysis
            </Link>
            <Link
              href="/ops"
              className="rounded border border-border/80 bg-background px-2 py-1 text-[11px] font-medium text-foreground/80 hover:bg-accent/50"
            >
              Operations / Registry
            </Link>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border/70 bg-muted/20 px-3 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <label
              htmlFor="demo-case-select"
              className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground"
            >
              Demo case
            </label>
            <select
              id="demo-case-select"
              value={selectedCaseName}
              onChange={(event) => setSelectedCaseName(event.target.value as DemoCaseName)}
              className="h-7 rounded border border-border/80 bg-background px-2 font-mono text-[11px] text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-priguidance-discovery/30"
            >
              {DEMO_CASE_OPTIONS.map((caseName) => (
                <option key={caseName} value={caseName}>
                  {caseName}
                </option>
              ))}
            </select>
          </div>
          <p className="truncate text-[11px] text-muted-foreground/70">
            Read-only demo view powered by{" "}
            <code className="font-mono text-[11px] text-muted-foreground/70">
              {demoEndpointForCase}
            </code>
          </p>
        </div>
        <p className="text-xs text-muted-foreground/70">
          Assessments are selectable; all data remains read-only.
        </p>
      </header>

      {isLoading ? (
        <section className="grid gap-4 md:grid-cols-2">
          {sectionTitles.map((title) => (
            <LoadingCard key={title} title={title} />
          ))}
        </section>
      ) : null}

      {!isLoading && error ? (
        <Card className="border-destructive/35">
          <CardHeader>
            <CardTitle className="text-lg text-destructive">Could not load demo data</CardTitle>
            <CardDescription>Check the local API and try again.</CardDescription>
          </CardHeader>
          <CardContent>
            <code className="font-mono text-sm text-destructive">{error}</code>
          </CardContent>
        </Card>
      ) : null}

      {!isLoading && !error && data ? (
        <section className="grid gap-4 md:grid-cols-2">
          <Card className="md:col-span-2">
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Divergence assessments</CardTitle>
              <CardDescription>Select an item to view full details.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {data.divergenceAssessments.length === 0 ? (
                <EmptyState message="No divergence assessments found in this payload." />
              ) : (
                data.divergenceAssessments.map((item) => (
                  <button
                    key={`${item.id}-${item.propositionId}-${item.comparatorPropositionId}`}
                    type="button"
                    onClick={() => setSelectedAssessmentId(item.id)}
                    className={`w-full rounded-md border p-2.5 text-left transition-all hover:bg-accent/60 ${
                      selectedAssessmentId === item.id
                        ? "border-primary bg-priguidance-discovery/[0.1] ring-2 ring-priguidance-discovery/30 shadow-sm"
                        : "border-border/90 bg-background"
                    }`}
                  >
                    <p className="mb-1.5 flex flex-wrap items-center gap-1.5 text-xs text-foreground/70">
                      <span className={META_CHIP_CLASS}>id: {item.id}</span>
                      <span className={META_CHIP_CLASS}>
                        type: {formatDivergenceTypeLabel(item.divergenceType)}
                      </span>
                    </p>
                    <p className="text-sm leading-relaxed">
                      {item.propositionId} vs {item.comparatorPropositionId}
                    </p>
                  </button>
                ))
              )}
            </CardContent>
          </Card>

          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle className="text-lg">Divergence detail</CardTitle>
              <CardDescription>Read-only details from the selected assessment.</CardDescription>
            </CardHeader>
            <CardContent>
              {selectedAssessment ? (
                <div className="space-y-3">
                  <div className="grid gap-2.5 sm:grid-cols-2">
                    <div className="rounded-md bg-muted/40 p-2.5">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">
                        Divergence type
                      </p>
                      <p className="mt-1 text-sm">
                        {formatDivergenceTypeLabel(selectedAssessment.divergenceType)}
                      </p>
                      <p className="mt-0.5 font-mono text-[11px] text-muted-foreground/80">
                        raw: {selectedAssessment.divergenceType}
                      </p>
                    </div>
                    <div className="rounded-md bg-muted/40 p-2.5">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">
                        Confidence
                      </p>
                      <p className="mt-1 font-mono text-sm">{selectedAssessment.confidence}</p>
                    </div>
                    <div className="rounded-md bg-muted/40 p-2.5">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">
                        Proposition ID
                      </p>
                      <p className="mt-1 font-mono text-sm">{selectedAssessment.propositionId}</p>
                    </div>
                    <div className="rounded-md bg-muted/40 p-2.5">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">
                        Comparator proposition ID
                      </p>
                      <p className="mt-1 font-mono text-sm">
                        {selectedAssessment.comparatorPropositionId}
                      </p>
                    </div>
                    <div className="rounded-md bg-muted/40 p-2.5">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">
                        Jurisdictions
                      </p>
                      <p className="mt-1 text-sm">
                        {selectedAssessment.jurisdictions.length > 0
                          ? selectedAssessment.jurisdictions.join(", ")
                          : "—"}
                      </p>
                    </div>
                    <div className="rounded-md bg-muted/40 p-2.5">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">
                        Review status
                      </p>
                      <p className="mt-1 font-mono text-sm">{selectedAssessment.reviewStatus}</p>
                    </div>
                  </div>

                  <div className="rounded-md bg-muted/30 p-3">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                      Rationale
                    </p>
                    <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">
                      {selectedAssessment.rationale}
                    </p>
                  </div>

                  <div className="rounded-md bg-muted/30 p-3">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                      Operational impact
                    </p>
                    <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">
                      {selectedAssessment.operationalImpact}
                    </p>
                  </div>

                  <div className="rounded-md bg-muted/30 p-3">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                      Sources checked
                    </p>
                    {selectedAssessment.sourcesChecked.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {selectedAssessment.sourcesChecked.map((sourceId) => (
                          <span key={sourceId} className={META_CHIP_CLASS}>
                            {sourceId}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-1 text-sm">No sources listed.</p>
                    )}
                  </div>

                  <div className="rounded-md bg-muted/25 p-3">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                      Linked context
                    </p>

                    <div className="mt-2.5 grid gap-2.5 sm:grid-cols-2">
                      <div className="rounded-md border border-border/70 bg-background/70 p-2.5">
                        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                          Proposition
                        </p>
                        {linkedPrimaryProposition ? (
                          <div className="mt-1.5 space-y-1.5">
                            <p className="text-sm leading-relaxed">
                              {linkedPrimaryProposition.text}
                            </p>
                            <div className="flex flex-wrap gap-1.5 text-xs text-foreground/70">
                              <span className={META_CHIP_CLASS}>
                                id: {linkedPrimaryProposition.id}
                              </span>
                              {linkedPrimaryProposition.articleReference ? (
                                <span className={META_CHIP_CLASS}>
                                  article: {linkedPrimaryProposition.articleReference}
                                </span>
                              ) : null}
                              {linkedPrimaryProposition.legalSubject ? (
                                <span className={META_CHIP_CLASS}>
                                  subject: {linkedPrimaryProposition.legalSubject}
                                </span>
                              ) : null}
                              {linkedPrimaryProposition.action ? (
                                <span className={META_CHIP_CLASS}>
                                  action: {linkedPrimaryProposition.action}
                                </span>
                              ) : null}
                            </div>
                          </div>
                        ) : (
                          <p className="mt-2 text-sm text-muted-foreground">
                            Linked proposition not found.
                          </p>
                        )}
                      </div>

                      <div className="rounded-md border border-border/70 bg-background/70 p-2.5">
                        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                          Comparator proposition
                        </p>
                        {linkedComparatorProposition ? (
                          <div className="mt-1.5 space-y-1.5">
                            <p className="text-sm leading-relaxed">
                              {linkedComparatorProposition.text}
                            </p>
                            <div className="flex flex-wrap gap-1.5 text-xs text-foreground/70">
                              <span className={META_CHIP_CLASS}>
                                id: {linkedComparatorProposition.id}
                              </span>
                              {linkedComparatorProposition.articleReference ? (
                                <span className={META_CHIP_CLASS}>
                                  article: {linkedComparatorProposition.articleReference}
                                </span>
                              ) : null}
                              {linkedComparatorProposition.legalSubject ? (
                                <span className={META_CHIP_CLASS}>
                                  subject: {linkedComparatorProposition.legalSubject}
                                </span>
                              ) : null}
                              {linkedComparatorProposition.action ? (
                                <span className={META_CHIP_CLASS}>
                                  action: {linkedComparatorProposition.action}
                                </span>
                              ) : null}
                            </div>
                          </div>
                        ) : (
                          <p className="mt-2 text-sm text-muted-foreground">
                            Linked comparator proposition not found.
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="mt-2.5 rounded-md border border-border/70 bg-background/70 p-2.5">
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Sources checked
                      </p>
                      {linkedSources.length > 0 ? (
                        <div className="mt-1.5 space-y-1.5">
                          {linkedSources.map((source) => (
                            <div
                              key={`linked-source-${source.id}`}
                              className="rounded-md bg-muted/50 p-2"
                            >
                              <p className="text-sm font-medium">{source.title}</p>
                              <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-foreground/70">
                                <span className={META_CHIP_CLASS}>id: {source.id}</span>
                                <span className={META_CHIP_CLASS}>
                                  jurisdiction: {source.jurisdiction ?? "—"}
                                </span>
                                <span className={META_CHIP_CLASS}>
                                  citation: {source.citation ?? "—"}
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="mt-2 text-sm text-muted-foreground">
                          No source records could be resolved from <code>sources_checked</code>.
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <EmptyState message="Select a divergence assessment to view details." />
              )}
            </CardContent>
          </Card>

          <div className="md:col-span-2 mt-1 flex items-center gap-3">
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
              Supporting context
            </p>
            <div className="h-px flex-1 bg-border/70" />
          </div>

          <section className="md:col-span-2 grid gap-3 md:grid-cols-2">
            <Card className="md:col-span-2">
              <CardHeader className="pb-1.5">
                <CardTitle className="text-base">Topic</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <p className="leading-relaxed">{data.topic}</p>
              </CardContent>
            </Card>

            <Card className="self-start">
              <CardHeader className="pb-1.5">
                <CardTitle className="text-base">Sources</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 pt-0">
                {data.sources.length === 0 ? (
                  <EmptyState message="No sources found in this payload." />
                ) : (
                  data.sources.map((source) => (
                    <div
                      key={`${source.id}-${source.title}`}
                      className={`rounded-md border p-2.5 ${
                        linkedSourceIds.has(source.id)
                          ? "border-priguidance-discovery/70 bg-priguidance-discovery/[0.07]"
                          : "border-border/90 bg-background"
                      }`}
                    >
                      <p className="font-medium">{source.title}</p>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-foreground/70">
                        <span className={META_CHIP_CLASS}>id: {source.id}</span>
                        {source.jurisdiction ? (
                          <span className={META_CHIP_CLASS}>
                            jurisdiction: {source.jurisdiction}
                          </span>
                        ) : null}
                        {source.citation ? (
                          <span className={META_CHIP_CLASS}>cite: {source.citation}</span>
                        ) : null}
                        {source.url ? (
                          <a
                            href={source.url}
                            target="_blank"
                            rel="noreferrer"
                            className={`${META_CHIP_CLASS} hover:bg-accent`}
                          >
                            {source.url}
                          </a>
                        ) : null}
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            <Card className="self-start border-border/70 bg-muted/[0.06]">
              <CardHeader className="pb-1.5">
                <CardTitle className="text-sm">Propositions (full list)</CardTitle>
              </CardHeader>
              <CardContent className="max-h-[30rem] space-y-1.5 overflow-auto pt-0 pr-1">
                {data.propositions.length === 0 ? (
                  <EmptyState message="No propositions found in this payload." />
                ) : (
                  data.propositions.map((item) => (
                    <div
                      key={`${item.id}-${item.text}`}
                      className={`rounded-md border p-2 ${
                        linkedPropositionIds.has(item.id)
                          ? "border-priguidance-discovery/60 bg-priguidance-discovery/[0.06]"
                          : "border-border/70 bg-background/80"
                      }`}
                    >
                      <p className="mb-1 text-[11px] text-foreground/70">
                        <span className={META_CHIP_CLASS}>id: {item.id}</span>
                      </p>
                      <p className="text-sm leading-relaxed text-foreground/90">{item.text}</p>
                      <div className="mt-1 flex flex-wrap gap-1.5 text-[11px] text-foreground/70">
                        {item.articleReference ? (
                          <span className={META_CHIP_CLASS}>article: {item.articleReference}</span>
                        ) : null}
                        {item.legalSubject ? (
                          <span className={META_CHIP_CLASS}>subject: {item.legalSubject}</span>
                        ) : null}
                        {item.action ? (
                          <span className={META_CHIP_CLASS}>action: {item.action}</span>
                        ) : null}
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            <div className="md:col-span-2 rounded-lg border border-border/60 bg-muted/15 px-3 py-2.5">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground/80">
                Narrative summary
              </p>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-foreground/85">
                {data.narrative}
              </p>
            </div>
          </section>
        </section>
      ) : null}
    </main>
  );
}
