import type {
  CompositionTraceSpan,
  ContextIncorporationEntry,
  LawStatementRow,
} from "@/lib/law-statements-index";
import { INCORPORATION_BADGE_LABEL } from "@/lib/composition-trace-segments";

const BADGE_CLASS = {
  should_inline: "border-sky-700/35 bg-sky-950/10 text-sky-950 dark:text-sky-100",
  should_split: "border-violet-700/35 bg-violet-950/10 text-violet-950 dark:text-violet-100",
  reviewer_required: "border-amber-700/35 bg-amber-950/10 text-amber-950 dark:text-amber-100",
  external_context: "border-zinc-600/35 bg-zinc-500/10 text-foreground/85",
} as const;

function IncorporationBadge(props: {
  kind: keyof typeof INCORPORATION_BADGE_LABEL;
}): JSX.Element {
  return (
    <span
      className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${BADGE_CLASS[props.kind]}`}
    >
      {INCORPORATION_BADGE_LABEL[props.kind]}
    </span>
  );
}

function badgesForIncorporation(
  incorporation: CompositionTraceSpan["incorporation"] | ContextIncorporationEntry["incorporation"],
): Array<keyof typeof INCORPORATION_BADGE_LABEL> {
  const badges: Array<keyof typeof INCORPORATION_BADGE_LABEL> = [];
  if (incorporation.should_inline) {
    badges.push("should_inline");
  }
  if (incorporation.should_split) {
    badges.push("should_split");
  }
  if (incorporation.reviewer_required) {
    badges.push("reviewer_required");
  }
  if (incorporation.external_context) {
    badges.push("external_context");
  }
  return badges;
}

export function StatementIncorporationPanels(props: {
  statement: LawStatementRow;
}): JSX.Element | null {
  const { statement } = props;
  const contextIncorporation = statement.context_incorporation ?? [];
  const trace = statement.composition_trace ?? [];

  if (contextIncorporation.length === 0 && trace.length === 0) {
    return null;
  }

  const externalEntries = contextIncorporation.filter(
    (entry) => entry.incorporation.external_context,
  );
  const incorporationCandidates = contextIncorporation.filter(
    (entry) =>
      entry.incorporation.should_inline ||
      entry.incorporation.should_split ||
      entry.incorporation.reviewer_required,
  );

  const traceBadges = {
    should_inline: trace.some((span) => span.incorporation.should_inline),
    should_split: trace.some((span) => span.incorporation.should_split),
    reviewer_required: trace.some((span) => span.incorporation.reviewer_required),
  };

  return (
    <div className="mt-4 grid gap-3 md:grid-cols-2">
      <section className="rounded-lg border border-border/80 bg-muted/[0.08] px-3 py-3">
        <p className="text-[12px] font-medium text-foreground">External context</p>
        <p className="mt-1 text-[11px] text-muted-foreground">
          Required context kept outside statement wording.
        </p>
        {externalEntries.length === 0 ? (
          <p className="mt-2 text-[11px] italic text-muted-foreground">None flagged.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {externalEntries.map((entry) => (
              <li key={entry.locator} className="rounded border border-border/70 px-2 py-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[11px]">{entry.locator}</span>
                  <span className="text-[10px] text-muted-foreground">{entry.material_role}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {badgesForIncorporation(entry.incorporation).map((badge) => (
                    <IncorporationBadge key={badge} kind={badge} />
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-lg border border-border/80 bg-muted/[0.08] px-3 py-3">
        <p className="text-[12px] font-medium text-foreground">Should be incorporated?</p>
        <p className="mt-1 text-[11px] text-muted-foreground">
          Material context not yet reflected in statement text.
        </p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {traceBadges.should_inline ? <IncorporationBadge kind="should_inline" /> : null}
          {traceBadges.should_split ? <IncorporationBadge kind="should_split" /> : null}
          {traceBadges.reviewer_required ? <IncorporationBadge kind="reviewer_required" /> : null}
        </div>
        {incorporationCandidates.length === 0 ? (
          <p className="mt-2 text-[11px] italic text-muted-foreground">No incorporation actions.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {incorporationCandidates.map((entry) => (
              <li key={entry.locator} className="rounded border border-border/70 px-2 py-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[11px]">{entry.locator}</span>
                  <span className="text-[10px] text-muted-foreground">{entry.material_role}</span>
                  {!entry.incorporation.included_in_text ? (
                    <span className="text-[10px] text-amber-800 dark:text-amber-200">not in text</span>
                  ) : null}
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {badgesForIncorporation(entry.incorporation).map((badge) => (
                    <IncorporationBadge key={badge} kind={badge} />
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
