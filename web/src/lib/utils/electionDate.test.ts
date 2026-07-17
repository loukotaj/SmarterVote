import { describe, expect, it } from "vitest";
import {
  daysUntilElection,
  formatElectionDate,
  parseElectionDate,
} from "./electionDate";

describe("election date utilities", () => {
  it("preserves the published calendar day for midnight UTC values", () => {
    expect(parseElectionDate("2025-11-05T00:00:00Z")).toEqual({
      year: 2025,
      month: 11,
      day: 5,
    });
    expect(
      formatElectionDate("2025-11-05T00:00:00Z", {
        month: "short",
        day: "numeric",
        year: "numeric",
      }),
    ).toBe("Nov 5, 2025");
  });

  it("supports date-only values and rejects invalid calendar dates", () => {
    expect(formatElectionDate("2026-11-03")).toBe("November 3, 2026");
    expect(parseElectionDate("2026-02-29")).toBeNull();
    expect(parseElectionDate("not-a-date")).toBeNull();
  });

  it("counts calendar days rather than elapsed 24-hour periods", () => {
    expect(daysUntilElection("2026-03-09", new Date(2026, 2, 8, 23, 30))).toBe(
      1,
    );
    expect(daysUntilElection("2026-03-08", new Date(2026, 2, 8, 0, 1))).toBe(0);
    expect(daysUntilElection("2026-03-07", new Date(2026, 2, 8, 0, 1))).toBe(
      -1,
    );
  });
});
