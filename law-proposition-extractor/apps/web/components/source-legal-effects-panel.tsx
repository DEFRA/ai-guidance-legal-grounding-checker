"use client";

import { ExternalLink } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import {
  affectingInstrumentDisplay,
  consumptionMatchDisplay,
  effectCategoryLabel,
  effectStatusLabel,
  humanCanonicalLocator,
  independentConsumptionStatusLabel,
  isHttpAffectingInstrumentUri,
  outstandingEffectsStatusLabel,
  sourceRepresentationStatusLabel,
  structuralLinkExplanation,
  usefulEffectDiagnostics,
  type RelevantSourceLegalEffect,
  type SourceLegalEffectRow,
  type SourceLegalEffectsView,
} from "@/lib/source-legal-effects";

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

export function OutstandingEffectsStatus(props: {
  status: SourceLegalEffectsView["outstandingEffectsStatus"];
  compact?: boolean;
}): JSX.Element {
  const { status, compact = false } = props;
  const label = outstandingEffectsStatusLabel(status);
  return (
    <p
      className={
        compact
          ? "text-[12px] text-foreground/90"
          : "text-[12px] leading-snug text-foreground/90"
      }
      data-testid="outstanding-effects-status"
      data-outstanding-status={status}
    >
      <span className="text-muted-foreground">Outstanding effects: </span>
      {label}
    </p>
  );
}

export function SourceLegalEffectCard(props: {
  match?: RelevantSourceLegalEffect;
  effect?: SourceLegalEffectRow;
  showDeveloperFields?: boolean;
}): JSX.Element {
  const effect = props.match?.effect ?? props.effect;
  if (!effect) {
    return <></>;
  }
  const match = props.match;
  const label = String(effect.annotation_label ?? "").trim() || "Annotation";
  const category = effectCategoryLabel(effect.effect_category);
  const instrument = affectingInstrumentDisplay(effect);
  const affectedLabel =
    humanCanonicalLocator(
      match?.matchedLocator ?? effect.affected_locator ?? match?.ancestorLocator,
    ) ?? "Not linked to a structural locator";
  const consumption = String(effect.independent_consumption_status ?? "not_assessed");
  const consumedConfirmed = consumption === "consumed_in_current_run";
  const registerOnly = consumption === "present_in_source_register_but_not_consumed";
  const matchDisplay = consumptionMatchDisplay(effect);

  return (
    <article
      className="rounded-md border border-border/70 bg-background/80 px-2.5 py-2"
      data-testid="source-legal-effect-card"
      data-effect-id={effect.id}
      data-annotation-label={label}
      data-relevance={match?.relevance ?? "snapshot"}
      data-consumption-status={consumption}
    >
      <h5 className="text-[12px] font-medium text-foreground">
        {label} · {category}
      </h5>
      {match ? (
        <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
          {structuralLinkExplanation(match)}
        </p>
      ) : null}

      <dl className="mt-2 space-y-1.5">
        <FieldLine label="Affecting instrument">
          {instrument.primary ? (
            <span className="break-words">{instrument.primary}</span>
          ) : (
            <span>Not stated by consumed source</span>
          )}
        </FieldLine>
        <FieldLine label="Affected source">{affectedLabel}</FieldLine>
        <FieldLine label="Source-reported status">
          {effectStatusLabel(effect.effect_status)}
        </FieldLine>
        <FieldLine label="Affecting instrument independently consumed">
          <span data-testid="independent-consumption-status">
            {independentConsumptionStatusLabel(effect.independent_consumption_status)}
          </span>
        </FieldLine>
        {consumedConfirmed ? (
          <>
            {(matchDisplay.title || matchDisplay.citation || matchDisplay.matchedSourceRecordId) && (
              <FieldLine label="Matched source">
                <span className="break-words" data-testid="matched-consumed-source">
                  {[matchDisplay.title, matchDisplay.citation].filter(Boolean).join(" · ") ||
                    matchDisplay.matchedSourceRecordId}
                </span>
              </FieldLine>
            )}
            <FieldLine label="Snapshots consumed">
              <span data-testid="matched-snapshot-count">{matchDisplay.snapshotCount}</span>
            </FieldLine>
            <p
              className="text-[10px] leading-snug text-muted-foreground"
              data-testid="consumption-not-application-note"
            >
              Independent consumption does not mean Law Proposition Extractor applied or verified the amendment effect.
            </p>
          </>
        ) : null}
        {registerOnly ? (
          <p
            className="text-[10px] leading-snug text-muted-foreground"
            data-testid="register-only-note"
          >
            Present in the run&apos;s source register, but not independently ingested as a source
            snapshot.
          </p>
        ) : null}
        {effect.effect_description ? (
          <FieldLine label="Description">
            <span className="break-words">{effect.effect_description}</span>
          </FieldLine>
        ) : null}
        {effect.effect_date ? <FieldLine label="Effect date">{effect.effect_date}</FieldLine> : null}
        {instrument.provision ? (
          <FieldLine label="Affecting provision">{instrument.provision}</FieldLine>
        ) : null}
        {effect.source_representation_status ? (
          <FieldLine label="Source representation">
            {sourceRepresentationStatusLabel(effect.source_representation_status)}
          </FieldLine>
        ) : null}
      </dl>

      {instrument.uri && isHttpAffectingInstrumentUri(instrument.uri) ? (
        <div className="mt-2">
          <a
            href={instrument.uri}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[11px] font-medium text-sky-900 underline-offset-2 hover:underline dark:text-sky-100"
            data-testid="open-affecting-instrument"
          >
            Open affecting instrument on legislation.gov.uk
            <ExternalLink className="h-3 w-3 shrink-0 opacity-80" aria-hidden />
          </a>
        </div>
      ) : null}

      {props.showDeveloperFields || effect.annotation_id || effect.raw_effect_category ? (
        <details className="mt-2 text-[10px] text-muted-foreground">
          <summary className="cursor-pointer select-none">Developer details</summary>
          <ul className="mt-1 space-y-0.5 font-mono">
            <li>effect_id: {effect.id}</li>
            {effect.annotation_id ? <li>annotation_id: {effect.annotation_id}</li> : null}
            {effect.raw_effect_category ? (
              <li>raw_effect_category: {effect.raw_effect_category}</li>
            ) : null}
            {instrument.uri ? <li className="break-all">affecting_uri: {instrument.uri}</li> : null}
            {effect.matched_source_record_id ? (
              <li>matched_source_record_id: {effect.matched_source_record_id}</li>
            ) : null}
            {effect.matched_instrument_identity ? (
              <li>matched_instrument_identity: {effect.matched_instrument_identity}</li>
            ) : null}
            {effect.consumption_match_basis ? (
              <li>consumption_match_basis: {effect.consumption_match_basis}</li>
            ) : null}
          </ul>
        </details>
      ) : null}
    </article>
  );
}

export function SourceLegalEffectsSummary(props: {
  view: SourceLegalEffectsView;
}): JSX.Element | null {
  const { view } = props;
  if (!view.hasEffects && view.outstandingEffectsStatus === "source_status_unknown") {
    // Older runs / empty artifact: keep the Source context quiet unless there is
    // something useful to say. Still allow explicit source-reported statuses.
    return null;
  }
  if (!view.hasEffects) {
    return (
      <div className="space-y-1" data-testid="source-legal-effects-summary">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          Source change annotations
        </p>
        <OutstandingEffectsStatus status={view.outstandingEffectsStatus} compact />
      </div>
    );
  }

  const relevantCount = view.relevant.length;
  const labels =
    view.relevantLabels.length > 0 ? view.relevantLabels.join(", ") : null;

  return (
    <div className="space-y-1" data-testid="source-legal-effects-summary">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        Source change annotations
      </p>
      <p className="text-[12px] text-foreground/90">
        {view.totalEffectCount} change annotation
        {view.totalEffectCount === 1 ? "" : "s"} recorded in the consumed source
        {relevantCount > 0 ? ` · ${relevantCount} relevant to this provision` : ""}
      </p>
      {labels ? (
        <p className="text-[12px] text-foreground/90">
          <span className="text-muted-foreground">Relevant annotations: </span>
          {labels}
        </p>
      ) : null}
      <OutstandingEffectsStatus status={view.outstandingEffectsStatus} compact />
    </div>
  );
}

export function SourceLegalEffectsPanel(props: {
  view: SourceLegalEffectsView;
  showDeveloperFields?: boolean;
}): JSX.Element | null {
  const { view, showDeveloperFields = false } = props;
  const panelId = useId();
  const otherId = useId();
  const [open, setOpen] = useState(false);
  const [otherOpen, setOtherOpen] = useState(false);

  if (!view.hasEffects) {
    return null;
  }

  const diagnostics = usefulEffectDiagnostics(view.diagnostics);

  return (
    <div className="mt-2" data-testid="source-legal-effects-panel">
      <button
        type="button"
        className="rounded border border-border/80 px-2 py-0.5 text-[10px] font-medium text-muted-foreground hover:bg-muted/50"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
      >
        {open
          ? "Changes recorded in consumed source ▾"
          : "Changes recorded in consumed source ▸"}
      </button>
      {open ? (
        <div
          id={panelId}
          className="mt-2 space-y-3 rounded-md border border-border/70 bg-background/80 px-2.5 py-2"
        >
          <p
            className="text-[11px] leading-snug text-muted-foreground"
            data-testid="source-legal-effects-truthfulness"
          >
            These records describe change annotations present in the legislation.gov.uk XML
            consumed by Law Proposition Extractor. They do not show that Law Proposition Extractor independently applied the changes,
            verified the full amendment history, or separately consumed each affecting instrument.
          </p>

          <OutstandingEffectsStatus status={view.outstandingEffectsStatus} />

          <section aria-labelledby={`${panelId}-relevant`}>
            <h4
              id={`${panelId}-relevant`}
              className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground"
            >
              Relevant to this proposition/provision
            </h4>
            {view.relevant.length > 0 ? (
              <ul className="mt-2 space-y-2">
                {view.relevant.map((match) => (
                  <li key={match.effect.id}>
                    <SourceLegalEffectCard
                      match={match}
                      showDeveloperFields={showDeveloperFields}
                    />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-[11px] text-muted-foreground">
                No change annotations are linked to this provision in the consumed source.
              </p>
            )}
          </section>

          {view.other.length > 0 ? (
            <section aria-labelledby={`${panelId}-other`}>
              <button
                type="button"
                className="rounded border border-border/80 px-2 py-0.5 text-[10px] font-medium text-muted-foreground hover:bg-muted/50"
                aria-expanded={otherOpen}
                aria-controls={otherId}
                onClick={() => setOtherOpen((current) => !current)}
              >
                {otherOpen
                  ? "Other changes recorded for this source snapshot ▾"
                  : `Other changes recorded for this source snapshot (${view.other.length}) ▸`}
              </button>
              {otherOpen ? (
                <ul id={otherId} className="mt-2 space-y-2" aria-labelledby={`${panelId}-other`}>
                  {view.other.map((effect) => (
                    <li key={effect.id}>
                      <SourceLegalEffectCard
                        effect={effect}
                        showDeveloperFields={showDeveloperFields}
                      />
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>
          ) : null}

          {diagnostics.length > 0 ? (
            <div data-testid="source-legal-effects-diagnostics">
              <p className="text-[11px] text-muted-foreground">
                Some source change references could not be fully resolved in this run.
              </p>
              {showDeveloperFields ? (
                <ul className="mt-1 space-y-0.5 font-mono text-[10px] text-muted-foreground">
                  {diagnostics.map((diag, index) => (
                    <li key={`${diag.code ?? "diag"}-${index}`}>
                      {String(diag.code ?? "diagnostic")}
                      {diag.message ? `: ${String(diag.message)}` : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
