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

    mockFetchWithAuth = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.includes("/api/races/queue") && options?.method === "POST") {
        const body = JSON.parse(String(options.body ?? "{}"));
        return jsonResponse({
          added: (body.race_ids ?? []).map((race_id: string) => ({
            race_id,
            status: "pending",
          })),
          errors: [],
        });
      }
      if (url.endsWith("/api/races/publish") && options?.method === "POST") {
        const body = JSON.parse(String(options.body ?? "{}"));
        return jsonResponse({ published: body.race_ids ?? [], errors: [] });
      }
      return jsonResponse({ races: rows });
    });

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

  function jsonResponse(body: unknown, ok = true, status = 200) {
    return {
      ok,
      status,
      statusText: ok ? "OK" : "Error",
      json: async () => body,
      text: async () =>
        typeof body === "string" ? body : JSON.stringify(body),
    };
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
        expect.stringMatching(/\/api\/races\/queue$/),
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

  it("reports row queue API partial failures as errors", async () => {
    rows = [makeRace({ race_id: "stuck-race" })];
    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url.includes("/api/races/queue")) {
        return jsonResponse({
          added: [],
          errors: [{ race_id: "stuck-race", error: "Race is already running" }],
        });
      }
      return jsonResponse({ races: rows });
    });

    const { component, getByLabelText, getByText } = await renderTab();

    await component.refresh();
    await waitFor(() => expect(getByText("stuck-race")).toBeTruthy());

    await fireEvent.change(getByLabelText("Actions for stuck-race"), {
      target: { value: "run" },
    });

    await waitFor(() =>
      expect(getByText(/Queue failed for stuck-race/)).toBeTruthy()
    );
    expect(getByText(/Race is already running/)).toBeTruthy();
  });

  it("publishes, unpublishes, rechecks, cancels, and deletes row actions", async () => {
    rows = [
      makeRace({
        race_id: "row-action-race",
        status: "running",
        draft_exists: true,
        published_exists: true,
        draft_updated_at: "2026-02-01T00:00:00Z",
        published_at: "2026-01-01T00:00:00Z",
      }),
    ];

    const { component, getByLabelText, getByText } = await renderTab();

    await component.refresh();
    await waitFor(() => expect(getByText("row-action-race")).toBeTruthy());

    const select = getByLabelText("Actions for row-action-race");

    await fireEvent.change(select, { target: { value: "publish" } });
    await waitFor(() => expect(getByText(/was published/)).toBeTruthy());
    expect(mockFetchWithAuth).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/races\/row-action-race\/publish$/),
      { method: "POST" },
      expect.any(Number)
    );

    await fireEvent.change(select, { target: { value: "unpublish" } });
    await waitFor(() => expect(getByText(/was unpublished/)).toBeTruthy());

    await fireEvent.change(select, { target: { value: "recheck" } });
    await waitFor(() => expect(getByText(/was rechecked/)).toBeTruthy());

    await fireEvent.change(select, { target: { value: "cancel" } });
    await waitFor(() => expect(getByText(/was cancelled/)).toBeTruthy());

    await fireEvent.change(select, { target: { value: "delete" } });
    await waitFor(() =>
      expect(getByText(/stored data were deleted/)).toBeTruthy()
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
        expect.stringMatching(/\/api\/races\/active-race\/cancel$/),
        { method: "POST" },
        expect.any(Number)
      )
    );
  });

  it("reports batch queue partial failures inline and clears selected rows", async () => {
    rows = [
      makeRace({ race_id: "batch-ok" }),
      makeRace({ race_id: "batch-bad" }),
    ];
    mockFetchWithAuth.mockImplementation(
      async (url: string, options?: RequestInit) => {
        if (url.includes("/api/races/queue") && options?.method === "POST") {
          return jsonResponse({
            added: [{ race_id: "batch-ok", status: "pending" }],
            errors: [{ race_id: "batch-bad", error: "Race is already queued" }],
          });
        }
        return jsonResponse({ races: rows });
      }
    );

    const { component, getAllByLabelText, getByText, queryByText } =
      await renderTab();

    await component.refresh();
    await waitFor(() => expect(getByText("batch-ok")).toBeTruthy());

    for (const checkbox of getAllByLabelText("Select row")) {
      await fireEvent.click(checkbox);
    }

    await fireEvent.click(getByText("Batch Run"));

    await waitFor(() =>
      expect(getByText(/Queued 1 of 2 selected race/)).toBeTruthy()
    );
    expect(getByText(/batch-bad: Race is already queued/)).toBeTruthy();
    await waitFor(() => expect(queryByText(/2 races selected/)).toBeNull());
  });

  it("reports batch publish and delete failures inline", async () => {
    rows = [
      makeRace({ race_id: "batch-one", draft_exists: true }),
      makeRace({ race_id: "batch-two", draft_exists: true }),
    ];
    mockFetchWithAuth.mockImplementation(
      async (url: string, options?: RequestInit) => {
        if (url.endsWith("/api/races/publish") && options?.method === "POST") {
          return jsonResponse({
            published: ["batch-one"],
            errors: [{ race_id: "batch-two", error: "Draft not found" }],
          });
        }
        if (url.includes("/batch-two") && options?.method === "DELETE") {
          return jsonResponse("delete failed", false, 500);
        }
        return jsonResponse({ races: rows });
      }
    );

    const { component, getAllByLabelText, getByText } = await renderTab();

    await component.refresh();
    await waitFor(() => expect(getByText("batch-one")).toBeTruthy());

    for (const checkbox of getAllByLabelText("Select row")) {
      await fireEvent.click(checkbox);
    }

    await fireEvent.click(getByText("Batch Publish"));
    await waitFor(() => expect(getByText(/Published 1 of 2/)).toBeTruthy());
    expect(getByText(/batch-two: Draft not found/)).toBeTruthy();

    for (const checkbox of getAllByLabelText("Select row")) {
      await fireEvent.click(checkbox);
    }

    await fireEvent.click(getByText("Batch Delete"));
    await waitFor(() => expect(getByText(/Deleted 1 of 2/)).toBeTruthy());
    expect(getByText(/Failures: batch-two/)).toBeTruthy();
  });
});
