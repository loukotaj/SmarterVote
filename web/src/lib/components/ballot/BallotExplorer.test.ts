import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Candidate, Race, RaceSummary } from "$lib/types";
import BallotExplorer from "./BallotExplorer.svelte";

const { getRace, replaceState } = vi.hoisted(() => ({
  getRace: vi.fn(),
  replaceState: vi.fn(),
}));

vi.mock("$lib/api", () => ({ getRace }));
vi.mock("$app/navigation", () => ({ replaceState }));

function candidate(
  name: string,
  party: string,
  hasHealthcareResearch = false,
): Candidate {
  return {
    name,
    party,
    incumbent: false,
    summary: `${name} summary`,
    summary_sources: [],
    issues: hasHealthcareResearch
      ? {
          Healthcare: {
            stance: `${name} healthcare position. Additional policy context.`,
            confidence: "high",
            sources: [
              {
                url: "https://example.com/healthcare",
                type: "website",
                last_accessed: "2026-07-01",
              },
            ],
          },
        }
      : {},
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
    candidate("Dana Democrat", "Democratic", true),
    candidate("Riley Republican", "Republican", true),
    candidate("Libby Libertarian", "Libertarian"),
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
    replaceState.mockReset();
    window.history.replaceState({}, "", "/my-ballot/");
  });

  afterEach(cleanup);

  it("includes every active candidate in the inline comparison by default", async () => {
    render(BallotExplorer, { races: [summary] });

    await waitFor(() =>
      expect(
        screen.getByRole("checkbox", { name: /Libby Libertarian/ }),
      ).toBeTruthy(),
    );
    expect(
      screen.queryByRole("link", { name: /Open detailed comparison/ }),
    ).toBeNull();
    const mobileCandidates = screen.getByLabelText(
      "Candidates in this comparison",
    );
    expect(
      within(mobileCandidates).getByRole("link", {
        name: "Libby Libertarian",
      }),
    ).toBeTruthy();
    expect(
      (
        screen.getByRole("checkbox", {
          name: /Libby Libertarian/,
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
    expect(screen.getAllByText("Healthcare")).toHaveLength(2);
    expect(
      screen.getAllByText(
        /No (sourced position available|stance researched) yet\./,
      ),
    ).toHaveLength(2);

    const danaPosition = screen.getByRole("article", {
      name: "Dana Democrat position on Healthcare",
    });
    expect(
      within(danaPosition).getByText("Dana Democrat healthcare position."),
    ).toBeTruthy();
    await fireEvent.click(
      within(danaPosition).getByRole("button", {
        name: "Show more for Dana Democrat",
      }),
    );
    expect(
      within(danaPosition).getByText(
        "Dana Democrat healthcare position. Additional policy context.",
      ),
    ).toBeTruthy();

    await fireEvent.click(
      screen.getByRole("checkbox", { name: /Libby Libertarian/ }),
    );

    expect(
      within(mobileCandidates).queryByRole("link", {
        name: "Libby Libertarian",
      }),
    ).toBeNull();
    expect(screen.getAllByText("Healthcare")).toHaveLength(2);
    expect(
      screen.queryAllByText(
        /No (sourced position available|stance researched) yet\./,
      ),
    ).toHaveLength(0);
  });
});
