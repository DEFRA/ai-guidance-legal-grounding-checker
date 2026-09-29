import { describe, expect, it } from "vitest";

import {
  REPAIR_BANNER_CREDITS_QUOTA_HELPER_TEXT,
  clientRepairableExtractionHintFromExplorerData,
  formatRepairBannerRetryTokenEstimate,
  repairBannerFailureReasonsSentence,
  repairBannerNeedsCreditsQuotaHelper,
  parseJuditExtractionMetaFromNotes,
  textSuggestsRepairableExtractionFailure,
  type UnknownRecord,
} from "./proposition-explorer-helpers";

describe("repairable extraction UI hints", () => {
  it("formats repair banner retry token estimate: missing → unknown, not zero", () => {
    expect(formatRepairBannerRetryTokenEstimate(undefined)).toBe("unknown");
    expect(formatRepairBannerRetryTokenEstimate({})).toBe("unknown");
    expect(
      formatRepairBannerRetryTokenEstimate({
        estimated_retry_tokens: null,
        estimated_retry_token_count: null,
      }),
    ).toBe("unknown");
    expect(
      formatRepairBannerRetryTokenEstimate({
        estimated_retry_tokens: null,
        estimated_retry_token_count: 0,
      }),
    ).toBe("unknown");
  });

  it("formats repair banner retry token estimate when API returns a number", () => {
    expect(
      formatRepairBannerRetryTokenEstimate({ estimated_retry_tokens: 42000 }),
    ).toBe("42,000");
    expect(formatRepairBannerRetryTokenEstimate({ estimated_retry_token_count: 99 })).toBe("99");
  });

  describe("repair banner failure reasons rendering", () => {
    it("returns no sentence when failure_reasons is missing or empty", () => {
      expect(repairBannerFailureReasonsSentence(undefined)).toBeNull();
      expect(repairBannerFailureReasonsSentence([])).toBeNull();
    });

    it("formats compact Reasons line (dedupe credits + quota)", () => {
      expect(
        repairBannerFailureReasonsSentence([
          "quota",
          "insufficient_credits",
          "json_parse_or_llm_failure",
        ]),
      ).toBe("Reasons: credits/quota, JSON parse");
    });

    it("JSON-parse-only failures omit credits/quota helper", () => {
      expect(repairBannerFailureReasonsSentence(["json_parse_or_llm_failure"])).toBe(
        "Reasons: JSON parse",
      );
      expect(repairBannerNeedsCreditsQuotaHelper(["json_parse_or_llm_failure"])).toBe(false);
    });

    it("shows credits helper gate when quota or insufficient_credits is present", () => {
      expect(repairBannerNeedsCreditsQuotaHelper(["quota"])).toBe(true);
      expect(repairBannerNeedsCreditsQuotaHelper(["insufficient_credits"])).toBe(true);
      expect(REPAIR_BANNER_CREDITS_QUOTA_HELPER_TEXT).toContain("Restore provider credits");
      expect(REPAIR_BANNER_CREDITS_QUOTA_HELPER_TEXT).toContain("fail again");
    });
  });

  it("detects quota-like validation text", () => {
    expect(textSuggestsRepairableExtractionFailure("monthly quota exceeded")).toBe(true);
    expect(textSuggestsRepairableExtractionFailure("everything is fine")).toBe(false);
  });

  it("parses judit_extraction_meta line from notes", () => {
    const notes =
      'judit_extraction_meta:{"extraction_mode":"frontier","fallback_used":true,"validation_errors":["quota hit"],"evidence_quote":"x"}\nbody';
    const meta = parseJuditExtractionMetaFromNotes(notes);
    expect(meta?.extraction_mode).toBe("frontier");
    expect(meta?.fallback_used).toBe(true);
  });

  it("returns true for frontier fallback trace with repairable validation_errors", () => {
    const traces: UnknownRecord[] = [
      {
        effective_value: {
          extraction_mode: "frontier",
          extraction_method: "fallback",
          fallback_used: true,
          validation_errors: ["context window exceeded"],
        },
      },
    ];
    expect(clientRepairableExtractionHintFromExplorerData(traces, [])).toBe(true);
  });

  it("returns true when only proposition notes carry meta fallback + infra errors", () => {
    const traces: UnknownRecord[] = [
      {
        effective_value: {
          extraction_mode: "frontier",
          extraction_method: "llm",
          fallback_used: false,
          validation_errors: [],
        },
      },
    ];
    const rows: UnknownRecord[] = [
      {
        original_artifact: {
          notes:
            'judit_extraction_meta:{"extraction_mode":"frontier","fallback_used":true,"validation_errors":["insufficient credits"],"evidence_quote":""}\n',
        },
      },
    ];
    expect(clientRepairableExtractionHintFromExplorerData(traces, rows)).toBe(true);
  });

  it("returns false when no fallback or no repair-like errors", () => {
    const traces: UnknownRecord[] = [
      {
        effective_value: {
          extraction_mode: "frontier",
          extraction_method: "llm",
          fallback_used: false,
          validation_errors: ["policy violation"],
        },
      },
    ];
    expect(clientRepairableExtractionHintFromExplorerData(traces, [])).toBe(false);
  });
});
