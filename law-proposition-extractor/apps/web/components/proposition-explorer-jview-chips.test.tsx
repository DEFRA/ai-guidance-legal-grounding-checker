import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockReplace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: (): { replace: typeof mockReplace } => ({
    replace: mockReplace,
  }),
  useSearchParams: (): URLSearchParams => new URLSearchParams(),
}));

import { PropositionExplorer } from "./proposition-explorer";

describe("PropositionExplorer jurisdiction view chips", () => {
  beforeEach(() => {
    mockReplace.mockReset();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        if (url.includes("/ops/runs")) {
          return new Response(JSON.stringify({ runs: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response("not found", { status: 404 });
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("clicking EU only uses router.replace only and does not POST run/extraction endpoints", async () => {
    render(<PropositionExplorer />);

    await waitFor(() => {
      expect(vi.mocked(fetch)).toHaveBeenCalled();
    });

    vi.mocked(fetch).mockClear();
    mockReplace.mockClear();

    screen.getByRole("button", { name: /EU only/i }).click();

    expect(mockReplace).toHaveBeenCalledWith("/propositions?jview=eu", { scroll: false });

    for (const call of vi.mocked(fetch).mock.calls) {
      const req = call[0];
      const url =
        typeof req === "string" ? req : req instanceof Request ? req.url : String(req);
      expect(url).not.toMatch(/\/ops\/run-jobs\/from-registry/);
      expect(url).not.toMatch(/\/ops\/run-jobs\/repair-extraction/);
      expect(url).not.toMatch(/\/ops\/run-jobs\/compare-proposition-datasets/);
      if (req instanceof Request) {
        expect(req.method).toBe("GET");
      }
    }
  });
});
