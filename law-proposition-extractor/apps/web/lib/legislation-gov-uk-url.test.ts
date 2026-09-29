import { describe, expect, it } from "vitest";

import {
  legislationDocumentBaseUrl,
  legislationContextCrumbs,
  legislationProvisionUrl,
  provisionPathFromLocator,
} from "@/lib/legislation-gov-uk-url";

describe("legislation-gov-uk-url", () => {
  it("strips data.xml and rejects non-legislation hosts", () => {
    expect(
      legislationDocumentBaseUrl("https://www.legislation.gov.uk/eur/2013/1380/data.xml"),
    ).toBe("https://www.legislation.gov.uk/eur/2013/1380");
    expect(legislationDocumentBaseUrl("https://example.com/eur/2013/1380/data.xml")).toBeNull();
  });

  it("maps canonical locators to provision paths", () => {
    expect(provisionPathFromLocator("article:10")).toBe("/article/10");
    expect(provisionPathFromLocator("article:10:paragraph:1")).toBe("/article/10/1");
    expect(provisionPathFromLocator("article:109:list:1-d-i")).toBe("/article/109");
    expect(provisionPathFromLocator("schedule:1:paragraph:2")).toBe("/schedule/1/paragraph/2");
    expect(provisionPathFromLocator("regulation:4:paragraph:1")).toBe("/regulation/4/1");
    expect(provisionPathFromLocator("annex:ii")).toBe("/annex/II");
  });

  it("maps free-text locators", () => {
    expect(provisionPathFromLocator("Article 1(1)")).toBe("/article/1/1");
    expect(provisionPathFromLocator("regulation 4(1)")).toBe("/regulation/4/1");
    expect(provisionPathFromLocator("Schedule 1 paragraph 2")).toBe("/schedule/1/paragraph/2");
  });

  it("builds full provision URLs and falls back to instrument root", () => {
    expect(
      legislationProvisionUrl(
        "https://www.legislation.gov.uk/eur/2013/1380/data.xml",
        "article:5:paragraph:1",
      ),
    ).toBe("https://www.legislation.gov.uk/eur/2013/1380/article/5/1");

    expect(
      legislationProvisionUrl(
        "https://www.legislation.gov.uk/ukpga/2020/22/data.xml",
        "not a locator",
      ),
    ).toBe("https://www.legislation.gov.uk/ukpga/2020/22");
  });

  it("builds hierarchical context crumbs with links at each level", () => {
    expect(
      legislationContextCrumbs({
        sourceUrl: "https://www.legislation.gov.uk/eur/2013/1380/data.xml",
        instrumentLabel: "2013/1380 — CFP",
        locator: "article:5:paragraph:1",
      }),
    ).toEqual([
      {
        label: "2013/1380 — CFP",
        href: "https://www.legislation.gov.uk/eur/2013/1380",
      },
      {
        label: "Article 5",
        href: "https://www.legislation.gov.uk/eur/2013/1380/article/5",
      },
      {
        label: "Paragraph 1",
        href: "https://www.legislation.gov.uk/eur/2013/1380/article/5/1",
      },
    ]);
  });
});
