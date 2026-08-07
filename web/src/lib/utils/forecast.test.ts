import { describe, expect, it } from "vitest";
import type { RaceSummary } from "$lib/types";
import {
  aggregateForecasts,
  filterForecastRaces,
  getControlRelevanceScore,
  getMostLikelySeatOutcome,
  isRaceInForecastTab,
  officeGroup,
  fallbackPartyForRace,
  parseForecastTab,
  groupSeatDistribution,
  normalizeForecastParty,
  raceHref,
  resolveControlParty,
  sortForecastRaces,
  type ForecastRace,
} from "./forecast";

const baseRace = {
  election_date: "2026-11-03",
  updated_utc: "2026-06-20T00:00:00Z",
  candidates: [],
};

describe("forecast utilities", () => {
  it("normalizes forecast parties correctly including fallbacks", () => {
    expect(normalizeForecastParty("Democratic")).toBe("Democratic");
    expect(normalizeForecastParty("Republican")).toBe("Republican");

    // Null party with probabilities
    expect(
      normalizeForecastParty(null, { Democratic: 0.53, Republican: 0.47 }),
    ).toBe("Democratic");
    expect(
      normalizeForecastParty(null, { Democratic: 0.45, Republican: 0.55 }),
    ).toBe("Republican");

    // Null party with candidate incumbent fallback
    expect(
      normalizeForecastParty(null, null, [
        { name: "Alice", party: "Democratic", incumbent: true },
      ]),
    ).toBe("Democratic");
    expect(
      normalizeForecastParty(null, null, [
        { name: "Bob", party: "Republican", incumbent: true },
      ]),
    ).toBe("Republican");

    // No probabilities, no incumbent, should fallback to Other
    expect(normalizeForecastParty(null)).toBe("Other");
  });

  it("classifies race offices", () => {
    expect(
      officeGroup({
        ...baseRace,
        id: "ga-senate-2026",
        office: "United States Senate",
      }),
    ).toBe("senate");
    expect(
      officeGroup({
        ...baseRace,
        id: "ga-governor-2026",
        office: "Governor of Georgia",
      }),
    ).toBe("governors");
    expect(
      officeGroup({
        ...baseRace,
        id: "ga-house-01-2026",
        office: "United States House",
      }),
    ).toBe("house");
  });

  it("parses URL tab parameters with a house default", () => {
    expect(parseForecastTab("senate")).toBe("senate");
    expect(parseForecastTab("governors")).toBe("governors");
    expect(parseForecastTab("bad-value")).toBe("house");
    expect(parseForecastTab(null)).toBe("house");
  });

  it("aggregates senate forecasts with holdover baseline", () => {
    const races: RaceSummary[] = [
      {
        ...baseRace,
        id: "ga-senate-2026",
        office: "United States Senate",
        forecast: {
          predicted_winner_name: "Alice",
          predicted_winner_party: "Democratic",
          win_probability: 0.57,
          party_probabilities: { Democratic: 0.57, Republican: 0.43 },
          margin_estimate: 1.2,
          rating: "tilt_d",
          confidence: "medium",
          rationale: "Narrow advantage.",
          based_on_poll_count: 1,
          generated_at: "2026-06-20T00:00:00Z",
          model: "openai/gpt-5.4",
          source_urls: [],
          key_reasons: [],
          market_signals: [],
        },
      },
    ];

    const aggregate = aggregateForecasts(races, "senate");
    expect(aggregate.projected.Democratic).toBe(36);
    expect(aggregate.projected.Republican).toBe(32);
    expect(aggregate.ratingCounts.tilt_d).toBe(1);
  });

  it("excludes Indiana governor from 2026 governor control aggregation", () => {
    const races: RaceSummary[] = [
      {
        ...baseRace,
        id: "in-governor-2026",
        office: "Governor of Indiana",
        forecast: {
          predicted_winner_party: "Republican",
          party_probabilities: { Republican: 0.9 },
          rating: "safe_r",
          confidence: "low",
          rationale: "Invalid cycle fixture.",
          based_on_poll_count: 0,
          generated_at: "2026-06-20T00:00:00Z",
          model: "openai/gpt-5.4",
          source_urls: [],
          key_reasons: [],
          market_signals: [],
        },
      },
    ];

    const aggregate = aggregateForecasts(races, "governors");
    expect(aggregate.races).toHaveLength(0);
    expect(aggregate.projected.Republican).toBe(8);
    expect(isRaceInForecastTab(races[0], "governors")).toBe(false);
  });

  it("groups seat distribution into buckets correctly", () => {
    const dist = {
      "54D-46R": 0.05,
      "53D-47R": 0.1,
      "52D-48R": 0.15,
      "51D-49R": 0.2,
      "50R-50D": 0.25,
      "51R-49D": 0.15,
      "52R-48D": 0.08,
      "53R-47D": 0.02,
    };
    const buckets = groupSeatDistribution(dist, "senate");
    expect(buckets).toHaveLength(5);

    // Strong D (53D+) should sum 54D and 53D: 0.05 + 0.10 = 0.15
    expect(buckets[0].label).toBe("Strong D (53D+)");
    expect(buckets[0].probability).toBe(0.15);

    // Narrow D (51-52D) should sum 52D and 51D: 0.15 + 0.20 = 0.35
    expect(buckets[1].label).toBe("Narrow D (51-52D)");
    expect(buckets[1].probability).toBe(0.35);

    // Tie (50-50): 0.25
    expect(buckets[2].label).toBe("Tie (50-50)");
    expect(buckets[2].probability).toBe(0.25);

    // Narrow R (51-52R) should sum 51R (49D) and 52R (48D): 0.15 + 0.08 = 0.23
    expect(buckets[3].label).toBe("Narrow R (51-52R)");
    expect(buckets[3].probability).toBe(0.23);

    // Strong R (53R+) should sum 53R (47D): 0.02
    expect(buckets[4].label).toBe("Strong R (53R+)");
    expect(buckets[4].probability).toBe(0.02);
  });

  it("uses House-specific distribution labels", () => {
    const buckets = groupSeatDistribution(
      {
        "218R-217D": 0.6,
        "223D-212R": 0.4,
      },
      "house",
    );

    expect(buckets[1].label).toBe("Narrow D (218-224D)");
    expect(buckets[1].probability).toBe(0.4);
    expect(buckets[2].label).toBe("Near Tie (212-217D)");
    expect(buckets[2].probability).toBe(0.6);
  });

  it("builds a race href", () => {
    expect(raceHref("ga-senate-2026")).toBe("/races/ga-senate-2026");
  });

  it("finds the most likely seat outcome, defaulting when empty", () => {
    expect(getMostLikelySeatOutcome({})).toEqual({ key: "", probability: 0 });
    expect(
      getMostLikelySeatOutcome({ "51D-49R": 0.3, "50D-50R": 0.45 }),
    ).toEqual({ key: "50D-50R", probability: 0.45 });
  });

  describe("resolveControlParty", () => {
    const aggregate = aggregateForecasts([], "senate");

    it("prefers the chamber summary's own control_party", () => {
      expect(
        resolveControlParty(
          "senate",
          { control_party: "Democratic" } as never,
          aggregate,
        ),
      ).toBe("Democratic");
    });

    it("resolves a Senate 50-50 projection to Republican via VP tie-break", () => {
      const tiedAggregate = {
        ...aggregate,
        projected: { Democratic: 50, Republican: 50, Other: 0 },
      };
      expect(resolveControlParty("senate", undefined, tiedAggregate)).toBe(
        "Republican",
      );
    });

    it("falls back to whichever party meets the seat threshold", () => {
      const demAggregate = {
        ...aggregate,
        threshold: 51,
        projected: { Democratic: 52, Republican: 48, Other: 0 },
      };
      expect(resolveControlParty("senate", undefined, demAggregate)).toBe(
        "Democratic",
      );

      const noControlAggregate = {
        ...aggregate,
        threshold: 51,
        projected: { Democratic: 45, Republican: 45, Other: 10 },
      };
      expect(resolveControlParty("senate", undefined, noControlAggregate)).toBe(
        "Other",
      );
    });
  });

  describe("race sorting and filtering", () => {
    function race(
      id: string,
      overrides: Partial<ForecastRace["forecast"]> = {},
      raceOverrides: Partial<RaceSummary> = {},
    ): ForecastRace {
      return {
        ...baseRace,
        id,
        state: raceOverrides.state,
        title: raceOverrides.title ?? id,
        forecast: {
          party_probabilities: {},
          rating: "tossup",
          confidence: "medium",
          rationale: "test",
          based_on_poll_count: 1,
          generated_at: "2026-06-20T00:00:00Z",
          model: "test",
          source_urls: [],
          ...overrides,
        },
      } as ForecastRace;
    }

    it("scores races by named competitive-race relevance first, then rating closeness", () => {
      const named = race("ga-senate-2026", {}, { title: "Georgia Senate" });
      const other = race("wy-senate-2026", { rating: "tossup" });
      const chamberSummary = {
        competitive_races: ["Georgia Senate"],
      } as never;

      expect(getControlRelevanceScore(named, chamberSummary)).toBeLessThan(
        getControlRelevanceScore(other, chamberSummary),
      );
    });

    it("sorts by margin, probability and state", () => {
      const races = [
        race("a", { margin_estimate: 5 }),
        race("b", { margin_estimate: 1 }),
      ];
      const byMargin = sortForecastRaces(races, "margin", undefined);
      expect(byMargin.map((r) => r.id)).toEqual(["a", "b"]);

      const byState = sortForecastRaces(
        [
          race("a", {}, { state: "Wyoming" }),
          race("b", {}, { state: "Arizona" }),
        ],
        "state",
        undefined,
      );
      expect(byState.map((r) => r.id)).toEqual(["b", "a"]);
    });

    it("filters by selected state, rating bucket and party", () => {
      const races = [
        race(
          "a",
          { rating: "tossup", predicted_winner_party: "Democratic" },
          {
            state: "Nevada",
          },
        ),
        race(
          "b",
          { rating: "safe_r", predicted_winner_party: "Republican" },
          { state: "Alabama" },
        ),
      ];

      expect(
        filterForecastRaces(races, {
          selectedState: "Nevada",
          filterRating: "all",
          filterParty: "all",
        }).map((r) => r.id),
      ).toEqual(["a"]);

      expect(
        filterForecastRaces(races, {
          selectedState: null,
          filterRating: "likely_safe",
          filterParty: "all",
        }).map((r) => r.id),
      ).toEqual(["b"]);

      expect(
        filterForecastRaces(races, {
          selectedState: null,
          filterRating: "all",
          filterParty: "Republican",
        }).map((r) => r.id),
      ).toEqual(["b"]);
    });
  });

  describe("chamber classification generality", () => {
    // `office` is free text written by the research model, so the classifier
    // must not depend on one federal spelling — anchoring on a spelling used to
    // drop "US Senate" and bare "Senate" races off the forecast page entirely.
    it.each([
      "U.S. Senate",
      "US Senate",
      "United States Senate",
      "Senate",
      "Senator",
    ])("classifies %s as the federal Senate", (office) => {
      expect(officeGroup({ ...baseRace, id: "x-senate-2026", office })).toBe(
        "senate",
      );
    });

    it.each(["U.S. House", "US House of Representatives", "Congress"])(
      "classifies %s as the federal House",
      (office) => {
        expect(officeGroup({ ...baseRace, id: "x-house-2026", office })).toBe(
          "house",
        );
      },
    );

    it.each([
      "Georgia State Senate District 5",
      "State Senator",
      "State House of Representatives",
      "Virginia House of Delegates",
      "State Assembly",
      "General Assembly",
    ])("does not classify %s into any federal chamber", (office) => {
      expect(
        officeGroup({ ...baseRace, id: "x-state-2026", office }),
      ).toBeNull();
    });

    // Not Indiana-specific: the rule is "this state's governor is not up this
    // cycle", derived from GOVERNOR_HOLDOVERS.
    it.each(["Indiana", "Kentucky", "Louisiana", "Virginia"])(
      "excludes the %s governor race from governor control math",
      (state) => {
        const race = {
          ...baseRace,
          id: "xx-governor-2026",
          office: "Governor",
          state,
        } as RaceSummary;
        expect(isRaceInForecastTab(race, "governors")).toBe(false);
      },
    );

    it("still counts a governor race in a state that is on the ballot", () => {
      const race = {
        ...baseRace,
        id: "ga-governor-2026",
        office: "Governor",
        state: "Georgia",
      } as RaceSummary;
      expect(isRaceInForecastTab(race, "governors")).toBe(true);
    });

    it("resolves the holdover state from the race id when state is absent", () => {
      const race = {
        ...baseRace,
        id: "in-governor-2026",
        office: "Governor",
      } as RaceSummary;
      expect(isRaceInForecastTab(race, "governors")).toBe(false);
    });

    it("does not extend the governor holdover exclusion to other chambers", () => {
      const race = {
        ...baseRace,
        id: "in-house-01-2026",
        office: "U.S. House",
        state: "Indiana",
      } as RaceSummary;
      expect(isRaceInForecastTab(race, "house")).toBe(true);
    });
  });

  describe("fallbackPartyForRace", () => {
    // Mirrors `fallback_party_for_race` in shared/forecast_summary.py. The roster
    // steps must come first: they work for every race, where the per-state
    // INCUMBENT_FALLBACKS table only covers a handful of states.
    it("uses the roster's own incumbent before anything else", () => {
      const race = {
        ...baseRace,
        id: "oh-senate-2026",
        office: "U.S. Senate",
        state: "Ohio",
        candidates: [
          { name: "A", party: "Republican", incumbent: true },
          { name: "B", party: "Democratic", incumbent: false },
          { name: "C", party: "Democratic", incumbent: false },
        ],
      } as RaceSummary;
      expect(fallbackPartyForRace(race, "senate")).toBe("Republican");
    });

    it("falls back to the roster's party majority when nobody is flagged incumbent", () => {
      const race = {
        ...baseRace,
        id: "oh-senate-2026",
        office: "U.S. Senate",
        state: "Ohio",
        candidates: [
          { name: "A", party: "Democratic", incumbent: false },
          { name: "B", party: "Democratic", incumbent: false },
          { name: "C", party: "Republican", incumbent: false },
        ],
      } as RaceSummary;
      expect(fallbackPartyForRace(race, "senate")).toBe("Democratic");
    });

    it("prefers the roster over the hand-maintained state table", () => {
      // Vermont's governors entry is Republican; the roster says otherwise.
      const race = {
        ...baseRace,
        id: "vt-governor-2026",
        office: "Governor",
        state: "Vermont",
        candidates: [{ name: "A", party: "Democratic", incumbent: true }],
      } as RaceSummary;
      expect(fallbackPartyForRace(race, "governors")).toBe("Democratic");
    });

    it("uses the state table when the roster is empty", () => {
      const race = {
        ...baseRace,
        id: "vt-governor-2026",
        office: "Governor",
        state: "Vermont",
        candidates: [],
      } as RaceSummary;
      expect(fallbackPartyForRace(race, "governors")).toBe("Republican");
    });

    it("uses the Senate holdover table as the last resort", () => {
      const race = {
        ...baseRace,
        id: "wy-senate-2026",
        office: "U.S. Senate",
        state: "Wyoming",
        candidates: [],
      } as RaceSummary;
      expect(fallbackPartyForRace(race, "senate")).toBe("Republican");
    });

    it("returns null when nothing in the data supports a guess", () => {
      const race = {
        ...baseRace,
        id: "ga-house-05-2026",
        office: "U.S. House",
        state: "Georgia",
        candidates: [],
      } as RaceSummary;
      expect(fallbackPartyForRace(race, "house")).toBeNull();
    });

    it("does not guess from an evenly split roster", () => {
      const race = {
        ...baseRace,
        id: "ga-house-05-2026",
        office: "U.S. House",
        state: "Georgia",
        candidates: [
          { name: "A", party: "Democratic", incumbent: false },
          { name: "B", party: "Republican", incumbent: false },
        ],
      } as RaceSummary;
      expect(fallbackPartyForRace(race, "house")).toBeNull();
    });

    it("counts an unforecasted race toward the projection using the roster", () => {
      const races = [
        {
          ...baseRace,
          id: "ga-house-05-2026",
          office: "U.S. House",
          state: "Georgia",
          candidates: [{ name: "A", party: "Democratic", incumbent: true }],
        },
      ] as RaceSummary[];
      const aggregate = aggregateForecasts(races, "house");
      expect(aggregate.missingForecasts).toHaveLength(1);
      expect(aggregate.projected.Democratic).toBe(1);
    });
  });
});
