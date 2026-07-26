/**
 * Canned Census geocoder response for the `my-ballot` address lookup flow.
 * Matches the shape `parseCensusGeography` (src/lib/services/electionLookup.ts)
 * expects, resolving to Ohio's 5th Congressional District so it lines up with
 * the `e2e-oh-house-05-2026` and `e2e-oh-senate-2026` fixture races.
 */
export const OHIO_DISTRICT_05_CENSUS_RESPONSE = {
  result: {
    addressMatches: [
      {
        geographies: {
          States: [{ NAME: "Ohio" }],
          "119th Congressional Districts": [{ CD119: "05" }],
        },
      },
    ],
  },
};

/** A response with no address matches, used to exercise the lookup error path. */
export const NO_MATCH_CENSUS_RESPONSE = {
  result: {
    addressMatches: [],
  },
};

/**
 * Resolves to a state/district with no fixture races, so my-ballot's
 * "we found your district but nothing published yet" empty state can be
 * exercised deterministically.
 */
export const NO_RACES_CENSUS_RESPONSE = {
  result: {
    addressMatches: [
      {
        geographies: {
          States: [{ NAME: "California" }],
          "119th Congressional Districts": [{ CD119: "12" }],
        },
      },
    ],
  },
};
