import { describe, expect, it } from "vitest";
import type { RaceSummary } from "$lib/types";
import {
  homepageMetrics,
  nationalElectionRaces,
  recentlyUpdated,
  rotateByDate,
} from "./homepage";

const race = (id: string, updated: string, state = "Iowa"): RaceSummary => ({
  id,
  election_date: "2026-11-03",
  updated_utc: updated,
  state,
  candidates: [
    { name: "Alex Example", incumbent: false },
    { name: "alex example", incumbent: false },
    { name: "Jordan Example", incumbent: false },
  ],
});

describe("homepage data", () => {
  it("keeps federal and gubernatorial contests in launch coverage", () => {
    const federal = {
      ...race("house", "2026-01-01T00:00:00Z"),
      office: "U.S. House of Representatives",
    };
    const state = {
      ...race("governor", "2026-01-01T00:00:00Z"),
      office: "Governor of Iowa",
    };
    expect(nationalElectionRaces([state, federal])).toEqual([state, federal]);
  });

  it("rotates preview candidates deterministically by date", () => {
    const items = ["a", "b", "c"];
    expect(rotateByDate(items, new Date("2026-07-12T00:00:00Z"))).toEqual(
      rotateByDate(items, new Date("2026-07-12T12:00:00Z")),
    );
    expect(rotateByDate(items, new Date("2026-07-13T00:00:00Z"))).not.toEqual(
      rotateByDate(items, new Date("2026-07-12T00:00:00Z")),
    );
  });

  it("selects recently updated races deterministically", () => {
    expect(
      recentlyUpdated([
        race("older", "2026-01-01T00:00:00Z"),
        race("newer", "2026-02-01T00:00:00Z"),
      ]).map(({ id }) => id),
    ).toEqual(["newer", "older"]);
  });

  it("computes reproducible published-data metrics", () => {
    expect(
      homepageMetrics(
        [
          race("one", "2026-01-01T00:00:00Z"),
          race("two", "2026-02-01T00:00:00Z", "Ohio"),
        ],
        "2026-07-12",
      ),
    ).toMatchObject({
      guides: 2,
      candidateProfiles: 4,
      statesRepresented: 2,
      lastUpdated: "2026-02-01T00:00:00.000Z",
      snapshotDate: "2026-07-12",
    });
  });
});
