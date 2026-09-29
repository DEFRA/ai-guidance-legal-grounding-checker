import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { buildCompositionContext } from "@/lib/export-composition-trace";
import type { LawStatementRow, PropositionRow, StatementQualityAssessment } from "@/lib/law-statements-index";
import {
  buildReviewQueue,
  buildReviewQueueItems,
  buildStatementSamplingContexts,
  countTraceBlockedHardCases,
  deterministicSample,
  findNextUnreviewedQueueItem,
  propositionCountBucket,
  seededRandomUnit,
  stratificationKey,
} from "@/lib/review-workbench-queue";
import { emptyWorkbenchReview } from "@/lib/review-workbench-state";

function statement(
  id: string,
  overrides?: Partial<LawStatementRow>,
): LawStatementRow {
  return {
    id,
    statement_text: `Statement ${id}`,
    presentation_role: "guidance_matching_candidate",
    standalone_status: "standalone",
    confidence: "high",
    source_proposition_ids: [`prop-${id}`],
    supporting_proposition_ids: [],
    required_context: [],
    connector_context: [],
    warnings: [],
    ...overrides,
  };
}

function quality(
  overrides?: Partial<StatementQualityAssessment>,
): StatementQualityAssessment {
  return {
    uniquePropositionCount: 1,
    refCount: 1,
    flags: [],
    issueLabels: [],
    reviewScore: 0,
    ...overrides,
  };
}

describe("review-workbench-queue", () => {
  it("samples deterministically from seed", () => {
    const items = ["a", "b", "c", "d", "e"];
    const first = deterministicSample(items, 2, "seed-1", (item) => item);
    const second = deterministicSample(items, 2, "seed-1", (item) => item);
    const other = deterministicSample(items, 2, "seed-2", (item) => item);

    expect(first).toEqual(second);
    expect(first).toHaveLength(2);
    expect(seededRandomUnit("seed-1", "a")).toBe(seededRandomUnit("seed-1", "a"));
    expect(seededRandomUnit("seed-1", "a")).not.toBe(seededRandomUnit("seed-1", "b"));
    if (other.join() !== first.join()) {
      expect(other).not.toEqual(first);
    }
  });

  it("maps proposition count buckets", () => {
    expect(propositionCountBucket(1)).toBe("1");
    expect(propositionCountBucket(3)).toBe("2-3");
    expect(propositionCountBucket(6)).toBe("4-6");
    expect(propositionCountBucket(9)).toBe("7+");
  });

  it("builds stratified queue items across dimensions", () => {
    const contexts = buildStatementSamplingContexts(
      [
        statement("s-complete-1", { standalone_status: "standalone" }),
        statement("s-incomplete-2", { standalone_status: "fragmentary" }),
        statement("s-matcher-3", { presentation_role: "guidance_matching_candidate" }),
        statement("s-unresolved-4", {
          required_context: [{ resolution_status: "unresolved", proposition_ids: ["p1"] }],
        }),
      ],
      {
        qualityById: new Map([
          ["s-complete-1", quality({ uniquePropositionCount: 1, reviewScore: 1 })],
          ["s-incomplete-2", quality({ uniquePropositionCount: 2, reviewScore: 4 })],
          ["s-matcher-3", quality({ uniquePropositionCount: 4, reviewScore: 3, flags: ["high_composition"] })],
          [
            "s-unresolved-4",
            quality({
              uniquePropositionCount: 7,
              reviewScore: 8,
              flags: ["unresolved_context"],
            }),
          ],
        ]),
        propositionMatcherStatementIds: new Set(["s-matcher-3"]),
        instrumentKeyByPropositionId: new Map([
          ["prop-s-complete-1", "instrument-a"],
          ["prop-s-incomplete-2", "instrument-b"],
          ["prop-s-matcher-3", "instrument-a"],
          ["prop-s-unresolved-4", "instrument-c"],
        ]),
      },
    );

    const items = buildReviewQueueItems(contexts, "stratified_sample", 4, "queue-seed");
    expect(items).toHaveLength(4);
    expect(new Set(items.map((item) => item.statement_id)).size).toBe(4);
    expect(items.every((item) => item.sample_bucket.includes("instrument:"))).toBe(true);
    expect(stratificationKey(contexts[0])).toContain("complete|1|");
  });

  it("prefers needs-review statements in needs_review_mix", () => {
    const contexts = buildStatementSamplingContexts(
      [statement("clean"), statement("flagged")],
      {
        qualityById: new Map([
          ["clean", quality({ reviewScore: 0 })],
          ["flagged", quality({ reviewScore: 9, flags: ["warnings"] })],
        ]),
        propositionMatcherStatementIds: new Set(),
        instrumentKeyByPropositionId: new Map(),
      },
    );

    const items = buildReviewQueueItems(contexts, "needs_review_mix", 1, "mix-seed");
    expect(items[0]?.statement_id).toBe("flagged");
    expect(items[0]?.sample_bucket).toBe("needs_review");
  });

  it("builds a priority-ranked trace-blocked hard case queue from export", () => {
    const exportDir = process.env.TRACE_BLOCKED_HARD_CASES_EXPORT_DIR;
    if (!exportDir) {
      return;
    }

    const root = resolve(exportDir);
    const input = {
      propositions: JSON.parse(readFileSync(resolve(root, "propositions.json"), "utf-8")) as PropositionRow[],
      source_fragments: JSON.parse(readFileSync(resolve(root, "source_fragments.json"), "utf-8")),
      source_records: JSON.parse(readFileSync(resolve(root, "sources.json"), "utf-8")),
      effective_law_statements: JSON.parse(
        readFileSync(resolve(root, "effective_law_statements.json"), "utf-8"),
      ),
    };
    const statements = input.effective_law_statements.statements ?? [];
    const compositionContext = buildCompositionContext(input);
    const instrumentKeyByPropositionId = new Map(
      input.propositions.map((row) => [row.id, row.source_record_id ?? "__unknown_instrument__"]),
    );
    const contexts = buildStatementSamplingContexts(statements, {
      qualityById: new Map(),
      propositionMatcherStatementIds: new Set(),
      instrumentKeyByPropositionId,
      compositionContext,
    });

    expect(countTraceBlockedHardCases(contexts)).toBeGreaterThan(0);

    const items = buildReviewQueueItems(contexts, "trace_blocked_hard_cases", 5, "hard-case-seed");
    expect(items.length).toBeGreaterThan(0);
    expect(items.every((item) => item.trace_metadata != null)).toBe(true);
    for (let index = 1; index < items.length; index += 1) {
      expect(items[index - 1]!.priority_score).toBeGreaterThanOrEqual(items[index]!.priority_score);
    }
  });

  it("finds next unreviewed queue item after current", () => {
    const queue = buildReviewQueue(
      "run-1",
      ["a", "b", "c"],
      buildStatementSamplingContexts(
        [statement("a"), statement("b"), statement("c")],
        {
          qualityById: new Map([
            ["a", quality()],
            ["b", quality()],
            ["c", quality()],
          ]),
          propositionMatcherStatementIds: new Set(),
          instrumentKeyByPropositionId: new Map(),
          reviews: {
            a: { ...emptyWorkbenchReview(), verdicts: ["accurate"] },
            b: { ...emptyWorkbenchReview(), verdicts: ["accurate"] },
          },
        },
      ),
      "random_sample",
      3,
      "seed",
    );

    expect(findNextUnreviewedQueueItem(queue, "a")?.statement_id).toBe("c");
    expect(findNextUnreviewedQueueItem(queue)?.statement_id).toBe("c");
  });
});
