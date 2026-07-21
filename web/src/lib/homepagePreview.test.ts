import { describe, expect, it } from "vitest";
import {
  gradeAHomepageFallbacks,
  isHomepagePreviewRace,
  mergeHomepagePreviewRaces,
} from "$lib/homepagePreview";

describe("homepage preview races", () => {
  it("accepts a strong reviewed race without requiring a letter grade of A", () => {
    const race = {
      ...gradeAHomepageFallbacks[0],
      validation_grade: {
        grade: "B" as const,
        score: 89,
        passed: true,
        summary: "Validated by reviewers.",
      },
    };

    expect(isHomepagePreviewRace(race)).toBe(true);
  });

  it("deduplicates races and respects the display limit", () => {
    const [first, second] = gradeAHomepageFallbacks;

    expect(mergeHomepagePreviewRaces([first, second, first], 1)).toEqual([
      first,
    ]);
  });
});
