import { describe, expect, it } from "vitest";

import {
  addReferenceToWorkspace,
  removeReferenceFromWorkspace,
  resolveWorkspaceReferences,
  selectedReferenceAfterRemoval,
} from "./legal-context-workspace";

describe("legal-context-workspace", () => {
  it("adds a reference without replacing existing workspace entries", () => {
    expect(addReferenceToWorkspace(["a"], "b")).toEqual(["a", "b"]);
    expect(addReferenceToWorkspace(["a", "b"], "a")).toEqual(["a", "b"]);
  });

  it("removes a reference from the workspace", () => {
    expect(removeReferenceFromWorkspace(["a", "b", "c"], "b")).toEqual(["a", "c"]);
  });

  it("selects the previous workspace entry when the selected card is removed", () => {
    expect(selectedReferenceAfterRemoval(["a", "b", "c"], "c", "c")).toBe("b");
    expect(selectedReferenceAfterRemoval(["a", "b"], "a", "b")).toBe("b");
    expect(selectedReferenceAfterRemoval(["a"], "a", "a")).toBeNull();
  });

  it("keeps the current selection when removing a different card", () => {
    expect(selectedReferenceAfterRemoval(["a", "b", "c"], "a", "c")).toBe("c");
  });

  it("resolves workspace references in insertion order", () => {
    const referencesById = new Map([
      ["a", { id: "a", label: "Schedule 3" }],
      ["b", { id: "b", label: "Regulation 36(4)" }],
    ]);

    expect(resolveWorkspaceReferences(["a", "b"], referencesById)).toEqual([
      { id: "a", label: "Schedule 3" },
      { id: "b", label: "Regulation 36(4)" },
    ]);
  });
});
