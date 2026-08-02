import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import InteractiveRaceCompare from "./InteractiveRaceCompare.svelte";
import type { Race } from "$lib/types";

const mockRaces: Race[] = [
  {
    schema_version: "0.3",
    id: "race-1",
    election_date: "2026-11-03",
    title: "Race 1 Title",
    jurisdiction: "State 1",
    office: "Senate",
    contest_stage: "post_primary_general",
    updated_utc: "2026-08-01T00:00:00Z",
    generator: ["test"],
    candidates: [
      {
        name: "Candidate A",
        incumbent: true,
        roster_sources: [],
        summary: "Summary A",
        summary_sources: [],
        issues: {},
        career_history: [],
        education: [],
        voting_sources: [],
        donor_sources: [],
        links: [],
        social_media: {},
        withdrawn: false,
      },
      {
        name: "Candidate B",
        incumbent: false,
        roster_sources: [],
        summary: "Summary B",
        summary_sources: [],
        issues: {},
        career_history: [],
        education: [],
        voting_sources: [],
        donor_sources: [],
        links: [],
        social_media: {},
        withdrawn: false,
      },
    ],
    polling: [],
    reviews: [],
  },
  {
    schema_version: "0.3",
    id: "race-2",
    election_date: "2026-11-03",
    title: "Race 2 Title",
    jurisdiction: "State 2",
    office: "Governor",
    contest_stage: "post_primary_general",
    updated_utc: "2026-08-01T00:00:00Z",
    generator: ["test"],
    candidates: [
      {
        name: "Candidate C",
        incumbent: true,
        roster_sources: [],
        summary: "Summary C",
        summary_sources: [],
        issues: {},
        career_history: [],
        education: [],
        voting_sources: [],
        donor_sources: [],
        links: [],
        social_media: {},
        withdrawn: false,
      },
      {
        name: "Candidate D",
        incumbent: false,
        roster_sources: [],
        summary: "Summary D",
        summary_sources: [],
        issues: {},
        career_history: [],
        education: [],
        voting_sources: [],
        donor_sources: [],
        links: [],
        social_media: {},
        withdrawn: false,
      },
    ],
    polling: [],
    reviews: [],
  },
];

describe("InteractiveRaceCompare", () => {
  afterEach(cleanup);

  it("renders featured comparison and allows pill selection", async () => {
    render(InteractiveRaceCompare, { props: { races: mockRaces } });
    expect(screen.getByText("Race 1 Title")).toBeTruthy();

    const secondPill = screen.getByText(/State 2 · Governor/);
    await fireEvent.click(secondPill);

    expect(screen.getByText("Race 2 Title")).toBeTruthy();
  });

  it("navigates races via previous and next buttons", async () => {
    render(InteractiveRaceCompare, { props: { races: mockRaces } });

    const nextBtn = screen.getByLabelText("Next featured race");
    await fireEvent.click(nextBtn);
    expect(screen.getByText("Race 2 Title")).toBeTruthy();

    const prevBtn = screen.getByLabelText("Previous featured race");
    await fireEvent.click(prevBtn);
    expect(screen.getByText("Race 1 Title")).toBeTruthy();
  });
});
