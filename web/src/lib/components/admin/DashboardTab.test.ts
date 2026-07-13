import { cleanup, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PipelineApiService } from "$lib/services/pipelineApiService";

describe("DashboardTab basic layout", () => {
  let analyticsService: {
    getOverview: ReturnType<typeof vi.fn>;
    getTraffic: ReturnType<typeof vi.fn>;
    getAlerts: ReturnType<typeof vi.fn>;
    getRaces: ReturnType<typeof vi.fn>;
    acknowledgeAllAlerts: ReturnType<typeof vi.fn>;
    acknowledgeAlert: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    vi.clearAllMocks();
    analyticsService = {
      getOverview: vi.fn(),
      getTraffic: vi.fn(),
      getAlerts: vi.fn(),
      getRaces: vi.fn(),
      acknowledgeAllAlerts: vi.fn(),
      acknowledgeAlert: vi.fn(),
    };
    analyticsService.getOverview.mockResolvedValue({
      total_requests: 0,
      unique_visitors: 0,
      avg_latency_ms: 25,
      error_rate: 2,
      error_count: 0,
      timeseries: [],
      hours: 24,
    });
    analyticsService.getTraffic.mockResolvedValue({
      configured: true,
      provider: "cloudflare",
      hours: 24,
      pageviews: 120,
      visits: 80,
      pages_per_visit: 1.5,
      timeseries: [],
      top_pages: [],
      top_referrers: [],
      countries: [],
      devices: [],
      fetched_at: "2026-06-13T00:00:00Z",
      error: null,
    });
    analyticsService.getAlerts.mockResolvedValue({ alerts: [] });
    analyticsService.getRaces.mockResolvedValue({ races: [] });

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
        apiService: {
          listRaces: vi.fn().mockResolvedValue([]),
        } as unknown as PipelineApiService,
      },
    });
  }

  it("renders traffic stats cards correctly", async () => {
    const { component, getByText } = await renderDashboard();
    await component.refresh();
    await waitFor(() => expect(getByText("Page Views (24h)")).toBeTruthy());
    expect(getByText("120")).toBeTruthy();
    expect(getByText("80")).toBeTruthy();
    expect(getByText("1.5")).toBeTruthy();
    expect(getByText("2% errors")).toBeTruthy();
  });
});
