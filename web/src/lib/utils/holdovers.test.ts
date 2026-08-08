import { describe, expect, it } from "vitest";
import {
  CHAMBER_SEAT_TOTALS,
  CHAMBER_VACANCIES,
  CURRENT_CHAMBER_COMPOSITION,
  GOVERNOR_HOLDOVERS,
  SENATE_HOLDOVERS,
} from "./holdovers";

/**
 * These tables are cycle data that must move together. Rolling the site to a new
 * election means editing the holdover tables *and* the current composition, and a
 * half-done edit produces a forecast page that is silently wrong rather than
 * visibly broken — the seat totals still render, they just do not add up.
 *
 * Each assertion below is an arithmetic identity that holds for any cycle, so
 * these keep working after the tables are updated. They fail only when the tables
 * disagree with each other.
 */
describe("holdover tables", () => {
  function partyCounts(parties: ("Democratic" | "Republican")[]) {
    return parties.reduce(
      (acc, party) => {
        acc[party] += 1;
        return acc;
      },
      { Democratic: 0, Republican: 0 },
    );
  }

  it("never lists more seats than the chamber has", () => {
    const senateSeats = Object.values(SENATE_HOLDOVERS).flat().length;
    expect(senateSeats).toBeLessThanOrEqual(CHAMBER_SEAT_TOTALS.senate);
    expect(Object.keys(GOVERNOR_HOLDOVERS).length).toBeLessThanOrEqual(
      CHAMBER_SEAT_TOTALS.governors,
    );
  });

  it("gives each state at most its two Senate seats", () => {
    for (const [state, parties] of Object.entries(SENATE_HOLDOVERS)) {
      expect(
        parties.length,
        `${state} has ${parties.length} Senate seats`,
      ).toBeGreaterThan(0);
      expect(
        parties.length,
        `${state} has ${parties.length} Senate seats`,
      ).toBeLessThanOrEqual(2);
    }
  });

  it("accounts for every seat in each chamber, held or vacant", () => {
    for (const chamber of ["house", "senate", "governors"] as const) {
      const composition = CURRENT_CHAMBER_COMPOSITION[chamber];
      const held =
        composition.Democratic + composition.Republican + composition.Other;
      expect(
        held + CHAMBER_VACANCIES[chamber],
        `${chamber}: ${held} held + ${CHAMBER_VACANCIES[chamber]} vacant`,
      ).toBe(CHAMBER_SEAT_TOTALS[chamber]);
    }
  });

  it("holds no more seats for a party than that party currently has", () => {
    // A holdover seat is a seat the party already holds and is not defending, so
    // it cannot exceed the party's current total. If it does, one of the two
    // tables was updated for a new cycle and the other was not.
    const senate = partyCounts(Object.values(SENATE_HOLDOVERS).flat());
    expect(senate.Democratic).toBeLessThanOrEqual(
      CURRENT_CHAMBER_COMPOSITION.senate.Democratic,
    );
    expect(senate.Republican).toBeLessThanOrEqual(
      CURRENT_CHAMBER_COMPOSITION.senate.Republican,
    );

    const governors = partyCounts(Object.values(GOVERNOR_HOLDOVERS));
    expect(governors.Democratic).toBeLessThanOrEqual(
      CURRENT_CHAMBER_COMPOSITION.governors.Democratic,
    );
    expect(governors.Republican).toBeLessThanOrEqual(
      CURRENT_CHAMBER_COMPOSITION.governors.Republican,
    );
  });

  it("leaves a whole number of seats on the ballot in each chamber", () => {
    // seats up = total − holdovers, and it must also equal the sum of each
    // party's defended seats. Both routes agreeing is what proves the tables
    // are describing the same cycle.
    const senateHoldovers = Object.values(SENATE_HOLDOVERS).flat();
    const senateCounts = partyCounts(senateHoldovers);
    const senateUp = CHAMBER_SEAT_TOTALS.senate - senateHoldovers.length;
    expect(
      CURRENT_CHAMBER_COMPOSITION.senate.Democratic -
        senateCounts.Democratic +
        (CURRENT_CHAMBER_COMPOSITION.senate.Republican -
          senateCounts.Republican) +
        CURRENT_CHAMBER_COMPOSITION.senate.Other,
    ).toBe(senateUp);

    const governorStates = Object.keys(GOVERNOR_HOLDOVERS);
    const governorCounts = partyCounts(Object.values(GOVERNOR_HOLDOVERS));
    const governorsUp = CHAMBER_SEAT_TOTALS.governors - governorStates.length;
    expect(
      CURRENT_CHAMBER_COMPOSITION.governors.Democratic -
        governorCounts.Democratic +
        (CURRENT_CHAMBER_COMPOSITION.governors.Republican -
          governorCounts.Republican) +
        CURRENT_CHAMBER_COMPOSITION.governors.Other,
    ).toBe(governorsUp);
  });
});
