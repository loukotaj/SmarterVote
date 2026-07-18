import { cleanup, fireEvent, render, within } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import type { Candidate, Race } from "$lib/types";
import CandidateComparison from "./CandidateComparison.svelte";

const candidate: Candidate = {
  name: "Casey Candidate",
  party: "Independent",
  incumbent: false,
  summary: "Candidate summary",
  summary_sources: [],
  issues: {
    Healthcare: {
      stance:
        "The first sentence explains the position. More detail follows here.",
      confidence: "high",
      sources: [],
    },
  },
  career_history: [],
  education: [],
  links: [],
  social_media: {},
};

const race: Race = {
  id: "test-race-2026",
  title: "Test Race",
  office: "U.S. Senate",
  election_date: "2026-11-03",
  updated_utc: "2026-07-01T00:00:00Z",
  generator: [],
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

    expect(
      desktop.getByText("The first sentence explains the position."),
    ).toBeTruthy();
    const button = desktop.getByRole("button", {
      name: "Show more for Casey Candidate",
    });

    await fireEvent.click(button);
    expect(
      desktop.getByText(
        "The first sentence explains the position. More detail follows here.",
      ),
    ).toBeTruthy();
    expect(
      desktop.getByRole("button", { name: "Show less for Casey Candidate" }),
    ).toBeTruthy();
  });
});
