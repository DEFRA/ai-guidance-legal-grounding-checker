import Link from "next/link";

import { ReviewAnalysisPanel } from "@/components/review-analysis-panel";

export default function ReviewAnalysisPage(): JSX.Element {
  return (
    <main className="mx-auto min-h-screen w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-6 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-3xl font-semibold tracking-tight">Review analysis</h1>
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
            <span className="rounded border border-priguidance-discovery/70 bg-priguidance-discovery/[0.12] px-2 py-1 text-[11px] font-medium text-primary">
              Review analysis
            </span>
            <Link
              href="/ops"
              className="rounded border border-border/80 bg-background px-2 py-1 text-[11px] font-medium text-foreground/80 hover:bg-accent/50"
            >
              Operations / Registry
            </Link>
          </div>
        </div>
        <p className="text-sm text-muted-foreground">
          Import exported review JSON (v3) and optional queue manifest JSON to summarise verdict
          rates, failure patterns, and Proposition Matcher candidate proxies. All processing happens in the
          browser.{" "}
          <Link
            href="/docs/review-workbench-calibration"
            className="font-medium text-primary underline-offset-2 hover:underline"
          >
            Calibration guide
          </Link>
        </p>
      </header>

      <ReviewAnalysisPanel />
    </main>
  );
}
