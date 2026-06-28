import { describe, expect, it } from "vitest";
import {
  partyAbbr,
  partyBadgeClass,
  partyRing,
  partyInitialBg,
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

    it("returns yellow style for Libertarians", () => {
      expect(partyBadgeClass("Libertarian")).toContain("bg-yellow-100");
      expect(partyBadgeClass("l")).toContain("bg-yellow-100");
    });

    it("returns green style for Greens", () => {
      expect(partyBadgeClass("Green")).toContain("bg-green-100");
      expect(partyBadgeClass("g")).toContain("bg-green-100");
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
});
