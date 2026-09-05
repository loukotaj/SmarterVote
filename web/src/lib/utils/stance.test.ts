import { describe, expect, it } from "vitest";
import { collapsedPreview, stancePreview } from "./stance";

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

describe("collapsedPreview", () => {
  it("returns short text unchanged", () => {
    expect(collapsedPreview("A brief position.")).toBe("A brief position.");
  });

  it("hard-caps long text that a sentence-bounded preview would keep whole", () => {
    const sentence = `${"word ".repeat(60).trim()}.`;
    const result = collapsedPreview(sentence);

    expect(result.length).toBeLessThanOrEqual(121);
    expect(result.endsWith("…")).toBe(true);
  });

  it("breaks on a word boundary rather than mid-word", () => {
    const result = collapsedPreview(`${"alpha ".repeat(40).trim()}.`);

    expect(result.replace("…", "").trim().endsWith("alpha")).toBe(true);
  });

  it("honors a custom limit", () => {
    const result = collapsedPreview(`${"beta ".repeat(40).trim()}.`, 20);

    expect(result.length).toBeLessThanOrEqual(21);
  });
});
