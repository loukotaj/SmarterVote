import { describe, expect, it } from "vitest";
import {
  gradeAHomepageFallbacks,
  mergeGradeAHomepageRaces,
} from "$lib/homepagePreview";

describe("mergeGradeAHomepageRaces", () => {
  it("keeps multiple carousel options after a partial production load", () => {
    const [verified, fallback] = gradeAHomepageFallbacks;

    expect(mergeGradeAHomepageRaces([verified])).toEqual([verified, fallback]);
  });

  it("deduplicates races and respects the display limit", () => {
    const [first, second] = gradeAHomepageFallbacks;

    expect(mergeGradeAHomepageRaces([first, second, first], [], 1)).toEqual([
      first,
    ]);
  });
});
