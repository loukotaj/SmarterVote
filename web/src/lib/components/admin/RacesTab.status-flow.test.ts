import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import type { RaceRecord } from "$lib/types";

function makeRace(overrides: Partial<RaceRecord> = {}): RaceRecord {
  return {
    race_id: "ga-senate-2026",
    title: "Georgia Senate 2026",
    office: "Senate",
    jurisdiction: "Georgia",
    election_date: "2026-11-03",
    status: "empty",
    published_at: undefined,
    draft_updated_at: undefined,
    candidate_count: 2,
    freshness: "recent",
    total_runs: 0,
    requests_24h: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("RacesTab preview and render flow", () => {
  let rows: RaceRecord[] = [];
  let mockFetchWithAuth: any;
  let openSpy: any;

  beforeEach(() => {
    vi.clearAllMocks();
    rows = [];
    vi.resetModules();

    mockFetchWithAuth = vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => ({ races: rows }),
    }));

    vi.doMock("$lib/stores/apiStore", () => {
      return {
        fetchWithAuth: mockFetchWithAuth,
      };
    });

    openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
  });

  afterEach(() => {
    cleanup();
    openSpy.mockRestore();
    vi.doUnmock("$lib/stores/apiStore");
  });

  async function renderTab() {
    const module = await import("./RacesTab.svelte");
    return render(module.default);
  }

  it("renders the list of races successfully", async () => {
    rows = [
      makeRace({
        race_id: "ga-senate-2026",
        status: "published",
        published_at: "2026-03-01T00:00:00Z",
      }),
    ];

    const { component, getByText } = await renderTab();

    await component.refresh();
    await waitFor(() => expect(mockFetchWithAuth).toHaveBeenCalled());
    await waitFor(() => expect(getByText("ga-senate-2026")).toBeTruthy());
  });

  it("opens draft preview when draft exists", async () => {
    rows = [
      makeRace({
        race_id: "active-draft",
        status: "draft",
        draft_exists: true,
        published_exists: false,
      }),
    ];

    const { component, getByText } = await renderTab();

    await component.refresh();
    await waitFor(() => expect(getByText("active-draft")).toBeTruthy());

    await fireEvent.click(getByText("View Draft"));
    expect(openSpy).toHaveBeenCalledWith("/races/active-draft?draft=true", "_blank");
  });

  it("opens normal page preview when published and no newer draft exists", async () => {
    rows = [
      makeRace({
        race_id: "published-only",
        status: "published",
        draft_exists: false,
        published_exists: true,
      }),
    ];

    const { component, getByText } = await renderTab();

    await component.refresh();
    await waitFor(() => expect(getByText("published-only")).toBeTruthy());

    await fireEvent.click(getByText("View Page"));
    expect(openSpy).toHaveBeenCalledWith("/races/published-only", "_blank");
  });
});
