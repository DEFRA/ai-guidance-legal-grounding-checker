"use client";

import { useId, useState } from "react";

import {
  sectionHeadingForTypedRole,
  type TypedLegalContextItemView,
  type TypedLegalContextSections,
  type TypedLegalContextUiRole,
} from "@/lib/typed-legal-context";

const ROLE_BADGE_CLASS: Record<TypedLegalContextUiRole, string> = {
  exception:
    "border-amber-700/40 bg-amber-950/10 text-amber-900 dark:border-amber-400/30 dark:text-amber-200",
  displaced_rule:
    "border-sky-700/40 bg-sky-950/10 text-sky-900 dark:border-sky-400/30 dark:text-sky-200",
  trigger:
    "border-violet-700/40 bg-violet-950/10 text-violet-900 dark:border-violet-400/30 dark:text-violet-200",
};

const ROLE_BADGE_LABEL: Record<TypedLegalContextUiRole, string> = {
  exception: "Exception",
  displaced_rule: "Displaced rule",
  trigger: "Trigger",
};

export function LegalRelationshipExplanation(props: {
  item: TypedLegalContextItemView;
  showDeveloperFields?: boolean;
}): JSX.Element {
  const { item, showDeveloperFields = false } = props;
  const panelId = useId();
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-2">
      <button
        type="button"
        className="rounded border border-border/80 px-2 py-0.5 text-[10px] font-medium text-muted-foreground hover:bg-muted/50"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
      >
        {open ? "Hide why linked" : "Why linked"}
      </button>
      {open ? (
        <div
          id={panelId}
          className="mt-2 space-y-1 rounded-md border border-border/70 bg-muted/[0.12] px-2.5 py-2 text-[11px] leading-relaxed text-muted-foreground"
        >
          <p className="text-foreground/90">{item.whyLinkedSummary}</p>
          {item.whyLinkedDetails.map((detail) => (
            <p key={detail}>{detail}</p>
          ))}
          {showDeveloperFields ? (
            <div className="mt-2 space-y-0.5 border-t border-border/60 pt-2 font-mono text-[10px] text-muted-foreground">
              {item.relationshipId ? <p>relationship_id: {item.relationshipId}</p> : null}
              {item.legalRuleGroupId ? <p>legal_rule_group_id: {item.legalRuleGroupId}</p> : null}
              {item.resolutionBasis ? <p>resolution_basis: {item.resolutionBasis}</p> : null}
              {item.inferenceBasis ? <p>inference_basis: {item.inferenceBasis}</p> : null}
              {item.relationshipType ? <p>relationship_type: {item.relationshipType}</p> : null}
              {item.relationshipDirection ? (
                <p>relationship_direction: {item.relationshipDirection}</p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function TypedLegalContextItem(props: {
  item: TypedLegalContextItemView;
  showDeveloperFields?: boolean;
}): JSX.Element {
  const { item, showDeveloperFields = false } = props;

  return (
    <li
      className="rounded-lg border border-border/75 bg-background px-3 py-2"
      data-testid={`typed-legal-context-item-${item.uiRole}`}
      data-proposition-id={item.propositionId || undefined}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${ROLE_BADGE_CLASS[item.uiRole]}`}
        >
          {ROLE_BADGE_LABEL[item.uiRole]}
        </span>
        {item.effectLabel ? (
          <span className="rounded border border-border/70 px-1.5 py-0.5 text-[10px] text-muted-foreground">
            {item.effectLabel}
          </span>
        ) : null}
        {item.missingTarget ? (
          <span className="rounded border border-amber-700/40 bg-amber-950/10 px-1.5 py-0.5 text-[10px] text-amber-900 dark:text-amber-200">
            Missing target
          </span>
        ) : null}
        {showDeveloperFields && item.propositionId ? (
          <span className="font-mono text-[10px] text-primary">{item.propositionId}</span>
        ) : null}
      </div>
      <p className="mt-2 whitespace-pre-wrap break-words text-[13px] leading-relaxed text-foreground">
        {item.propositionText}
      </p>
      <p className="mt-1 font-mono text-[11px] text-muted-foreground">{item.sourceLocator}</p>
      <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{item.conciseExplanation}</p>
      {item.groupInheritanceLabel ? (
        <p
          className="mt-1 text-[11px] font-medium text-foreground/80"
          data-testid="typed-context-group-inheritance"
        >
          {item.groupInheritanceLabel}
        </p>
      ) : item.inheritedViaGroup === false ? (
        <p className="mt-1 text-[11px] text-muted-foreground">Direct relationship</p>
      ) : null}
      <LegalRelationshipExplanation item={item} showDeveloperFields={showDeveloperFields} />
    </li>
  );
}

function TypedLegalContextRoleSection(props: {
  role: TypedLegalContextUiRole;
  items: TypedLegalContextItemView[];
  showDeveloperFields?: boolean;
}): JSX.Element | null {
  const { role, items, showDeveloperFields = false } = props;
  if (items.length === 0) {
    return null;
  }
  const heading = sectionHeadingForTypedRole(role, items.length);
  const sharedGroupLabel =
    items.every((item) => item.groupInheritanceLabel) &&
    new Set(items.map((item) => item.groupInheritanceLabel)).size === 1
      ? items[0]!.groupInheritanceLabel
      : null;

  return (
    <section
      className="space-y-2"
      data-testid={`typed-legal-context-section-${role}`}
      aria-label={heading.title}
    >
      <div>
        <h3 className="text-[13px] font-medium text-foreground">
          {heading.title}
          <span className="ml-1.5 text-[11px] font-normal text-muted-foreground">
            ({items.length})
          </span>
        </h3>
        <p className="mt-1 text-[11px] text-muted-foreground">{heading.description}</p>
        {sharedGroupLabel ? (
          <p className="mt-1 text-[11px] font-medium text-foreground/80">{sharedGroupLabel}</p>
        ) : null}
      </div>
      <ul className="list-none space-y-2">
        {items.map((item) => (
          <TypedLegalContextItem
            key={item.id}
            item={
              sharedGroupLabel
                ? { ...item, groupInheritanceLabel: null }
                : item
            }
            showDeveloperFields={showDeveloperFields}
          />
        ))}
      </ul>
    </section>
  );
}

export function TypedLegalContextSection(props: {
  sections: TypedLegalContextSections;
  showDeveloperFields?: boolean;
}): JSX.Element | null {
  const { sections, showDeveloperFields = false } = props;
  const hasAny =
    sections.applicableExceptions.length > 0 ||
    sections.exceptionTargets.length > 0 ||
    sections.triggerConditions.length > 0;
  if (!hasAny) {
    return null;
  }

  return (
    <div className="space-y-4" data-testid="typed-legal-context">
      <TypedLegalContextRoleSection
        role="exception"
        items={sections.applicableExceptions}
        showDeveloperFields={showDeveloperFields}
      />
      <TypedLegalContextRoleSection
        role="displaced_rule"
        items={sections.exceptionTargets}
        showDeveloperFields={showDeveloperFields}
      />
      <TypedLegalContextRoleSection
        role="trigger"
        items={sections.triggerConditions}
        showDeveloperFields={showDeveloperFields}
      />
    </div>
  );
}
