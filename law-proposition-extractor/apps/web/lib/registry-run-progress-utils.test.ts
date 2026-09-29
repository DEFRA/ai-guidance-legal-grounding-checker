import { describe, expect, it } from "vitest";

import {
  getStageDisplayStatus,
  isStageLevelTerminalEvent,
  latestStageOutcomes,
  stageStatusSymbol,
} from "./registry-run-progress-utils";

describe("registry-run-progress-utils", () => {
  it("stageStatusSymbol maps statuses", () => {
    expect(stageStatusSymbol("pass")).toBe("ok");
    expect(stageStatusSymbol("warning")).toBe("warn");
    expect(stageStatusSymbol("fail")).toBe("fail");
    expect(stageStatusSymbol("running")).toBe("run");
  });

  it("isStageLevelTerminalEvent treats proposition_extraction pass without duration as sub-step", () => {
    expect(
      isStageLevelTerminalEvent({
        stage: "proposition_extraction",
        status: "pass",
        message: "Finished extracting source x",
      })
    ).toBe(false);
    expect(
      isStageLevelTerminalEvent({
        stage: "proposition_extraction",
        status: "pass",
        duration_ms: 1200,
      })
    ).toBe(true);
    expect(
      isStageLevelTerminalEvent({ stage: "source_intake", status: "pass", duration_ms: 10 })
    ).toBe(true);
  });

  it("latestStageOutcomes keeps last stage-level event per stage and ignores per-source extraction rows", () => {
    const events = [
      { sequence_number: 1, stage: "source_intake", status: "pass", duration_ms: 10 },
      { sequence_number: 2, stage: "source_intake", status: "running" },
      { sequence_number: 3, stage: "source_intake", status: "pass", duration_ms: 20 },
    ];
    const m = latestStageOutcomes(events);
    expect(m.get("source_intake")?.duration_ms).toBe(20);
  });

  it("latestStageOutcomes does not use per-source proposition_extraction pass as stage outcome", () => {
    const events = [
      {
        sequence_number: 1,
        stage: "proposition_extraction",
        status: "pass",
        message: "Finished extracting source abc",
      },
    ];
    expect(latestStageOutcomes(events).has("proposition_extraction")).toBe(false);
  });

  it("getStageDisplayStatus maps stage-level outcomes and job position", () => {
    expect(
      getStageDisplayStatus({
        slug: "source_intake",
        stageLevelOutcome: { status: "pass", duration_ms: 1 },
        currentStage: "source_parsing",
        runStatus: "running",
      })
    ).toBe("complete");

    expect(
      getStageDisplayStatus({
        slug: "source_parsing",
        stageLevelOutcome: undefined,
        currentStage: "source_parsing",
        runStatus: "running",
      })
    ).toBe("running");

    expect(
      getStageDisplayStatus({
        slug: "export_bundle",
        stageLevelOutcome: undefined,
        currentStage: "source_intake",
        runStatus: "running",
      })
    ).toBe("not_started");

    expect(
      getStageDisplayStatus({
        slug: "source_intake",
        stageLevelOutcome: undefined,
        currentStage: null,
        runStatus: "queued",
      })
    ).toBe("pending");

    expect(
      getStageDisplayStatus({
        slug: "source_intake",
        stageLevelOutcome: { status: "skipped", duration_ms: 0 },
        currentStage: "source_parsing",
        runStatus: "running",
      })
    ).toBe("skipped");

    expect(
      getStageDisplayStatus({
        slug: "source_intake",
        stageLevelOutcome: { status: "warning", duration_ms: 1 },
        currentStage: null,
        runStatus: "warning",
      })
    ).toBe("warning");
  });

  it("getStageDisplayStatus: current running stage wins over stage-level pass (stale snapshot)", () => {
    expect(
      getStageDisplayStatus({
        slug: "source_intake",
        stageLevelOutcome: { status: "pass", duration_ms: 10 },
        currentStage: "source_intake",
        runStatus: "running",
      })
    ).toBe("running");
  });

  it("getStageDisplayStatus: proposition extraction running while per-source events exist", () => {
    expect(
      getStageDisplayStatus({
        slug: "proposition_extraction",
        stageLevelOutcome: undefined,
        currentStage: "proposition_extraction",
        runStatus: "running",
      })
    ).toBe("running");
  });

  it("getStageDisplayStatus: stage-level fail before running check", () => {
    expect(
      getStageDisplayStatus({
        slug: "source_parsing",
        stageLevelOutcome: { status: "fail", duration_ms: 1 },
        currentStage: "source_parsing",
        runStatus: "running",
      })
    ).toBe("failed");
  });
});
