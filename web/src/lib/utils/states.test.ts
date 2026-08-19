import { describe, expect, it } from "vitest";
import { canonicalRaceState } from "./states";

describe("canonicalRaceState", () => {
  it("expands state abbreviations", () => {
    expect(canonicalRaceState({ id: "ca-senate-2026", state: "CA" })).toBe(
      "California",
    );
  });

  it("preserves canonical state names", () => {
    expect(
      canonicalRaceState({ id: "nh-senate-2026", state: "New Hampshire" }),
    ).toBe("New Hampshire");
  });

  it("recovers from a district label using the race id", () => {
    expect(
      canonicalRaceState({
        id: "ut-house-04-2026",
        state: "Utah's 4th Congressional District",
        jurisdiction: "Utah's 4th Congressional District",
      }),
    ).toBe("Utah");
  });

  it("uses a recognized jurisdiction when state is absent", () => {
    expect(
      canonicalRaceState({ id: "ks-senate-2026", jurisdiction: "Kansas" }),
    ).toBe("Kansas");
  });
});
