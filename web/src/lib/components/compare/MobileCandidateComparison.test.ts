import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import type { Candidate, Race, Source } from "$lib/types";
import MobileCandidateComparison from "./MobileCandidateComparison.svelte";

const sources: Source[] = [
  {
    url: "https://example.com/first",
    type: "news",
    title: "First source",
    last_accessed: "2026-07-17",
    is_fresh: false,
  },
  {
    url: "https://example.com/second",
    type: "government",
    title: "Second source",
    last_accessed: "2026-07-17",
    is_fresh: false,
  },
];

const candidate: Candidate = {
  name: "Alex Example",
  party: "Independent",
  incumbent: false,
  summary: "Candidate summary",
  summary_sources: [],
  image_url: "https://example.com/missing.jpg",
  issues: {
    Healthcare: {
      stance:
        "U.S. Senate candidate supports expanding coverage. More details follow.",
      confidence: "high",
      sources,
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
  id: "example-race",
  election_date: "2026-11-03",
  contest_stage: "unknown",
  candidates: [candidate],
  updated_utc: "2026-07-17T00:00:00Z",
  generator: ["test"],
  polling: [],
  reviews: [],
};

describe("MobileCandidateComparison", () => {
  afterEach(cleanup);

  it("previews a complete stance and expands its full source list", async () => {
    render(MobileCandidateComparison, { race, candidates: [candidate] });

    expect(
      screen.getByText("U.S. Senate candidate supports expanding coverage."),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: /First source/ })).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Second source/ })).toBeNull();

    await fireEvent.click(
      screen.getByRole("button", {
        name: "Show 1 more source for Alex Example",
      }),
    );
    expect(screen.getByRole("link", { name: /Second source/ })).toBeTruthy();
    expect(
      screen.getByRole("button", {
        name: "Show fewer sources for Alex Example",
      }),
    ).toBeTruthy();
  });

  it("shows initials if a candidate image fails", async () => {
    render(MobileCandidateComparison, { race, candidates: [candidate] });

    await fireEvent.error(document.querySelector("img") as HTMLImageElement);
    expect(screen.getByText("AE")).toBeTruthy();
  });

  it("uses a short expandable position preview in compact mode", async () => {
    const longStance =
      "Alex Example supports expanding affordable healthcare coverage while protecting rural hospitals, lowering prescription costs, and preserving access to local doctors. The complete position includes additional implementation details.";
    const compactCandidate = {
      ...candidate,
      issues: {
        Healthcare: {
          ...candidate.issues.Healthcare,
          stance: longStance,
        },
      },
    } as Candidate;

    render(MobileCandidateComparison, {
      race,
      candidates: [compactCandidate],
      compact: true,
      collapseText: true,
    });

    expect(screen.queryByText(longStance)).toBeNull();
    expect(screen.queryByRole("link", { name: /First source/ })).toBeNull();

    await fireEvent.click(
      screen.getByRole("button", { name: "Show more for Alex Example" }),
    );

    expect(screen.getByText(longStance)).toBeTruthy();
    expect(screen.getByRole("link", { name: /First source/ })).toBeTruthy();
  });
});
