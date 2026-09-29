import Link from "next/link";

import { LawStatementsExplorer } from "@/components/law-statements-explorer";

export default function StatementsPage(): JSX.Element {
  return (
    <div className="rw-frame">
      <header className="rw-nav">
        <div className="mx-auto flex w-full max-w-[1200px] flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-6 lg:px-8">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-navy-foreground">
              Review workbench
            </h1>
            <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-navy-foreground/70">
              Structured evaluation of sampled effective law statements. Use j/k or arrow keys to
              move between statements.
            </p>
          </div>
          <nav className="flex flex-wrap items-center gap-2">
            <Link href="/" className="rw-nav-link">
              Analysis workbench
            </Link>
            <Link href="/propositions" className="rw-nav-link">
              Propositions
            </Link>
            <span className="rw-nav-link-active rounded px-2 py-1 text-[11px] font-medium">
              Review workbench
            </span>
            <Link href="/review-analysis" className="rw-nav-link">
              Review analysis
            </Link>
            <Link href="/ops" className="rw-nav-link">
              Operations / Registry
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6 lg:px-8">
        <p className="mb-5 text-sm text-muted-foreground">
          Structured evaluation of sampled effective law statements from{" "}
          <code className="font-mono text-xs">effective_law_statements.json</code>. Review via the
          provenance journey (law → propositions → statement → verdict), persist assessments locally,
          and export evaluation JSON.{" "}
          <Link
            href="/docs/review-workbench-calibration"
            className="font-medium text-navy underline-offset-2 hover:underline"
          >
            Calibration guide
          </Link>
        </p>

        <LawStatementsExplorer />
      </main>
    </div>
  );
}
