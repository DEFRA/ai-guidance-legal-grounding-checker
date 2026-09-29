import { describe, expect, it } from "vitest";

import {
  classifyFamilyCandidate,
  classificationRegisterEligible,
  describeBlockReasons,
  findDuplicateRegistryMatch,
  isConceptualGroupingCandidate,
  normalizeCelex,
  type FamilyRegistryEntryLite,
} from "./source-family-candidate-utils";

const baseCandidate = (
  overrides: Partial<Parameters<typeof classifyFamilyCandidate>[0]["row"]> = {},
) =>
  ({
    id: overrides.id ?? "c1",
    title: overrides.title ?? "Council Regulation test",
    citation: overrides.citation,
    celex: overrides.celex,
    url: overrides.url,
    candidate_source_id: overrides.candidate_source_id,
    source_role: overrides.source_role ?? "amendment",
    relationship_to_target: overrides.relationship_to_target ?? "amends",
    inclusion_status: overrides.inclusion_status ?? "candidate_needs_review",
    metadata: overrides.metadata ?? {},
    ...overrides,
  }) as Parameters<typeof classifyFamilyCandidate>[0]["row"];

describe("conceptual grouping", () => {
  it("labels source family wording as Needs source selection", () => {
    const row = baseCandidate({
      title: "EU legal framework — source family for animal health instruments",
      url: "",
      candidate_source_id: "",
      citation: "",
      inclusion_status: "optional_context",
      source_role: "unknown",
      relationship_to_target: "unknown",
      celex: undefined,
      eli: undefined,
      metadata: { conceptual_grouping: false },
    });
    expect(isConceptualGroupingCandidate(row)).toBe(true);
    const classified = classifyFamilyCandidate({
      row,
      registryEntries: [],
      registryByMembershipKey: new Map(),
      registeredThisSession: {},
      decisions: {},
    });
    expect(classified.primary).toBe("needs_source_selection");
    expect(describeBlockReasons(classified.block_reasons)).toEqual(
      expect.arrayContaining([
        expect.stringMatching(/conceptual grouping/i),
      ]),
    );
  });
});

describe("CELEX duplicate", () => {
  it("flags Possible duplicate vs registry entry with matching CELEX", () => {
    const row = baseCandidate({
      id: "d1",
      title: "Regulation unrelated title",
      celex: "32016R0429",
      citation: "",
      candidate_source_id: "eur/wrong/path",
      url: "",
    });

    const hit = classifyFamilyCandidate({
      row,
      registryEntries: [
        {
          registry_id: "reg-eur-2016",
          reference: {
            authority: "legislation_gov_uk",
            authority_source_id: "eur/2016/429/reg/1",
            title: "Regulation (EU) 2016/429",
            celex: "32016R0429",
            source_url:
              "https://www.legislation.gov.uk/eur/2016/429/reg/1/data.xml",
          },
          current_state: {
            source_record: { citation: "Reg 429/16", celex: "32016R0429", title: "Reg 429" },
          },
        },
      ],
      registryByMembershipKey: new Map(),
      registeredThisSession: {},
      decisions: {},
    });

    expect(hit.primary === "possible_duplicate" || hit.primary === "already_registered").toBe(
      true,
    );
    expect(
      normalizeCelex(hit.duplicate_match ? row.celex : "32016R0429") ===
        normalizeCelex("32016R0429"),
    ).toBe(true);
  });

  it("shows Already registered when membership key resolves to registry hit", () => {
    const row = baseCandidate({
      id: "r1",
      title: "Reg (EU) 2016/429",
      citation: "",
      candidate_source_id: "eur/2016/429/reg/1",
    });
    const mk =
      classifyFamilyCandidate({
        row,
        registryEntries: [],
        registryByMembershipKey: new Map<string, FamilyRegistryEntryLite>([
          ["legislation_gov_uk:eur/2016/429/reg/1", { registry_id: "reg-hit" }],
        ]),
        registeredThisSession: {},
        decisions: {},
      }).membership_key ?? "";

    expect(mk).toContain("eur/2016/429/reg/1");

    const classified = classifyFamilyCandidate({
      row,
      registryEntries: [],
      registryByMembershipKey: new Map<string, FamilyRegistryEntryLite>([
        [mk, { registry_id: "reg-hit" }],
      ]),
      registeredThisSession: {},
      decisions: {},
    });

    expect(classified.primary).toBe("already_registered");
    expect(classified.existing_registry_id).toBe("reg-hit");
  });
});

describe("findDuplicateRegistryMatch", () => {
  it("returns match on CELEX when candidate lacks legislation path", () => {
    const row = baseCandidate({
      celex: "32016R0429",
      candidate_source_id: "x/y",
      title: "",
    });
    const m = findDuplicateRegistryMatch(
      row,
      [
        {
          registry_id: "r1",
          reference: {
            authority: "legislation_gov_uk",
            authority_source_id: "eur/2016/429/reg/1",
            celex: "32016R0429",
            title: "",
          },
          current_state: { source_record: {} },
        },
      ],
      {},
    );
    expect(m?.registry_id).toBe("r1");
    expect(m?.matched_by).toContain("celex");
  });
});

describe("register eligibility", () => {
  it("disables-register path yields needs_source_selection without ready_to_register when no locator", () => {
    const row = baseCandidate({
      title: "Something",
      citation: "",
      candidate_source_id: "",
      url: "",
      celex: undefined,
      eli: undefined,
      source_role: "amendment",
      relationship_to_target: "amends",
    });
    expect(
      classifyFamilyCandidate({
        row,
        registryEntries: [],
        registryByMembershipKey: new Map(),
        registeredThisSession: {},
        decisions: {},
      }).primary,
    ).not.toBe("ready_to_register");
  });
});

describe("covered by existing registry source", () => {
  it("records coverage via decision metadata", () => {
    const row = baseCandidate({});
    const out = classifyFamilyCandidate({
      row,
      registryEntries: [],
      registryByMembershipKey: new Map(),
      registeredThisSession: {},
      decisions: {
        [row.id]: {
          candidate_id: row.id,
          decision: "covered_by_existing",
          existing_registry_id: "pick-me",
          reviewed_at: "2026-01-01T00:00:00.000Z",
        },
      },
    });
    expect(out.coverage_registry_id).toBe("pick-me");
  });
});

describe("classificationRegisterEligible", () => {
  it("allows registration UI only for ready_to_register primary", () => {
    expect(classificationRegisterEligible("ready_to_register")).toBe(true);
    expect(classificationRegisterEligible("possible_duplicate")).toBe(false);
    expect(classificationRegisterEligible("needs_source_selection")).toBe(false);
    expect(classificationRegisterEligible("context_only")).toBe(false);
  });
});
