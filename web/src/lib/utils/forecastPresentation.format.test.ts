import { describe, expect, it } from "vitest";
import {
  colorForRating,
  marketAsOf,
  marketSignalTarget,
  marketSpread,
  oneDecimal,
  partyClass,
  probability,
  probabilityOneDecimal,
  ratingClass,
  ratingCompetitiveness,
} from "./forecastPresentation";
import type { ForecastRating } from "$lib/types";

/**
 * The pure presentation helpers. `forecastPresentation.test.ts` covers the
 * composite builders (seat charts, state map data); this file covers the small
 * formatters and classifiers those builders lean on, where the interesting
 * behaviour is entirely in the boundaries.
 */

describe("partyClass", () => {
  it.each([
    ["Democratic", "blue"],
    ["Republican", "red"],
  ])("colours %s with the %s ramp", (party, hue) => {
    expect(partyClass(party)).toContain(hue);
  });

  it.each(["Independent", "Libertarian", "", "democratic"])(
    "falls back to muted text for %j",
    (party) => {
      expect(partyClass(party)).toBe("text-content-muted");
    },
  );

  it("gives every recognised party a dark-mode variant", () => {
    expect(partyClass("Democratic")).toContain("dark:");
    expect(partyClass("Republican")).toContain("dark:");
  });
});

describe("ratingClass", () => {
  it.each(["safe_d", "likely_d", "lean_d", "tilt_d"])(
    "treats %s as a Democratic rating",
    (rating) => {
      expect(ratingClass(rating as ForecastRating)).toContain("blue");
    },
  );

  it.each(["safe_r", "likely_r", "lean_r", "tilt_r"])(
    "treats %s as a Republican rating",
    (rating) => {
      expect(ratingClass(rating as ForecastRating)).toContain("red");
    },
  );

  it.each(["tossup", "other"])("treats %s as neutral", (rating) => {
    expect(ratingClass(rating as ForecastRating)).toContain("slate");
  });
});

describe("colorForRating", () => {
  it("maps a rating onto its CSS custom property", () => {
    expect(colorForRating("safe_d" as ForecastRating)).toBe(
      "var(--color-safe-d)",
    );
  });

  it("leaves a single-word rating unhyphenated", () => {
    expect(colorForRating("tossup" as ForecastRating)).toBe(
      "var(--color-tossup)",
    );
  });

  // Only the first underscore is replaced, which is fine for the current
  // vocabulary but worth pinning in case a three-part rating is ever added.
  it("replaces only the first underscore", () => {
    expect(colorForRating("a_b_c" as ForecastRating)).toBe(
      "var(--color-a-b_c)",
    );
  });
});

describe("ratingCompetitiveness", () => {
  // Lower is more competitive; the ordering drives "closest race" selection.
  it("orders ratings from tossup outward", () => {
    const order = [
      "tossup",
      "tilt_d",
      "lean_r",
      "likely_d",
      "safe_r",
    ] as ForecastRating[];
    const scores = order.map(ratingCompetitiveness);

    expect(scores).toEqual([0, 1, 2, 3, 4]);
    expect([...scores].sort((a, b) => a - b)).toEqual(scores);
  });

  it("scores an unknown rating as least competitive", () => {
    expect(ratingCompetitiveness("other" as ForecastRating)).toBe(5);
  });

  it("scores both parties of a band identically", () => {
    expect(ratingCompetitiveness("lean_d" as ForecastRating)).toBe(
      ratingCompetitiveness("lean_r" as ForecastRating),
    );
  });
});

describe("probability", () => {
  it.each([
    [undefined, "n/a"],
    [null, "n/a"],
  ])("renders %s as n/a", (value, expected) => {
    expect(probability(value as number | null | undefined)).toBe(expected);
  });

  // Certainty is never claimed: 1 and 0 are clamped to >99% / <1%, because a
  // forecast that says "100%" reads as a promise rather than an estimate.
  it.each([
    [1, ">99%"],
    [1.2, ">99%"],
    [0, "<1%"],
    [-0.5, "<1%"],
  ])("clamps %s to %s", (value, expected) => {
    expect(probability(value)).toBe(expected);
  });

  it.each([
    [0.5, "50%"],
    [0.674, "67%"],
    [0.675, "68%"],
    [0.009, "1%"],
  ])("rounds %s to %s", (value, expected) => {
    expect(probability(value)).toBe(expected);
  });
});

describe("probabilityOneDecimal", () => {
  it.each([
    [undefined, "n/a"],
    [null, "n/a"],
  ])("renders %s as n/a", (value, expected) => {
    expect(probabilityOneDecimal(value as number | null | undefined)).toBe(
      expected,
    );
  });

  // Unlike `probability`, this one does not clamp — it is used for market
  // quotes, where an exact 100.0% bid is a real thing to display.
  it.each([
    [0.5, "50.0%"],
    [0.6745, "67.5%"],
    [1, "100.0%"],
    [0, "0.0%"],
  ])("formats %s as %s", (value, expected) => {
    expect(probabilityOneDecimal(value)).toBe(expected);
  });
});

describe("marketSignalTarget", () => {
  it("annotates the party when it differs from the matched name", () => {
    expect(
      marketSignalTarget({
        matched_to: "Jane Doe",
        matched_party: "Democratic",
      }),
    ).toBe("Jane Doe (Democratic)");
  });

  it("omits a redundant party annotation", () => {
    expect(
      marketSignalTarget({
        matched_to: "Democratic",
        matched_party: "Democratic",
      }),
    ).toBe("Democratic");
  });

  it.each([undefined, ""])("omits an absent party (%j)", (party) => {
    expect(
      marketSignalTarget({ matched_to: "Jane Doe", matched_party: party }),
    ).toBe("Jane Doe");
  });
});

describe("marketSpread", () => {
  it("renders a bid/ask pair", () => {
    expect(marketSpread({ yes_bid: 0.42, yes_ask: 0.45 })).toBe(
      "42.0% bid / 45.0% ask",
    );
  });

  it.each([
    ["a missing bid", { yes_ask: 0.45 }],
    ["a missing ask", { yes_bid: 0.42 }],
    ["a null bid", { yes_bid: null, yes_ask: 0.45 }],
    ["neither side", {}],
  ])("returns null for %s", (_label, signal) => {
    expect(marketSpread(signal)).toBeNull();
  });

  // 0 is a legitimate quote, so the guard is a type check rather than
  // truthiness — a falsy check would hide a market priced at zero.
  it("renders a zero bid rather than treating it as missing", () => {
    expect(marketSpread({ yes_bid: 0, yes_ask: 0.05 })).toBe(
      "0.0% bid / 5.0% ask",
    );
  });
});

describe("marketAsOf", () => {
  it("formats a valid timestamp", () => {
    expect(marketAsOf("2026-01-15T00:00:00Z")).toMatch(/Jan/);
    expect(marketAsOf("2026-01-15T00:00:00Z")).toMatch(/2026/);
  });

  it.each([
    ["an empty string", ""],
    ["undefined", undefined],
    ["null", null],
    ["an unparseable value", "not-a-date"],
  ])("returns an empty string for %s", (_label, value) => {
    expect(marketAsOf(value as string | null | undefined)).toBe("");
  });
});

describe("oneDecimal", () => {
  it.each([
    [undefined, "n/a"],
    [null, "n/a"],
  ])("renders %s as n/a", (value, expected) => {
    expect(oneDecimal(value as number | null | undefined)).toBe(expected);
  });

  it.each([
    [1, "1.0"],
    [1.25, "1.3"],
    [1.24, "1.2"],
    [0, "0.0"],
    [-2.5, "-2.5"],
  ])("formats %s as %s", (value, expected) => {
    expect(oneDecimal(value)).toBe(expected);
  });
});
