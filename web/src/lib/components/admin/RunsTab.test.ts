import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PipelineApiService } from "$lib/services/pipelineApiService";
import type {
  PipelineMetricsSummary,
  PipelineRunRecord,
  RunHistoryItem,
} from "$lib/types";

const records: PipelineRunRecord[] = [
  {
    run_id: "run-newest",
    race_id: "mn-governor-2026",
    status: "completed",
    timestamp: "2026-05-04T12:00:00Z",
    model: "gpt-5.4-mini",
    prompt_tokens: 100,
    completion_tokens: 50,
    total_tokens: 150,
    estimated_usd: 0.012,
    cost_usd: 0.011234,
    cost_source: "provider",
    model_breakdown: {},
    duration_s: 42,
    candidate_count: 3,
    cheap_mode: true,
  },
];

const summary: PipelineMetricsSummary = {
  total_runs: 1,
  total_usd: 0.012,
  avg_usd: 0.012,
  recent_30d_usd: 0.012,
  success_rate: 1,
  cheap_runs: 1,
  avg_cheap_usd: 0.012,
  full_runs: 0,
  avg_full_usd: 0,
  avg_usd_per_candidate: 0.004,
};

const mockRuns: RunHistoryItem[] = [
  {
    run_id: "run-newest",
    race_id: "mn-governor-2026",
    status: "completed",
    started_at: "2026-05-04T12:00:00Z",
    completed_at: "2026-05-04T12:00:42Z",
    duration_ms: 42000,
    progress: 100,
    steps: [],
  } as unknown as RunHistoryItem,
];

describe("RunsTab", () => {
  let analyticsService: {
    getPipelineMetrics: ReturnType<typeof vi.fn>;
    getPipelineMetricsSummary: ReturnType<typeof vi.fn>;
  };
  let apiService: {
    getRunDetails: ReturnType<typeof vi.fn>;
    getRunLogs: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    vi.clearAllMocks();
    analyticsService = {
      getPipelineMetrics: vi.fn(),
      getPipelineMetricsSummary: vi.fn(),
    };
    analyticsService.getPipelineMetrics.mockResolvedValue({ records });
    analyticsService.getPipelineMetricsSummary.mockResolvedValue(summary);

    apiService = {
      getRunDetails: vi.fn().mockResolvedValue({
        run_id: "run-newest",
        race_id: "mn-governor-2026",
        status: "completed",
        started_at: "2026-05-04T12:00:00Z",
        completed_at: "2026-05-04T12:00:42Z",
        duration_ms: 42000,
        progress: 100,
        options: { research_model: "gpt-5.4-mini" },
        steps: [],
      }),
      getRunLogs: vi.fn().mockResolvedValue({ logs: [], total: 0 }),
    };

    vi.doMock("$lib/services/analyticsService", () => ({ analyticsService }));
  });

  afterEach(() => {
    cleanup();
    vi.doUnmock("$lib/services/analyticsService");
  });

  async function renderRunsTab() {
    const module = await import("./RunsTab.svelte");
    return render(module.default, {
      props: {
        runs: mockRuns,
        queueItems: [],
        isRefreshing: false,
        isPruning: false,
        apiService: apiService as unknown as PipelineApiService,
      },
    });
  }

  it("renders pipeline metrics summary and historical runs", async () => {
    const { component, getByText } = await renderRunsTab();

    // Trigger metrics loading and await it
    await component.fetchMetrics();

    await waitFor(() => expect(getByText("Total Runs (24h)")).toBeTruthy());
    expect(getByText("Success Rate")).toBeTruthy();
    expect(getByText("100.0%")).toBeTruthy();
    expect(analyticsService.getPipelineMetrics).toHaveBeenCalledWith(50);

    // Check historical run item
    expect(getByText("mn-governor-2026")).toBeTruthy();
  });

  it("opens logs drawer on clicking run history item", async () => {
    const { component, getByText } = await renderRunsTab();

    // Trigger metrics loading and await it
    await component.fetchMetrics();

    await waitFor(() => expect(getByText("mn-governor-2026")).toBeTruthy());
    const runRow = getByText("mn-governor-2026");
    await fireEvent.click(runRow);

    await waitFor(() =>
      expect(apiService.getRunDetails).toHaveBeenCalledWith("run-newest"),
    );
    // getRunLogs now takes an opaque Firestore cursor rather than a numeric
    // `since` index; the initial drawer load passes no cursor.
    expect(apiService.getRunLogs).toHaveBeenCalledWith("run-newest");

    // Expect drawer content to be displayed
    await waitFor(() => expect(getByText("Run Logs: run-newest")).toBeTruthy());
  });
});
