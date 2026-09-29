import Link from "next/link";

import { OperationsInspector } from "@/components/operations-inspector";

export default function OperationsPage(): JSX.Element {
  return (
    <main className="mx-auto min-h-screen w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-6 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-3xl font-semibold tracking-tight">Operations / registry</h1>
          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="rounded border border-border/80 bg-background px-2 py-1 text-[11px] font-medium text-foreground/80 hover:bg-accent/50"
            >
              Analysis workbench
            </Link>
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
            <span className="rounded border border-priguidance-discovery/70 bg-priguidance-discovery/[0.12] px-2 py-1 text-[11px] font-medium text-primary">
              Operations
            </span>
          </div>
        </div>
        <p className="text-sm text-muted-foreground">
          Read-only operational surface for run inspection and source registry workflows.
        </p>
      </header>
      <OperationsInspector />
    </main>
  );
}
