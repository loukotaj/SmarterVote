import { describe, expect, it } from "vitest";
import { matchesSearchQuery } from "./search";

describe("matchesSearchQuery", () => {
  it("matches words regardless of their order in a race title", () => {
    expect(
      matchesSearchQuery("Texas Senate", "2026 U.S. Senate election in Texas"),
    ).toBe(true);
  });

  it("matches a candidate using candidate and race fields together", () => {
    expect(
      matchesSearchQuery(
        "Talarico Texas",
        "James Talarico",
        "Democratic",
        "2026 U.S. Senate election in Texas",
      ),
    ).toBe(true);
  });

  it("normalizes punctuation and accents", () => {
    expect(matchesSearchQuery("Jose US", "José", "U.S. House")).toBe(true);
  });

  it("does not match short terms inside unrelated words", () => {
    expect(matchesSearchQuery("US", "State House")).toBe(false);
  });

  it("requires every query term", () => {
    expect(matchesSearchQuery("Texas Florida", "Texas Senate")).toBe(false);
  });
});

describe("state abbreviation search", () => {
  it("matches a race by its two-letter state code", () => {
    expect(
      matchesSearchQuery("tx senate", "2026 U.S. Senate election in Texas"),
    ).toBe(true);
  });

  it("expands multi-word states", () => {
    expect(
      matchesSearchQuery("nh", "2026 U.S. Senate election in New Hampshire"),
    ).toBe(true);
  });

  it("still matches the full state name", () => {
    expect(
      matchesSearchQuery("texas senate", "2026 U.S. Senate election in Texas"),
    ).toBe(true);
  });

  it("does not let an abbreviation match an unrelated state", () => {
    expect(
      matchesSearchQuery("tx", "2026 U.S. Senate election in Georgia"),
    ).toBe(false);
  });

  it("requires every term, so a wrong state code fails the whole query", () => {
    expect(
      matchesSearchQuery("tx governor", "2026 Georgia gubernatorial election"),
    ).toBe(false);
  });
});
