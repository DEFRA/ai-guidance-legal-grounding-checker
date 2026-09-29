"use client";

import { ExternalLink } from "lucide-react";
import { useCallback, useId, useState, type ReactNode } from "react";

import {
  knowledgeStatusLabel,
  statusChipLabel,
  type SourceVersionProvenanceView,
} from "@/lib/source-version-provenance";
import type { SourceLegalEffectsView } from "@/lib/source-legal-effects";
import {
  SourceLegalEffectsPanel,
  SourceLegalEffectsSummary,
} from "@/components/source-legal-effects-panel";

const META_CHIP_CLASS =
  "rounded border border-border/70 bg-muted/30 px-1.5 py-0.5 text-[10px] text-muted-foreground";

function FieldLine(props: { label: string; children: ReactNode }): JSX.Element {
  return (
    <div className="grid gap-0.5 sm:grid-cols-[9.5rem_minmax(0,1fr)] sm:gap-2">
      <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {props.label}
      </dt>
      <dd className="min-w-0 break-words text-[12px] text-foreground/90">{props.children}</dd>
    </div>
  );
}

function Mono(props: { children: ReactNode; title?: string }): JSX.Element {
  return (
    <span className="font-mono text-[11px]" title={props.title}>
      {props.children}
    </span>
  );
}

export function SourceProvenanceStatusList(props: {
  view: SourceVersionProvenanceView;
}): JSX.Element {
  const { view } = props;
  return (
    <div className="space-y-3" data-testid="source-provenance-status-list">
      {view.knowledgeRecorded.length > 0 ? (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
            Known
          </p>
          <ul className="mt-1 space-y-0.5 text-[12px] text-foreground/90">
            {view.knowledgeRecorded.map((item) => (
              <li key={item.id}>
                <span aria-hidden>✓ </span>
                {item.label}
                <span className="sr-only"> ({knowledgeStatusLabel(item.status)})</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {view.knowledgeAbsent.length > 0 ? (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
            Not recorded, not assessed, or not established
          </p>
          <ul className="mt-1 space-y-0.5 text-[12px] text-muted-foreground">
            {view.knowledgeAbsent.map((item) => (
              <li key={item.id}>
                <span aria-hidden>— </span>
                {item.label}
                <span className="sr-only"> ({knowledgeStatusLabel(item.status)})</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function ConsumedSourceProvenance(props: {
  view: SourceVersionProvenanceView;
  runId: string;
  apiBaseUrl: string;
}): JSX.Element {
  const { view, runId, apiBaseUrl } = props;
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const [inspectState, setInspectState] = useState<
    | { kind: "idle" }
    | { kind: "loading" }
    | { kind: "content"; text: string; contentType: string | null }
    | { kind: "fragment" }
    | { kind: "unavailable"; message: string }
    | { kind: "error"; message: string }
  >({ kind: "idle" });

  const inspectSnapshot = useCallback(async () => {
    if (view.snapshotInspection === "fragment_only") {
      setInspectState({ kind: "fragment" });
      return;
    }
    if (view.snapshotInspection !== "api_available" || !view.sourceSnapshotId) {
      setInspectState({
        kind: "unavailable",
        message:
          "Full consumed snapshot is unavailable for this run. The consumed fragment and snapshot identity are still available.",
      });
      return;
    }
    setInspectState({ kind: "loading" });
    try {
      const response = await fetch(
        `${apiBaseUrl}/ops/source-snapshots/${encodeURIComponent(view.sourceSnapshotId)}/content?run_id=${encodeURIComponent(runId)}`,
        { headers: { Accept: "application/json" } },
      );
      if (!response.ok) {
        setInspectState({
          kind: "unavailable",
          message:
            "Full consumed snapshot is unavailable for this run. The consumed fragment and snapshot identity are still available.",
        });
        return;
      }
      const payload = (await response.json()) as {
        available?: boolean;
        content?: string | null;
        content_type?: string | null;
        reason?: string | null;
      };
      if (!payload.available || !payload.content) {
        setInspectState({
          kind: "unavailable",
          message:
            payload.reason?.trim() ||
            "Full consumed snapshot is unavailable for this run. The consumed fragment and snapshot identity are still available.",
        });
        return;
      }
      setInspectState({
        kind: "content",
        text: payload.content,
        contentType: payload.content_type ?? null,
      });
    } catch (error: unknown) {
      setInspectState({
        kind: "error",
        message: error instanceof Error ? error.message : "Failed to load snapshot content",
      });
    }
  }, [apiBaseUrl, runId, view.snapshotInspection, view.sourceSnapshotId]);

  return (
    <div className="mt-2" data-testid="consumed-source-provenance">
      <button
        type="button"
        className="rounded border border-border/80 px-2 py-0.5 text-[10px] font-medium text-muted-foreground hover:bg-muted/50"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
      >
        {open ? "What Law Proposition Extractor consumed ▾" : "What Law Proposition Extractor consumed ▸"}
      </button>
      {open ? (
        <div
          id={panelId}
          className="mt-2 space-y-3 rounded-md border border-border/70 bg-background/80 px-2.5 py-2"
        >
          <dl className="space-y-2">
            <FieldLine label="Source record">
              <Mono>{view.sourceRecordId}</Mono>
            </FieldLine>
            <FieldLine label="Source snapshot">
              {view.sourceSnapshotId ? (
                <Mono>{view.sourceSnapshotId}</Mono>
              ) : (
                <span>Not recorded</span>
              )}
            </FieldLine>
            <FieldLine label="Consumed source">
              {view.consumedSourceUrl ? (
                isSafeConsumedUrl(view.consumedSourceUrl) ? (
                  <a
                    href={view.consumedSourceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="break-all text-sky-800 underline-offset-2 hover:underline dark:text-sky-200"
                  >
                    {view.consumedSourceUrl}
                  </a>
                ) : (
                  <Mono>{view.consumedSourceUrl}</Mono>
                )
              ) : (
                <span>Not recorded</span>
              )}
            </FieldLine>
            <FieldLine label="Consumed format">
              {view.consumedFormat ?? "Not recorded"}
            </FieldLine>
            <FieldLine label="Retrieved">
              {view.retrievedAtLabel ?? "Not recorded"}
            </FieldLine>
            <FieldLine label="Content hash">
              {view.contentHash ? (
                <Mono title={view.contentHash}>{view.contentHashShort ?? view.contentHash}</Mono>
              ) : (
                <span>Not recorded</span>
              )}
            </FieldLine>
            <FieldLine label="Parser">{view.parserName ?? "Not recorded"}</FieldLine>
            <FieldLine label="Manifestation">{view.manifestationTypeLabel}</FieldLine>
            {view.manifestationBasisLabel ? (
              <FieldLine label="Basis">{view.manifestationBasisLabel}</FieldLine>
            ) : null}
            {view.requestedManifestation && !view.resolvedManifestation ? (
              <>
                <FieldLine label="Requested manifestation">
                  {view.requestedManifestationLabel}
                </FieldLine>
                <FieldLine label="Resolved manifestation">
                  Not confirmed by source metadata
                </FieldLine>
              </>
            ) : null}
            {view.requestedAsOfDateLabel ? (
              <FieldLine label="Requested as of">{view.requestedAsOfDateLabel}</FieldLine>
            ) : null}
            {view.resolvedAsOfDateLabel ? (
              <FieldLine label="Resolved as of">{view.resolvedAsOfDateLabel}</FieldLine>
            ) : (
              <FieldLine label="As-of date">{view.asOfDateLabel}</FieldLine>
            )}
            {view.revisedManifestationDisclaimer ? (
              <p
                className="text-[11px] leading-snug text-muted-foreground"
                data-testid="revised-manifestation-disclaimer"
              >
                {view.revisedManifestationDisclaimer}
              </p>
            ) : null}
            {view.versionId ? (
              <FieldLine label="Intake version_id">
                <Mono>{view.versionId}</Mono>
                <span className="mt-0.5 block text-[11px] text-muted-foreground">
                  Intake identifier only — not a legislative manifestation version.
                </span>
              </FieldLine>
            ) : null}
            <FieldLine label="Proposition source">
              {view.fragmentLocator ? (
                <span>
                  {humanLocator(view.fragmentLocator)}
                  {view.sourceFragmentId ? (
                    <>
                      {" "}
                      <Mono>({view.sourceFragmentId})</Mono>
                    </>
                  ) : null}
                </span>
              ) : (
                <span>Not recorded</span>
              )}
            </FieldLine>
            {view.fragmentHash ? (
              <FieldLine label="Fragment hash">
                <Mono title={view.fragmentHash}>{view.fragmentHash}</Mono>
              </FieldLine>
            ) : null}
          </dl>

          <div className="space-y-1.5 border-t border-border/60 pt-2">
            {view.snapshotInspection === "api_available" ? (
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded border border-sky-700/35 bg-sky-950/10 px-2 py-0.5 text-[11px] text-sky-950 hover:bg-sky-950/20 dark:text-sky-100"
                onClick={() => void inspectSnapshot()}
              >
                Inspect consumed snapshot
              </button>
            ) : view.snapshotInspection === "fragment_only" ? (
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded border border-border/80 px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-muted/50"
                onClick={() => void inspectSnapshot()}
              >
                View consumed source fragment
              </button>
            ) : (
              <p className="text-[11px] text-muted-foreground">
                Full consumed snapshot is unavailable for this run. The consumed fragment and
                snapshot identity are still available.
              </p>
            )}
            {inspectState.kind === "loading" ? (
              <p className="text-[11px] text-muted-foreground">Loading snapshot…</p>
            ) : null}
            {inspectState.kind === "content" ? (
              <div data-testid="consumed-snapshot-viewer">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Consumed snapshot text
                  {inspectState.contentType ? ` · ${inspectState.contentType}` : ""}
                </p>
                <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap rounded border border-border/70 bg-muted/20 p-2 font-mono text-[10px] leading-relaxed text-foreground">
                  {inspectState.text}
                </pre>
              </div>
            ) : null}
            {inspectState.kind === "fragment" && view.fragmentText ? (
              <div data-testid="consumed-fragment-viewer">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Consumed fragment text
                </p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  The full raw snapshot is unavailable. Showing the extracted source fragment from
                  this run.
                </p>
                <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap rounded border border-border/70 bg-muted/20 p-2 font-mono text-[10px] leading-relaxed text-foreground">
                  {view.fragmentText}
                </pre>
              </div>
            ) : null}
            {inspectState.kind === "unavailable" || inspectState.kind === "error" ? (
              <p className="text-[11px] text-muted-foreground">{inspectState.message}</p>
            ) : null}
          </div>

          <SourceProvenanceStatusList view={view} />
        </div>
      ) : null}
    </div>
  );
}

function isSafeConsumedUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function humanLocator(locator: string): string {
  const parts = locator.split(":").filter(Boolean);
  if (parts.length >= 2 && parts[0] === "article") {
    const article = parts[1];
    if (parts[2] === "paragraph" && parts[3]) {
      return `Article ${article}, paragraph ${parts[3]}`;
    }
    return `Article ${article}`;
  }
  return locator;
}

export function SourceVersionSummary(props: {
  view: SourceVersionProvenanceView;
  runId: string;
  apiBaseUrl: string;
  sourceLegalEffectsView?: SourceLegalEffectsView | null;
}): JSX.Element {
  const { view, runId, apiBaseUrl, sourceLegalEffectsView = null } = props;
  const formatBits = [
    view.authorityLabel,
    view.consumedFormat ? `consumed as ${view.consumedFormat}` : null,
  ].filter(Boolean);

  return (
    <div
      className="space-y-2 rounded-md border border-border/70 bg-background/70 px-2.5 py-2"
      data-testid="source-version-summary"
      data-source-record-id={view.sourceRecordId}
      data-source-snapshot-id={view.sourceSnapshotId ?? undefined}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          Source version
        </p>
        {view.statusChips.map((chip) => (
          <span key={chip} className={META_CHIP_CLASS}>
            {statusChipLabel(chip)}
          </span>
        ))}
      </div>

      <p className="text-[12px] text-foreground/90">{formatBits.join(" · ")}</p>

      <dl className="space-y-1 text-[12px]">
        {view.sourceSnapshotId ? (
          <div>
            <span className="text-muted-foreground">Snapshot </span>
            <Mono>{view.sourceSnapshotId}</Mono>
          </div>
        ) : (
          <div>
            <span className="text-muted-foreground">Snapshot: </span>
            Not recorded
          </div>
        )}
        <div>
          <span className="text-muted-foreground">Retrieved </span>
          {view.retrievedAtLabel ?? "Not recorded"}
        </div>
        {view.contentHashShort ? (
          <div>
            <span className="text-muted-foreground">Content hash </span>
            <Mono title={view.contentHash ?? undefined}>{view.contentHashShort}</Mono>
          </div>
        ) : null}
        {view.parserName ? (
          <div>
            <span className="text-muted-foreground">Parser </span>
            <Mono>{view.parserName}</Mono>
          </div>
        ) : null}
        <div>
          <span className="text-muted-foreground">As-of date: </span>
          {view.asOfDateLabel}
        </div>
        <div>
          <span className="text-muted-foreground">Manifestation: </span>
          {view.manifestationTypeLabel}
        </div>
        {view.manifestationBasisLabel ? (
          <div>
            <span className="text-muted-foreground">Basis: </span>
            {view.manifestationBasisLabel}
          </div>
        ) : null}
        {view.requestedAsOfDateLabel ? (
          <div>
            <span className="text-muted-foreground">Requested as of: </span>
            {view.requestedAsOfDateLabel}
          </div>
        ) : null}
        {view.resolvedAsOfDateLabel ? (
          <div>
            <span className="text-muted-foreground">Resolved as of: </span>
            {view.resolvedAsOfDateLabel}
          </div>
        ) : null}
        {view.revisedManifestationDisclaimer ? (
          <p
            className="text-[11px] leading-snug text-muted-foreground"
            data-testid="revised-manifestation-disclaimer-summary"
          >
            {view.revisedManifestationDisclaimer}
          </p>
        ) : null}
      </dl>

      {sourceLegalEffectsView &&
      (sourceLegalEffectsView.hasEffects ||
        sourceLegalEffectsView.outstandingEffectsStatus !== "source_status_unknown") ? (
        <div className="space-y-1 border-t border-border/60 pt-2">
          <SourceLegalEffectsSummary view={sourceLegalEffectsView} />
          <SourceLegalEffectsPanel view={sourceLegalEffectsView} />
        </div>
      ) : null}

      {view.liveHtmlUrl ? (
        <div className="space-y-1 border-t border-border/60 pt-2">
          <a
            href={view.liveHtmlUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[12px] font-medium text-sky-900 underline-offset-2 hover:underline dark:text-sky-100"
            data-testid="open-live-legislation-page"
          >
            Open live legislation page
            <ExternalLink className="h-3 w-3 shrink-0 opacity-80" aria-hidden />
          </a>
          <p className="text-[11px] leading-snug text-muted-foreground">
            This opens the current public webpage and may not exactly match the snapshot Law Proposition Extractor
            consumed.
            {view.consumedFormat === "data.xml" && view.fragmentLocator ? (
              <>
                {" "}
                The consumed source is instrument-level {view.consumedFormat}; the live link targets
                the provision locator.
              </>
            ) : null}
          </p>
        </div>
      ) : null}

      <ConsumedSourceProvenance view={view} runId={runId} apiBaseUrl={apiBaseUrl} />
    </div>
  );
}
