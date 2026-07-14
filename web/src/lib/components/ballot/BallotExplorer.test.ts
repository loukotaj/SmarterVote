import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Candidate, Race, RaceSummary } from "$lib/types";
import BallotExplorer from "./BallotExplorer.svelte";

const { getRace } = vi.hoisted(() => ({ getRace: vi.fn() }));

vi.mock("$lib/api", () => ({ getRace }));

function candidate(name: string, party: string): Candidate {
  return {
    name,
    party,
    incumbent: false,
    summary: `${name} summary`,
    summary_sources: [],
    issues: {},
    career_history: [],
    education: [],
    links: [],
    social_media: {},
  };
}

const race: Race = {
  id: "test-house-2026",
  title: "Test House Election, 2026",
  office: "U.S. House of Representatives",
  election_date: "2026-11-03",
  updated_utc: "2026-07-01T00:00:00Z",
  generator: [],
  candidates: [
    candidate("Dana Democrat", "Democratic"),
    candidate("Riley Republican", "Republican"),
    candidate("Indy Independent", "Independent"),
  ],
};

const summary: RaceSummary = {
  id: race.id,
  title: race.title,
  office: race.office,
  election_date: race.election_date,
  updated_utc: race.updated_utc,
  candidates: race.candidates,
};

describe("BallotExplorer", () => {
  beforeEach(() => {
    getRace.mockReset();
    getRace.mockResolvedValue(race);
    window.history.replaceState({}, "", "/my-ballot/");
  });

  afterEach(cleanup);

  it("adds a third-party candidate to the inline comparison", async () => {
    render(BallotExplorer, { races: [summary] });

    await waitFor(() =>
      expect(
        screen.getByRole("checkbox", { name: /Indy Independent/ }),
      ).toBeTruthy(),
    );
    expect(screen.queryByRole("link", { name: "Indy Independent" })).toBeNull();

    await fireEvent.click(
      screen.getByRole("checkbox", { name: /Indy Independent/ }),
    );

    expect(screen.getByRole("link", { name: "Indy Independent" })).toBeTruthy();
  });
});
