import { cleanup, render } from "@testing-library/svelte";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import type { RaceRecord } from "$lib/types";

const mockApi = vi.hoisted(() => ({
  listRaceRuns: vi.fn(),
  publishRace: vi.fn(),
  unpublishRaceRecord: vi.fn(),
  cancelRace: vi.fn(),
  getRaceData: vi.fn(),
  deleteDraftRace: vi.fn(),
  deleteRaceRecord: vi.fn(),
  deleteRaceRun: vi.fn(),
}));

vi.mock("$lib/services/pipelineApiService", () => {
  return {
    PipelineApiService: class {
      listRaceRuns = mockApi.listRaceRuns;
      publishRace = mockApi.publishRace;
      unpublishRaceRecord = mockApi.unpublishRaceRecord;
      cancelRace = mockApi.cancelRace;
      getRaceData = mockApi.getRaceData;
      deleteDraftRace = mockApi.deleteDraftRace;
      deleteRaceRecord = mockApi.deleteRaceRecord;
      deleteRaceRun = mockApi.deleteRaceRun;
    },
  };
});

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
    quality_score: 78,
    freshness: "recent",
    total_runs: 0,
    requests_24h: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("RacePanel status flow", () => {
  let RacePanel: typeof import("./RacePanel.svelte").default;

  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.listRaceRuns.mockResolvedValue([]);
  });

  beforeEach(async () => {
    RacePanel = (await import("./RacePanel.svelte")).default;
  });

  afterEach(() => {
    cleanup();
  });

  it("shows publish + discard controls for draft status even without draft_updated_at", () => {
    const race = makeRace({
      status: "draft",
      draft_updated_at: undefined,
      published_at: undefined,
    });

    const { getByText, queryByText } = render(RacePanel, { race, open: true });

    expect(getByText("Publish")).toBeTruthy();
    expect(getByText(/^Delete$/)).toBeTruthy();
    expect(queryByText("Unpublish")).toBeNull();
  });

  it("shows publish draft and unpublish when published race has a newer draft", () => {
    const race = makeRace({
      status: "published",
      published_at: "2026-03-01T00:00:00Z",
      draft_updated_at: "2026-03-02T00:00:00Z",
    });

    const { getByText } = render(RacePanel, { race, open: true });

    expect(getByText("Publish Draft")).toBeTruthy();
    expect(getByText("Unpublish")).toBeTruthy();
    expect(getByText("Publish Now")).toBeTruthy();
  });

  it("hides publish controls when race is published and has no active draft", () => {
    const race = makeRace({
      status: "published",
      published_at: "2026-03-01T00:00:00Z",
      draft_updated_at: undefined,
    });

    const { getByText, queryByText } = render(RacePanel, { race, open: true });

    expect(getByText("Unpublish")).toBeTruthy();
    expect(queryByText("Publish")).toBeNull();
    expect(queryByText("Publish Draft")).toBeNull();
    expect(queryByText("Publish Now")).toBeNull();
  });
});
