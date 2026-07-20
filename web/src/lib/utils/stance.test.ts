import { describe, expect, it } from "vitest";
import { stancePreview } from "./stance";

describe("stancePreview", () => {
  it("keeps abbreviations inside the first sentence", () => {
    expect(
      stancePreview(
        "U.S. Senate candidate supports expanding health coverage. A second sentence follows.",
      ),
    ).toBe("U.S. Senate candidate supports expanding health coverage.");
  });

  it("returns the first complete sentence", () => {
    expect(
      stancePreview("The first position is clear! More detail follows."),
    ).toBe("The first position is clear!");
  });

  it("can include complete sentences until a minimum preview length", () => {
    expect(
      stancePreview(
        "One short sentence. A second complete sentence reaches the requested preview length. More detail follows.",
        180,
        50,
      ),
    ).toBe(
      "One short sentence. A second complete sentence reaches the requested preview length.",
    );
  });

  it("truncates a long sentence on a word boundary", () => {
    const preview = stancePreview("word ".repeat(50), 40);
    expect(preview.endsWith("…")).toBe(true);
    expect(preview.length).toBeLessThanOrEqual(41);
  });
});
