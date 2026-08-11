import { describe, expect, it } from "vitest";
import {
  raceDisplayTitle,
  raceMetaDescription,
  racePageTitle,
} from "./raceTitle";

describe("raceDisplayTitle", () => {
  it("normalizes Senate titles and special elections", () => {
    expect(
      raceDisplayTitle({
        id: "ga-senate-2026",
        title: "old",
        office: "United States Senate",
        state: "Georgia",
      }),
    ).toBe("2026 Georgia U.S. Senate Election");
    expect(
      raceDisplayTitle({
        id: "fl-senate-2026-special",
        title: "old",
        office: "U.S. Senate",
        state: "Florida",
      }),
    ).toBe("2026 Florida U.S. Senate Special Election");
  });

  it("normalizes House and governor titles", () => {
    expect(
      raceDisplayTitle({
        id: "ga-house-10-2026",
        title: "old",
        office: "U.S. House of Representatives",
        state: "Georgia",
      }),
    ).toBe("2026 Georgia's 10th Congressional District Election");
    expect(
      raceDisplayTitle({
        id: "wa-01-house-2026",
        title: "old",
        office: "U.S. Representative",
        state: "Washington",
      }),
    ).toBe("2026 Washington's 1st Congressional District Election");
    expect(
      raceDisplayTitle({
        id: "e2e-oh-house-05-2026",
        title: "old",
        office: "U.S. House",
        state: "Ohio",
        jurisdiction: "Ohio's 5th Congressional District",
      }),
    ).toBe("2026 Ohio's 5th Congressional District Election");
    expect(
      raceDisplayTitle({
        id: "de-house-at-large-2026",
        title: "old",
        office: "U.S. House",
        state: "Delaware",
      }),
    ).toBe("2026 Delaware's At-Large Congressional District Election");
    expect(
      raceDisplayTitle({
        id: "ga-governor-2026",
        title: "old",
        office: "Governor of Georgia",
        state: "Georgia",
      }),
    ).toBe("2026 Georgia Governor Election");
    expect(
      raceDisplayTitle({
        id: "md-governor-2026",
        title: "old",
        office: "Governor and Lieutenant Governor of Maryland",
        state: "Maryland",
      }),
    ).toBe("2026 Maryland Governor and Lieutenant Governor Election");
  });

  it("keeps unsupported offices' source title", () => {
    expect(
      raceDisplayTitle({
        id: "ar-supreme-court-2026",
        title: "Arkansas Supreme Court associate justice election, 2026",
        office: "Arkansas Supreme Court associate justice",
        state: "Arkansas",
      }),
    ).toBe("Arkansas Supreme Court associate justice election, 2026");
  });

  it("builds voter-focused page metadata", () => {
    const race = {
      id: "ga-senate-2026",
      title: "old",
      office: "U.S. Senate",
      state: "Georgia",
    };
    expect(racePageTitle(race)).toBe(
      "2026 Georgia U.S. Senate Election | Smarter.Vote",
    );
    expect(raceMetaDescription(race)).toContain(
      "Compare candidates in the 2026 Georgia U.S. Senate Election",
    );
  });
});
