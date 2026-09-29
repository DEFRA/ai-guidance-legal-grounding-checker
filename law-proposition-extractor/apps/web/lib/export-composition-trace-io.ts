import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  analyzeExportCompositionTraceFromInput,
  buildExportCompositionTraceReport,
  type CompositionTraceExportInput,
} from "@/lib/export-composition-trace";

function loadExportInput(exportDir: string, effectiveLawPath?: string): CompositionTraceExportInput {
  const root = resolve(exportDir);
  const effectivePath = effectiveLawPath ?? resolve(root, "effective_law_statements.json");
  const input: CompositionTraceExportInput = {
    propositions: JSON.parse(readFileSync(resolve(root, "propositions.json"), "utf-8")),
    source_fragments: JSON.parse(readFileSync(resolve(root, "source_fragments.json"), "utf-8")),
    source_records: JSON.parse(readFileSync(resolve(root, "sources.json"), "utf-8")),
    effective_law_statements: JSON.parse(readFileSync(effectivePath, "utf-8")),
  };
  try {
    input.proposition_completeness_assessments = JSON.parse(
      readFileSync(resolve(root, "proposition_completeness_assessments.json"), "utf-8"),
    );
  } catch {
    input.proposition_completeness_assessments = [];
  }
  return input;
}

export function analyzeExportCompositionTrace(
  exportDir: string,
  effectiveLawPath?: string,
) {
  const input = loadExportInput(exportDir, effectiveLawPath);
  return analyzeExportCompositionTraceFromInput(exportDir, input);
}

export function writeExportCompositionTraceReport(outputPath: string, report: string): void {
  writeFileSync(outputPath, `${report}\n`, "utf-8");
}

export { buildExportCompositionTraceReport };
