import { describe, expect, it } from "vitest";
import {
  partyAbbr,
  partyBadgeClass,
  partyRing,
  partyInitialBg,
  partyKey,
  partySlug,
} from "./party";

describe("party utilities", () => {
  describe("partyAbbr", () => {
    it("returns ? for empty values", () => {
      expect(partyAbbr(undefined)).toBe("?");
      expect(partyAbbr("")).toBe("?");
    });

    it("identifies Democratic party variants", () => {
      expect(partyAbbr("Democratic")).toBe("D");
      expect(partyAbbr("democrat")).toBe("D");
      expect(partyAbbr("DFL")).toBe("D");
      expect(partyAbbr("d")).toBe("D");
    });

    it("identifies Republican party variants", () => {
      expect(partyAbbr("Republican")).toBe("R");
      expect(partyAbbr("republican")).toBe("R");
      expect(partyAbbr("GOP")).toBe("R");
      expect(partyAbbr("r")).toBe("R");
    });

    it("identifies Independent variants", () => {
      expect(partyAbbr("Independent")).toBe("I");
      expect(partyAbbr("i")).toBe("I");
    });

    it("identifies Green variants", () => {
      expect(partyAbbr("Green")).toBe("G");
      expect(partyAbbr("g")).toBe("G");
    });

    it("identifies Libertarian variants", () => {
      expect(partyAbbr("Libertarian")).toBe("L");
      expect(partyAbbr("l")).toBe("L");
    });

    it("falls back to first letter capitalized for other parties", () => {
      expect(partyAbbr("Constitution")).toBe("C");
      expect(partyAbbr("Reform")).toBe("R");
    });
  });

  describe("partyBadgeClass", () => {
    it("returns gray style for undefined", () => {
      const cls = partyBadgeClass(undefined);
      expect(cls).toContain("bg-gray-100");
    });

    it("returns blue style for Democrats", () => {
      expect(partyBadgeClass("Democratic")).toContain("bg-blue-100");
      expect(partyBadgeClass("d")).toContain("bg-blue-100");
    });

    it("returns red style for Republicans", () => {
      expect(partyBadgeClass("Republican")).toContain("bg-red-100");
      expect(partyBadgeClass("r")).toContain("bg-red-100");
    });

    it("returns purple style for Independents", () => {
      expect(partyBadgeClass("Independent")).toContain("bg-purple-100");
      expect(partyBadgeClass("i")).toContain("bg-purple-100");
    });

    it("returns amber style for Libertarians", () => {
      expect(partyBadgeClass("Libertarian")).toContain("bg-amber-100");
      expect(partyBadgeClass("l")).toContain("bg-amber-100");
    });

    it("returns emerald style for Greens", () => {
      expect(partyBadgeClass("Green")).toContain("bg-emerald-100");
      expect(partyBadgeClass("g")).toContain("bg-emerald-100");
    });
  });

  describe("partyRing", () => {
    it("returns gray style for undefined", () => {
      expect(partyRing(undefined)).toBe("ring-gray-300");
    });

    it("returns blue style for Democrats", () => {
      expect(partyRing("Democratic")).toBe("ring-blue-500");
      expect(partyRing("d")).toBe("ring-blue-500");
    });

    it("returns red style for Republicans", () => {
      expect(partyRing("Republican")).toBe("ring-red-500");
      expect(partyRing("r")).toBe("ring-red-500");
    });
  });

  describe("partyInitialBg", () => {
    it("returns gray style for undefined", () => {
      expect(partyInitialBg(undefined)).toBe("bg-gray-400");
    });

    it("returns blue style for Democrats", () => {
      expect(partyInitialBg("Democratic")).toBe("bg-blue-500");
      expect(partyInitialBg("d")).toBe("bg-blue-500");
    });

    it("returns red style for Republicans", () => {
      expect(partyInitialBg("Republican")).toBe("bg-red-500");
      expect(partyInitialBg("r")).toBe("bg-red-500");
    });
  });

  describe("partySlug", () => {
    it("returns empty string for undefined or other parties", () => {
      expect(partySlug(undefined)).toBe("");
      expect(partySlug("Green")).toBe("");
    });

    it("returns dem for Democrats", () => {
      expect(partySlug("Democratic")).toBe("dem");
      expect(partySlug("d")).toBe("dem");
    });

    it("returns rep for Republicans", () => {
      expect(partySlug("Republican")).toBe("rep");
      expect(partySlug("r")).toBe("rep");
    });
  });

  describe("consistency across helpers", () => {
    // These four helpers describe the same candidate in four places on the page.
    // Before they shared a classifier, only partyAbbr and partyBadgeClass knew
    // about independents, so an independent wore a purple pill above a grey
    // avatar ring.
    const INDEPENDENT_LABELS = ["Independent", "independent", "i", "I"];

    it.each(INDEPENDENT_LABELS)(
      "gives %s the independent treatment in every helper",
      (label) => {
        expect(partyKey(label)).toBe("ind");
        expect(partyAbbr(label)).toBe("I");
        expect(partyBadgeClass(label)).toContain("purple");
        expect(partyRing(label)).toBe("ring-purple-500");
        expect(partyInitialBg(label)).toBe("bg-purple-500");
      },
    );

    it.each([
      ["Democratic", "dem"],
      ["Republican", "rep"],
      ["Independent", "ind"],
      ["Green", "grn"],
      ["Libertarian", "lib"],
      ["Nonpartisan", "other"],
      ["Undeclared", "other"],
    ])("classifies %s as %s", (label, key) => {
      expect(partyKey(label)).toBe(key);
    });

    it("never leaves a recognised party without a ring or avatar colour", () => {
      // A party the classifier knows but a helper forgot would fall through to
      // undefined and render an unstyled element.
      for (const label of [
        "Democratic",
        "Republican",
        "Independent",
        "Green",
        "Libertarian",
        "Constitution",
      ]) {
        expect(partyRing(label)).toMatch(/^ring-/);
        expect(partyInitialBg(label)).toMatch(/^bg-/);
        expect(partyBadgeClass(label)).toContain("bg-");
        expect(partyAbbr(label)).not.toBe("");
      }
    });

    it("keeps an absent party distinct from an unrecognised one", () => {
      // Nothing claimed vs. claimed-but-unknown are different states and the
      // avatar reflects that; collapsing them would lose the distinction.
      expect(partyRing(undefined)).not.toBe(partyRing("Constitution"));
      expect(partyInitialBg(undefined)).not.toBe(
        partyInitialBg("Constitution"),
      );
    });

    it("keeps partySlug to the two parties the stylesheet defines", () => {
      // .poll-bar-fill.dem and .poll-bar-fill.rep are the only rules that exist;
      // returning anything else would name a class with no styling behind it.
      expect(partySlug("Independent")).toBe("");
      expect(partySlug("Libertarian")).toBe("");
      expect(partySlug("Green")).toBe("");
    });
  });
});
