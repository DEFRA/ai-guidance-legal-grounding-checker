import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  analyzeTraceBlockedHardCasesFromInput,
  buildTraceBlockedHardCasesReport,
} from "@/lib/analyze-trace-blocked-hard-cases";
import {
  type CompositionTraceExportInput,
} from "@/lib/export-composition-trace";

function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf-8")) as T;
}

function loadExportInput(exportDir: string, effectiveLawPath?: string): CompositionTraceExportInput {
  const root = resolve(exportDir);
  const effectivePath = effectiveLawPath ?? resolve(root, "effective_law_statements.json");
  const input: CompositionTraceExportInput = {
    propositions: readJson(resolve(root, "propositions.json")),
    source_fragments: readJson(resolve(root, "source_fragments.json")),
    source_records: readJson(resolve(root, "sources.json")),
    effective_law_statements: readJson(effectivePath),
  };
  try {
    input.proposition_completeness_assessments = readJson(
      resolve(root, "proposition_completeness_assessments.json"),
    );
  } catch {
    input.proposition_completeness_assessments = [];
  }
  return input;
}

function buildInstrumentKeyByPropositionId(
  input: CompositionTraceExportInput,
): Map<string, string> {
  const sourceById = new Map((input.source_records ?? []).map((row) => [row.id, row]));
  const map = new Map<string, string>();
  for (const proposition of input.propositions) {
    const source = proposition.source_record_id
      ? sourceById.get(proposition.source_record_id)
      : undefined;
    const citation = String(source?.citation ?? "").trim();
    const title = String(source?.title ?? "").trim();
    map.set(proposition.id, citation || title || "__unknown_instrument__");
  }
  return map;
}

export function analyzeTraceBlockedHardCases(
  exportDir: string,
  effectiveLawPath?: string,
) {
  const input = loadExportInput(exportDir, effectiveLawPath);
  const instrumentKeyByPropositionId = buildInstrumentKeyByPropositionId(input);
  return analyzeTraceBlockedHardCasesFromInput(exportDir, input, instrumentKeyByPropositionId);
}

export function writeTraceBlockedHardCasesReport(outputPath: string, report: string): void {
  writeFileSync(outputPath, `${report}\n`, "utf-8");
}

export { buildTraceBlockedHardCasesReport };
