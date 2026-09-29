"use client";

import type { ReactNode } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  READINESS_STEP_LABELS,
  chipOrDash,
  corpusCoverageCountsFromPayload,
  corpusReadinessHighlightIndex,
  corpusRowDisplayStatus,
  corpusRowsByEquineLawFamily,
  corpusSecondaryLocatorLine,
  corpusSourceBucket,
  corpusSourceTitleLine,
  currentEuEquineIdentificationDownstreamCandidates,
  equinePortfolioStatusLabel,
  groupCorpusSourcesByBucket,
  sourceUniverseClusterEntries,
} from "@/lib/equine-corpus-coverage-utils";

const META_CHIP_CLASS =
  "rounded-md border border-border bg-muted px-2 py-0.5 font-mono text-[11px] leading-5 font-medium text-foreground";

function toText(value: unknown, fallback = "—"): string {
  if (typeof value === "string") {
    return value.trim() || fallback;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function asArrayRecords(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => asRecord(item))
    .filter((item): item is Record<string, unknown> => item !== null);
}

function CorpusCoverageJsonBlock({ payload }: { payload: unknown }): JSX.Element {
  return (
    <pre className="max-h-80 overflow-auto rounded-md border border-border bg-muted/50 p-3 text-[11px] leading-relaxed text-foreground">
      {JSON.stringify(payload, null, 2)}
    </pre>
  );
}

function MetadataChip({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <span className={META_CHIP_CLASS} title={label}>
      {label}: {value}
    </span>
  );
}

function SourceCoverageRowItem({
  row,
  mutedTechnicalDetail,
}: {
  row: Record<string, unknown>;
  mutedTechnicalDetail: boolean;
}): JSX.Element {
  const titleLine = corpusSourceTitleLine(row);
  const secondary = corpusSecondaryLocatorLine(row);
  const sid = String(row.source_id ?? "");
  const eqRel = typeof row.equine_relevance === "string" ? row.equine_relevance.trim() : "";
  const confChip =
    typeof row.confidence === "string" && row.confidence.trim() ? chipOrDash(row.confidence) : null;
  const eqPortfolio =
    typeof row.equine_portfolio_status === "string" ? row.equine_portfolio_status.trim() : "";
  const candInc =
    typeof row.corpus_candidate_inclusion_status === "string"
      ? row.corpus_candidate_inclusion_status.trim()
      : "";

  const primaryTone = mutedTechnicalDetail
    ? "text-foreground/75"
    : row.extraction_status === "excluded"
      ? "text-muted-foreground line-through decoration-muted-foreground"
      : corpusSourceBucket(row) === "included_legal"
        ? "text-emerald-800 dark:text-emerald-200"
        : "text-foreground";

  return (
    <li className="rounded-md border border-border bg-card px-2.5 py-2 shadow-sm">
      <p className={`text-[12px] font-medium leading-snug ${primaryTone}`}>{titleLine}</p>
      <div className="mt-1 flex flex-wrap gap-1">
        <MetadataChip label="status" value={corpusRowDisplayStatus(row)} />
        <MetadataChip label="role" value={chipOrDash(row.source_role)} />
        <MetadataChip label="relationship" value={chipOrDash(row.relationship_to_target)} />
        {confChip ? <MetadataChip label="confidence" value={confChip} /> : null}
        {eqPortfolio ? (
          <MetadataChip label="corpus posture" value={equinePortfolioStatusLabel(eqPortfolio)} />
        ) : null}
        {candInc ? <MetadataChip label="discovery inclusion" value={chipOrDash(candInc)} /> : null}
        {eqRel ? <MetadataChip label="equine relevance" value={eqRel} /> : null}
      </div>
      {secondary ? (
        <p className="mt-1 break-all text-[10px] text-foreground/70">{secondary}</p>
      ) : null}
      <p className="mt-0.5 font-mono text-[10px] text-foreground/65">Internal ID: {sid || "—"}</p>
    </li>
  );
}

function SectionBlock({
  title,
  description,
  rows,
  mutedTechnicalDetail,
}: {
  title: string;
  description: string;
  rows: Record<string, unknown>[];
  mutedTechnicalDetail?: boolean;
}): JSX.Element | null {
  if (rows.length === 0) {
    return null;
  }
  const showHeading = Boolean(title.trim() || description.trim());
  return (
    <div className="space-y-1">
      {showHeading ? (
        <div>
          {title.trim() ? (
            <p className="text-[11px] font-semibold text-foreground">{title}</p>
          ) : null}
          {description.trim() ? (
            <p className="text-[10px] leading-snug text-foreground/70">{description}</p>
          ) : null}
        </div>
      ) : null}
      <ul className="max-h-44 space-y-1 overflow-y-auto pr-0.5">
        {rows.map((row, idx) => (
          <SourceCoverageRowItem
            key={`${String(row.source_id ?? "row")}-${idx}`}
            row={row}
            mutedTechnicalDetail={mutedTechnicalDetail ?? false}
          />
        ))}
      </ul>
    </div>
  );
}

const EXPECTED_ROLE_GUIDANCE = (
  <div className="space-y-2 text-[11px] text-foreground/80">
    <p className="font-semibold text-foreground">Core legal sources</p>
    <ul className="list-disc space-y-0.5 pl-4">
      <li>Regulation (EU) 2016/429 base act</li>
      <li>EU consolidated text</li>
      <li>UK retained / assimilated version</li>
      <li>Corrigenda and amendments</li>
    </ul>
    <p className="font-semibold text-foreground">Equine / scope-relevant sources</p>
    <ul className="list-disc space-y-0.5 pl-4">
      <li>Article 109 database provisions</li>
      <li>Article 114 equine identification provisions</li>
      <li>
        Commission Implementing Regulation (EU) 2015/262 — equine passports (often historical
        baseline)
      </li>
      <li>
        AHL delegated / implementing pairs such as (EU) 2019/2035 and (EU) 2021/963 for
        identification documents
      </li>
      <li>
        Delegated / implementing acts under Articles 118 / 120 and related powers where registered
      </li>
      <li>
        Movement, certification, disease-control instruments (for example (EU) 2020/688 and (EU)
        2020/692)
      </li>
      <li>
        Annexes, corrigenda, model certificates, official lists — each as explicit rows when
        discovered
      </li>
    </ul>
    <p className="font-semibold text-foreground">Context / support</p>
    <ul className="list-disc space-y-0.5 pl-4">
      <li>Explanatory material</li>
      <li>Official guidance</li>
      <li>Certificate models / operational forms</li>
    </ul>
    <p className="text-[10px] italic text-foreground/75">
      Roles above map to source-role chips (for example base_act, consolidated_text, guidance). The
      list does not invent instruments — it explains how categories appear once present in coverage
      data.
    </p>
  </div>
);

export function EquineCorpusCoveragePanel({
  payload,
  coverageEndpointError,
  readinessToolbar,
}: {
  payload: Record<string, unknown> | null;
  coverageEndpointError?: string | null;
  readinessToolbar?: ReactNode;
}): JSX.Element {
  const doc =
    typeof payload === "object" && payload !== null ? (payload as Record<string, unknown>) : null;
  const sourceUniverse = doc ? asRecord(doc.source_universe) : null;
  const universeClusterLines = sourceUniverseClusterEntries(sourceUniverse);
  const sourceDoc = doc ? asRecord(doc.source_coverage) : null;
  const propDoc = doc ? asRecord(doc.proposition_coverage) : null;
  const summary = sourceDoc ? asRecord(sourceDoc.summary) : null;
  const sourceRows = asArrayRecords(sourceDoc?.sources);
  const propositionRows = asArrayRecords(propDoc?.propositions);

  const grouped = groupCorpusSourcesByBucket(sourceRows);
  const counts = corpusCoverageCountsFromPayload({
    summary,
    sourceRows,
    propositionRows,
  });

  const unreviewedProps = propositionRows.filter(
    (r) => String(r.review_status ?? "").toLowerCase() === "proposed"
  ).length;

  const readinessIdx = corpusReadinessHighlightIndex({
    pendingLegalCandidates: counts.pendingLegalCandidates,
    includedLegalSources: counts.includedLegalSources,
    propositionsTotal: counts.propositionsTotal,
    propositionsUnreviewed: unreviewedProps,
    guidanceReadyPropositions: counts.guidanceReadyPropositions,
  });

  const guidanceReadyList = propositionRows.filter((r) => r.guidance_ready === true);

  const downstreamIds = new Set(["sfc-2019-2035-delegated", "sfc-2021-963-implementing"]);
  const passportFamilyAll = corpusRowsByEquineLawFamily(
    sourceRows,
    "equine_passport_identification"
  );
  const passportFamilyPrimary = passportFamilyAll.filter(
    (r) => !downstreamIds.has(String(r.source_id ?? ""))
  );
  const euIdentificationDownstream = currentEuEquineIdentificationDownstreamCandidates(sourceRows);
  const movementFamily = corpusRowsByEquineLawFamily(sourceRows, "movement_entry_certification");

  return (
    <Card className="md:col-span-2">
      <CardHeader className="space-y-4 pb-2">
        <div className="space-y-2">
          <CardTitle className="text-lg">Equine corpus coverage</CardTitle>
          <CardDescription className="text-sm leading-relaxed text-foreground/80">
            Export-root artifacts from{" "}
            <code className="rounded-md bg-muted px-1 py-0.5 text-[11px] text-foreground">
              build-equine-corpus
            </code>
            .
          </CardDescription>
        </div>
        <div
          className="flex flex-col gap-1 rounded-lg border border-amber-600/85 bg-amber-100 px-3 py-3 text-sm font-medium text-amber-950 shadow-sm dark:border-amber-500 dark:bg-amber-950 dark:text-amber-50"
          role="note"
        >
          <span className="inline-flex w-fit items-center rounded-md border border-amber-800/70 bg-amber-200 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide dark:border-amber-400 dark:bg-amber-900 dark:text-amber-100">
            Pending review
          </span>
          <span>Coverage status is pending review — not a claim of complete equine law.</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-6 text-[12px] text-foreground">
        {coverageEndpointError ? (
          <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-[11px] font-semibold leading-relaxed text-destructive">
            Equine coverage API: {coverageEndpointError}
          </p>
        ) : null}
        {!doc && !coverageEndpointError ? (
          <p className="rounded-lg border border-border bg-muted/60 px-3 py-2.5 text-[11px] font-medium leading-relaxed text-foreground">
            No curated equine corpus artifacts loaded from the ops export root yet — run below to
            extract, export, and refresh readiness.
          </p>
        ) : null}
        <section
          className="rounded-lg border border-border bg-muted/35 px-4 py-4 shadow-sm"
          aria-labelledby="equine-readiness-heading"
        >
          <p
            id="equine-readiness-heading"
            className="mb-3 text-[11px] font-bold uppercase tracking-wider text-foreground"
          >
            Corpus readiness
          </p>
          <div className="mb-3 flex flex-wrap gap-2">
            {READINESS_STEP_LABELS.map((label, i) => (
              <span
                key={label}
                className={
                  i === readinessIdx
                    ? "inline-flex rounded-full border border-primary bg-primary px-2.5 py-1 text-[11px] font-semibold text-primary-foreground shadow-sm"
                    : "inline-flex rounded-full border border-input bg-transparent px-2.5 py-1 text-[11px] font-medium text-foreground/70"
                }
              >
                {i + 1}. {label}
              </span>
            ))}
          </div>
          <p className="mb-4 text-[11px] leading-relaxed text-foreground/75">
            Ladder shows workflow position inferred from exports — not legal completeness.
            Guidance-ready is only highlighted when reviewed, high-confidence propositions exist in
            this artifact set.
          </p>
          {readinessToolbar ? (
            <div className="border-t border-border pt-4">{readinessToolbar}</div>
          ) : null}
        </section>

        {sourceUniverse ? (
          <section
            className="rounded-lg border border-sky-700/40 bg-sky-950/20 px-4 py-3 text-[11px] leading-relaxed text-foreground shadow-sm dark:border-sky-500/35 dark:bg-sky-950/40"
            aria-label="Staged source universe"
          >
            <p className="font-semibold text-foreground">
              Staged source universe (profile:{" "}
              <span className="font-mono">{toText(sourceUniverse.profile_id)}</span>)
            </p>
            <p className="mt-1 text-foreground/85">
              This source universe is broader than the analysed corpus. Only profile-selected sources
              are fetched and extracted for propositions.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <span className={META_CHIP_CLASS}>
                universe instruments: {toText(sourceUniverse.universe_instrument_count)}
              </span>
              <span className={META_CHIP_CLASS}>
                analysed legislation sources: {toText(sourceUniverse.analysed_legislation_source_count)}
              </span>
              <span className={META_CHIP_CLASS}>
                analysis scope: {toText(sourceUniverse.analysis_scope) || "—"}
              </span>
            </div>
            {universeClusterLines.length > 0 ? (
              <div className="mt-3 space-y-1">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-foreground/80">
                  Universe counts by cluster
                </p>
                <ul className="flex flex-wrap gap-2">
                  {universeClusterLines.map((c) => (
                    <li key={c.key}>
                      <span className={META_CHIP_CLASS} title={c.label}>
                        {c.label}: {c.count}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            <p className="mt-2 text-[10px] italic text-foreground/70">
              Roles for ingested rows use staged-universe analysis_role values (for example
              required_core, optional_context) in the coverage list below.
            </p>
          </section>
        ) : null}

        {doc ? (
          <>
            <div className="flex flex-wrap gap-2">
              <span className={META_CHIP_CLASS}>corpus: {toText(sourceDoc?.corpus_id)}</span>
              <span className={META_CHIP_CLASS}>
                artifact status: {toText(sourceDoc?.coverage_status)}
              </span>
              <span className={META_CHIP_CLASS}>
                discovered candidates (discovery): {toText(summary?.sources_discovered_candidates)}
              </span>
              <span className={META_CHIP_CLASS}>
                included legal sources: {counts.includedLegalSources}
              </span>
              <span className={META_CHIP_CLASS}>
                pending legal candidates: {counts.pendingLegalCandidates}
              </span>
              <span className={META_CHIP_CLASS}>
                excluded candidates: {counts.excludedLegalCandidates}
              </span>
              <span className={META_CHIP_CLASS}>
                developer fixtures: {counts.developerFixtures}
              </span>
              <span className={META_CHIP_CLASS}>
                guidance-ready propositions: {counts.guidanceReadyPropositions} /{" "}
                {counts.propositionsTotal}
              </span>
            </div>

            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-4">
                <div className="space-y-2">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-foreground">
                    Corpus source candidates
                  </p>
                  <p className="text-[11px] leading-relaxed text-foreground/75">
                    This list shows legal sources and candidate sources for the equine corpus. It is
                    a review aid, not a claim that the corpus is complete.
                  </p>
                </div>

                <div className="space-y-3 rounded-lg border border-border bg-muted/35 px-3 py-3 shadow-sm">
                  <p className="text-[11px] font-semibold text-foreground">
                    Passport / identification (discovery grouping)
                  </p>
                  <p className="text-[10px] leading-relaxed text-foreground/70">
                    2015/262 and related annex/corrigendum rows surface here without implying they
                    are already ingested. &quot;Corpus posture&quot; chips distinguish historical
                    baseline passports from current AHL delegated routes.
                  </p>
                  <SectionBlock
                    title="Historic / passport family rows"
                    description="Includes Implementing Regulation (EU) 2015/262, UK retained presentation, Annex I/II placeholders, CELEX corrigendum 32015R0262R(02)."
                    rows={passportFamilyPrimary}
                  />
                  <SectionBlock
                    title="Current EU identification detail (delegated + implementing)"
                    description="Commission Delegated Regulation (EU) 2019/2035 and Implementing Regulation (EU) 2021/963 — required_for_scope in discovery metadata; remain candidates until registered like any instrument."
                    rows={euIdentificationDownstream}
                  />
                </div>

                <SectionBlock
                  title="Movement / Union entry candidates"
                  description="Delegated Regulations (EU) 2020/688 and (EU) 2020/692 plus annex-hosted certificate placeholders — ingest only after scope confirmation."
                  rows={movementFamily}
                />

                <SectionBlock
                  title="A. Included legal sources"
                  description="Real legal sources ingested for this export and not marked excluded."
                  rows={grouped.included_legal}
                />
                <SectionBlock
                  title="B. Pending legal candidates"
                  description="Discovered instruments not yet registered or ingested into this workflow."
                  rows={grouped.pending_legal}
                />
                <SectionBlock
                  title="C. Excluded candidates"
                  description="Sources marked excluded for corpus inclusion in pipeline metadata."
                  rows={grouped.excluded_legal}
                />

                <details className="rounded-lg border border-dashed border-border bg-muted/25 shadow-sm hover:bg-muted/40">
                  <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold text-foreground outline-none transition-colors hover:bg-accent/80 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background">
                    D. Developer validation fixtures ({grouped.developer_fixture.length})
                  </summary>
                  <p className="mt-1 px-3 pb-3 text-[10px] leading-relaxed text-foreground/70">
                    Test and linker-validation rows (for example fixture-equine-direct). Not corpus
                    legal instruments — kept separate so coverage reflects operational law sources.
                  </p>
                  <div className="mt-2">
                    <SectionBlock
                      title=""
                      description=""
                      rows={grouped.developer_fixture}
                      mutedTechnicalDetail
                    />
                  </div>
                </details>
              </div>

              <div className="space-y-3">
                <p className="text-[11px] font-bold uppercase tracking-wider text-foreground">
                  Guidance-ready propositions
                </p>
                <p className="text-[11px] leading-relaxed text-foreground/75">
                  Guidance-ready means reviewed, high-confidence propositions with source evidence.
                </p>
                <ul className="max-h-52 space-y-1 overflow-y-auto rounded-lg border border-border bg-card p-3 font-mono text-[11px] text-foreground shadow-sm">
                  {guidanceReadyList.length === 0 ? (
                    <>
                      <li className="text-foreground/70">None yet.</li>
                      <li className="mt-2 text-[11px] text-foreground/70">
                        Review extracted propositions before using them in guidance.
                      </li>
                    </>
                  ) : (
                    guidanceReadyList.slice(0, 24).map((row, idx) => (
                      <li key={`${toText(row.proposition_id, "p")}-${idx}`}>
                        {toText(row.proposition_id)} — {toText(row.proposition_key)}
                      </li>
                    ))
                  )}
                </ul>
              </div>
            </div>

            <details className="group rounded-lg border border-border bg-card shadow-sm transition-colors hover:border-border hover:bg-accent/30">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 rounded-md px-4 py-3 text-sm font-semibold text-foreground outline-none transition-colors hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background [&::-webkit-details-marker]:hidden">
                <span>Raw corpus coverage JSON</span>
                <span
                  aria-hidden
                  className="shrink-0 text-muted-foreground transition-transform duration-200 group-open:rotate-180"
                >
                  ▼
                </span>
              </summary>
              <div className="border-t border-border px-4 pb-4 pt-3">
                <CorpusCoverageJsonBlock payload={doc} />
              </div>
            </details>
          </>
        ) : null}

        <details className="group rounded-lg border border-border bg-muted/25 shadow-sm transition-colors hover:bg-muted/45">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-sm font-semibold text-foreground outline-none transition-colors hover:bg-accent/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background [&::-webkit-details-marker]:hidden">
            <span>Expected legal corpus categories (reference)</span>
            <span
              aria-hidden
              className="text-foreground/60 transition-transform duration-200 group-open:rotate-180"
            >
              ▼
            </span>
          </summary>
          <div className="border-t border-border bg-card px-4 py-4">{EXPECTED_ROLE_GUIDANCE}</div>
        </details>
      </CardContent>
    </Card>
  );
}
