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
