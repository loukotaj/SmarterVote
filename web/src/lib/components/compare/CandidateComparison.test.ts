import { cleanup, fireEvent, render, within } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import type { Candidate, Race } from "$lib/types";
import CandidateComparison from "./CandidateComparison.svelte";

const desktopPreview =
  "The first sentence explains the position. The second sentence adds context about implementation and likely effects. The third sentence explains funding and accountability for the proposal. The fourth sentence provides further evidence about the expected outcome.";
const fullStance = `${desktopPreview} The final sentence contains additional detail for voters who want the complete record.`;

const candidate: Candidate = {
  name: "Casey Candidate",
  party: "Independent",
  incumbent: false,
  summary: "Candidate summary",
  summary_sources: [],
  issues: {
    Healthcare: {
      stance: fullStance,
      confidence: "high",
      sources: [],
    },
  },
  career_history: [],
  education: [],
  links: [],
  social_media: {},
  roster_sources: [],
  voting_sources: [],
  donor_sources: [],
  withdrawn: false,
};

const race: Race = {
  schema_version: "0.3",
  id: "test-race-2026",
  title: "Test Race",
  office: "U.S. Senate",
  election_date: "2026-11-03",
  contest_stage: "unknown",
  updated_utc: "2026-07-01T00:00:00Z",
  generator: [],
  polling: [],
  reviews: [],
  candidates: [candidate],
};

describe("CandidateComparison", () => {
  afterEach(cleanup);

  it("expands and collapses desktop stance previews", async () => {
    const { container } = render(CandidateComparison, {
      race,
      candidates: [candidate],
    });
    const desktop = within(
      container.querySelector("[data-desktop-candidate-comparison]")!,
    );

    expect(desktop.getByText(desktopPreview)).toBeTruthy();
    const button = desktop.getByRole("button", {
      name: "Show more for Casey Candidate",
    });

    await fireEvent.click(button);
    expect(desktop.getByText(fullStance)).toBeTruthy();
    expect(
      desktop.getByRole("button", { name: "Show less for Casey Candidate" }),
    ).toBeTruthy();
  });

  it("uses opaque sticky labels so scrolled content does not show through", () => {
    const reviewedRace: Race = {
      ...race,
      validation_grade: {
        grade: "A",
        score: 95,
        passed: true,
        summary: "Publication checks passed.",
      },
    };
    const { container } = render(CandidateComparison, {
      race: reviewedRace,
      candidates: [candidate],
      compact: true,
      showQuality: true,
    });
    const desktop = within(
      container.querySelector("[data-desktop-candidate-comparison]")!,
    );

    expect(desktop.getByText("Compare").classList).toContain("bg-surface");
    expect(desktop.getByText("Compare").classList).toContain("self-stretch");
    expect(desktop.getByText("Research review").classList).toContain(
      "bg-emerald-50",
    );
  });

  it("explains the limits of the AI review score", async () => {
    const reviewedRace: Race = {
      ...race,
      validation_grade: {
        grade: "A",
        score: 95,
        passed: true,
        summary: "Publication checks passed.",
      },
    };
    const { container } = render(CandidateComparison, {
      race: reviewedRace,
      candidates: [candidate],
      compact: true,
      showQuality: true,
    });
    const desktop = within(
      container.querySelector("[data-desktop-candidate-comparison]")!,
    );

    await fireEvent.click(
      desktop.getByRole("button", { name: "About this AI review score" }),
    );

    const note = desktop.getByRole("note").textContent?.replace(/\s+/g, " ");
    expect(note).toContain("It is not independent fact-checking");
    expect(note).toContain(
      "does not validate that the underlying information is correct",
    );
  });
});
