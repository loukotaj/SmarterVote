import { describe, expect, it } from "vitest";
import { matchingNationalRaces, parseCensusGeography } from "./electionLookup";
import type { RaceSummary } from "$lib/types";

const race = (overrides: Partial<RaceSummary>): RaceSummary => ({
  id: "race",
  title: "Race",
  office: "United States Senate",
  jurisdiction: "Maryland",
  state: "Maryland",
  election_date: "2026-11-03",
  updated_utc: "2026-07-01T00:00:00Z",
  candidates: [],
  ...overrides,
});

describe("parseCensusGeography", () => {
  it("extracts the state and current congressional district", () => {
    expect(
      parseCensusGeography({
        result: {
          addressMatches: [
            {
              geographies: {
                States: [{ NAME: "Maryland" }],
                "119th Congressional Districts": [{ CD119: "04" }],
              },
            },
          ],
        },
      }),
    ).toEqual({ state: "Maryland", congressionalDistrict: "04" });
  });

  it("returns null for an unmatched address", () => {
    expect(parseCensusGeography({ result: { addressMatches: [] } })).toBeNull();
  });
});

describe("matchingNationalRaces", () => {
  it("returns the matching House district and statewide Senate race", () => {
    const races = [
      race({ id: "senate" }),
      race({ id: "governor", office: "Governor of Maryland" }),
      race({
        id: "house-4",
        office: "U.S. House of Representatives",
        jurisdiction: "Maryland's 4th Congressional District",
      }),
      race({
        id: "house-5",
        office: "U.S. House of Representatives",
        jurisdiction: "Maryland's 5th Congressional District",
      }),
      race({ id: "virginia", state: "Virginia", jurisdiction: "Virginia" }),
    ];

    expect(
      matchingNationalRaces(
        races,
        { state: "Maryland", congressionalDistrict: "04" },
        new Date("2026-07-12"),
      ).map(({ id }) => id),
    ).toEqual(["senate", "governor", "house-4"]);
  });

  it("matches at-large House races and excludes past elections", () => {
    const races = [
      race({
        id: "at-large",
        office: "U.S. House of Representatives",
        state: "Alaska",
        jurisdiction: "Alaska's At-Large Congressional District",
      }),
      race({
        id: "past",
        state: "Alaska",
        jurisdiction: "Alaska",
        election_date: "2024-11-05",
      }),
    ];

    expect(
      matchingNationalRaces(
        races,
        { state: "Alaska", congressionalDistrict: "00" },
        new Date("2026-07-12"),
      ).map(({ id }) => id),
    ).toEqual(["at-large"]);
  });

  it("does not confuse Virginia with West Virginia", () => {
    const races = [
      race({
        id: "virginia-senate",
        state: "Virginia",
        jurisdiction: "Virginia",
      }),
      race({
        id: "west-virginia-senate",
        state: "West Virginia",
        jurisdiction: "West Virginia",
      }),
    ];

    expect(
      matchingNationalRaces(races, {
        state: "Virginia",
        congressionalDistrict: "01",
      }).map(({ id }) => id),
    ).toEqual(["virginia-senate"]);
  });
});
