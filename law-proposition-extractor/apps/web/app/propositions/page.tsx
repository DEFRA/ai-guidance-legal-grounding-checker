import Link from "next/link";

import { PropositionExplorer } from "@/components/proposition-explorer";

export default function PropositionsPage(): JSX.Element {
  return (
    <main className="mx-auto min-h-screen w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-6 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-3xl font-semibold tracking-tight">Propositions</h1>
          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="rounded border border-border/80 bg-background px-2 py-1 text-[11px] font-medium text-foreground/80 hover:bg-accent/50"
            >
              Analysis workbench
            </Link>
            <span className="rounded border border-priguidance-discovery/70 bg-priguidance-discovery/[0.12] px-2 py-1 text-[11px] font-medium text-primary">
              Propositions
            </span>
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
        <p className="text-sm text-muted-foreground">
          Review extracted pipeline propositions (analysis run output / proposition datasets). Use view
          filters to inspect existing proposition datasets or comparison outputs (display only — no
          extraction). Pipeline review controls append to{" "}
          <code className="font-mono text-xs">pipeline_review_decisions.json</code> for the export
          directory your API serves.
        </p>
      </header>

      <PropositionExplorer />
    </main>
  );
}
