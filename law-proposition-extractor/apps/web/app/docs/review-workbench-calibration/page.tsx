import { readFileSync } from "node:fs";
import { join } from "node:path";

import Link from "next/link";

function loadCalibrationGuide(): string {
  const guidePath = join(process.cwd(), "../../docs/review-workbench-calibration.md");
  return readFileSync(guidePath, "utf-8");
}

export default function ReviewWorkbenchCalibrationPage(): JSX.Element {
  const content = loadCalibrationGuide();

  return (
    <main className="mx-auto min-h-screen w-full max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-6 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
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
        </div>
        <p className="text-sm text-muted-foreground">
          Calibration guide for structured statement reviews. Read before starting a batch.
        </p>
      </header>

      <article className="rounded-lg border border-border/80 bg-background px-4 py-5 sm:px-6">
        <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-foreground">
          {content}
        </pre>
      </article>
    </main>
  );
}
