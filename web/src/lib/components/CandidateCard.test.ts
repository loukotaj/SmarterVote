import { render } from "@testing-library/svelte";
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
  voting_record: [],
  top_donors: [],
  website: "https://example.com",
  social_media: {},
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
});
