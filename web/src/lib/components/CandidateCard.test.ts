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
  top_donors: [],
  website: "https://example.com",
  social_media: {},
};

describe("CandidateCard", () => {
  it("renders candidate details", () => {
    const { container } = render(CandidateCard, { candidate });
    const text = container.textContent || "";
    expect(text).toContain("Jane Doe");
    expect(text).toContain("Independent");
    expect(text).toContain("Incumbent");
  });
});
