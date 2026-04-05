import { fireEvent, render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";
import CandidateCard from "./CandidateCard.svelte";
import type { Candidate, CanonicalIssue, IssueStance } from "$lib/types";

const candidate: Candidate = {
  name: "Jane Doe",
  party: "Independent",
  incumbent: true,
  summary: "Test summary",
  issues: {} as Record<CanonicalIssue, IssueStance>,
  career_history: [],
  education: [],
  links: [],
  website: "https://example.com",
  social_media: {},
  summary_sources: [],
};

describe("CandidateCard", () => {
  it("renders candidate details", () => {
    const { container } = render(CandidateCard, { candidate });
    const text = container.textContent || "";
    expect(text).toContain("Jane Doe");
    // Party is abbreviated in the card (e.g. "Independent" → "I")
    expect(text).toMatch(/Independent|I\b/);
    expect(text).toContain("Incumbent");
  });

  it("renders background source links when career and education entries include sources", async () => {
    const candidateWithSources: Candidate = {
      ...candidate,
      career_history: [
        {
          title: "Strategy Consultant",
          organization: "Example Group",
          source: {
            url: "https://example.com/career",
            type: "news",
            title: "Career Source",
            last_accessed: "2026-04-04T00:00:00Z",
          },
        },
      ],
      education: [
        {
          institution: "Example University",
          degree: "BA",
          field: "Politics",
          source: {
            url: "https://example.com/education",
            type: "website",
            title: "Education Source",
            last_accessed: "2026-04-04T00:00:00Z",
          },
        },
      ],
    };

    const { getByText } = render(CandidateCard, { candidate: candidateWithSources });
    await fireEvent.click(getByText("Show More"));
    await fireEvent.click(getByText("Background"));

    expect(getByText("Career Source")).toBeTruthy();
    expect(getByText("Education Source")).toBeTruthy();
  });
});
