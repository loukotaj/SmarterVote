import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PipelineApiService } from "$lib/services/pipelineApiService";
import type { PipelineMetricsSummary, PipelineRunRecord } from "$lib/types";

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

describe("DashboardTab run list", () => {
  let analyticsService: {
    getOverview: ReturnType<typeof vi.fn>;
    getAlerts: ReturnType<typeof vi.fn>;
    getRaces: ReturnType<typeof vi.fn>;
    getPipelineMetrics: ReturnType<typeof vi.fn>;
    getPipelineMetricsSummary: ReturnType<typeof vi.fn>;
    acknowledgeAllAlerts: ReturnType<typeof vi.fn>;
    acknowledgeAlert: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.resetModules();
    analyticsService = {
      getOverview: vi.fn(),
      getAlerts: vi.fn(),
      getRaces: vi.fn(),
      getPipelineMetrics: vi.fn(),
      getPipelineMetricsSummary: vi.fn(),
      acknowledgeAllAlerts: vi.fn(),
      acknowledgeAlert: vi.fn(),
    };
    analyticsService.getOverview.mockResolvedValue({
      total_requests: 0,
      unique_visitors: 0,
      avg_latency_ms: 0,
      error_rate: 0,
      error_count: 0,
      timeseries: [],
      hours: 24,
    });
    analyticsService.getAlerts.mockResolvedValue({ alerts: [] });
    analyticsService.getRaces.mockResolvedValue({ races: [] });
    analyticsService.getPipelineMetrics.mockResolvedValue({ records });
    analyticsService.getPipelineMetricsSummary.mockResolvedValue(summary);

    vi.doMock("$lib/services/analyticsService", () => ({ analyticsService }));
  });

  afterEach(() => {
    cleanup();
    vi.doUnmock("$lib/services/analyticsService");
  });

  async function renderDashboard() {
    const module = await import("./DashboardTab.svelte");
    return render(module.default, {
      props: {
        apiService: { listRaces: vi.fn().mockResolvedValue([]) } as unknown as PipelineApiService,
      },
    });
  }

  it("uses the metrics table as the only recent run list and links rows to run detail", async () => {
    const { component, getByText, getAllByText, queryByText } = await renderDashboard();
    const viewedRuns = vi.fn();
    const viewedRun = vi.fn();

    component.$on("view-runs", viewedRuns);
    component.$on("view-run", viewedRun);

    await component.refresh();
    await waitFor(() => expect(getByText("mn-governor-2026")).toBeTruthy());
    expect(getByText("$0.011234")).toBeTruthy();

    expect(queryByText("Recent Pipeline Runs")).toBeNull();
    expect(getAllByText("Recent Runs")).toHaveLength(1);

    await fireEvent.click(getByText("View all runs"));
    expect(viewedRuns).toHaveBeenCalledTimes(1);

    await fireEvent.click(getByText("Open"));
    expect(viewedRun).toHaveBeenCalledTimes(1);
    expect(viewedRun.mock.calls[0][0].detail).toEqual({
      runId: "run-newest",
      raceId: "mn-governor-2026",
    });
  });
});
