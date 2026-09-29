import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  analyzeCompositionTracesFromBundle,
  buildCompositionTraceReport,
  type ExportBundle,
} from "@/lib/analyze-composition-traces";
function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf-8")) as T;
}

function loadBundle(exportDir: string, effectiveLawPath?: string): ExportBundle {
  const root = resolve(exportDir);
  let propositionCompleteness: ExportBundle["proposition_completeness_assessments"] = [];
  try {
    propositionCompleteness = readJson(resolve(root, "proposition_completeness_assessments.json"));
  } catch {
    propositionCompleteness = [];
  }
  const effectivePath = effectiveLawPath ?? resolve(root, "effective_law_statements.json");
  return {
    propositions: readJson(resolve(root, "propositions.json")),
    source_fragments: readJson(resolve(root, "source_fragments.json")),
    source_records: readJson(resolve(root, "sources.json")),
    effective_law_statements: readJson(effectivePath),
    proposition_completeness_assessments: propositionCompleteness,
  };
}

export function analyzeCompositionTraces(
  exportDir: string,
  effectiveLawPath?: string,
) {
  const bundle = loadBundle(exportDir, effectiveLawPath);
  return analyzeCompositionTracesFromBundle(exportDir, bundle);
}

export function writeCompositionTraceReport(outputPath: string, report: string): void {
  writeFileSync(outputPath, `${report}\n`, "utf-8");
}

export { buildCompositionTraceReport };
