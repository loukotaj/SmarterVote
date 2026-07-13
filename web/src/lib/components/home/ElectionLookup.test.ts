import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ElectionLookup from "./ElectionLookup.svelte";

const { lookupElectionGeography } = vi.hoisted(() => ({
  lookupElectionGeography: vi.fn(),
}));

vi.mock("$lib/services/electionLookup", async () => {
  const actual = await vi.importActual<
    typeof import("$lib/services/electionLookup")
  >("$lib/services/electionLookup");
  return { ...actual, lookupElectionGeography };
});

const races = [
  {
    id: "md-house-04-2026",
    title: "Maryland's 4th Congressional District Election, 2026",
    office: "U.S. House of Representatives",
    jurisdiction: "Maryland's 4th Congressional District",
    state: "Maryland",
    election_date: "2026-11-03",
    updated_utc: "2026-07-01T00:00:00Z",
    candidates: [],
  },
];

describe("ElectionLookup", () => {
  beforeEach(() => lookupElectionGeography.mockReset());
  afterEach(cleanup);

  it("explains privacy and renders matched national research", async () => {
    lookupElectionGeography.mockResolvedValue({
      state: "Maryland",
      congressionalDistrict: "04",
    });
    render(ElectionLookup, { races });

    expect(screen.getByLabelText("Home address")).toBeTruthy();
    expect(screen.getByText(/Smarter\.Vote does not save/i)).toBeTruthy();
    expect(screen.getByText(/not yet a complete local ballot/i)).toBeTruthy();

    const input = screen.getByLabelText("Home address") as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "A complete address" } });
    await fireEvent.click(
      screen.getByRole("button", { name: "Show my elections" }),
    );

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Your election guide" }),
      ).toBeTruthy(),
    );
    expect(screen.getByText(/Maryland · U\.S\. House District 4/)).toBeTruthy();
    expect(
      screen.getByRole("tab", { name: "U.S. House", selected: true }),
    ).toBeTruthy();
    expect(sessionStorage.getItem("smarterVote.ballot")).toContain(
      "md-house-04-2026",
    );
    expect(screen.queryByLabelText("Home address")).toBeNull();
    expect(
      screen.getByRole("button", { name: "← Search another address" }),
    ).toBeTruthy();
  });
});
