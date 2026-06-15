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
  let confirmSpy: any;

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
    confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    cleanup();
    openSpy.mockRestore();
    confirmSpy.mockRestore();
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
    expect(openSpy).toHaveBeenCalledWith(
      "/races/active-draft?draft=true",
      "_blank"
    );
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

  it("queues an inactive race from the action selector", async () => {
    rows = [makeRace({ race_id: "ready-to-run" })];

    const { component, getByLabelText, getByText } = await renderTab();

    await component.refresh();
    await waitFor(() => expect(getByText("ready-to-run")).toBeTruthy());

    await fireEvent.change(getByLabelText("Actions for ready-to-run"), {
      target: { value: "run" },
    });

    await waitFor(() =>
      expect(mockFetchWithAuth).toHaveBeenCalledWith(
        "http://localhost:8080/api/races/queue",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ race_ids: ["ready-to-run"], options: {} }),
        })
      )
    );
    await waitFor(() =>
      expect(
        getByText("ready-to-run was added to the pipeline queue.")
      ).toBeTruthy()
    );
  });

  it("offers cancel instead of queue for an active race", async () => {
    rows = [makeRace({ race_id: "active-race", status: "running" })];

    const { component, getByLabelText, getByText, queryByText } =
      await renderTab();

    await component.refresh();
    await waitFor(() => expect(getByText("active-race")).toBeTruthy());

    expect(queryByText("Queue pipeline")).toBeNull();
    await fireEvent.change(getByLabelText("Actions for active-race"), {
      target: { value: "cancel" },
    });

    await waitFor(() =>
      expect(mockFetchWithAuth).toHaveBeenCalledWith(
        "http://localhost:8080/api/races/active-race/cancel",
        { method: "POST" },
        expect.any(Number)
      )
    );
  });
});
