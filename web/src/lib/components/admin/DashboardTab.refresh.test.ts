import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PipelineApiService } from "$lib/services/pipelineApiService";

/**
 * Complements `DashboardTab.test.ts` (which covers the stat cards) with the
 * refresh machinery: range switching, in-flight de-duplication, partial-failure
 * handling, per-race traffic aggregation, and the visibility/interval lifecycle.
 *
 * NOTE ON MOCK SHAPE: the sibling file uses `vi.doMock` + dynamic import, which
 * only works because it contains a single test. Repeating it here fails two
 * ways — without `vi.resetModules()` the component keeps the first test's spies
 * and every later assertion sees an uncalled mock; *with* resetModules Svelte 5
 * throws `effect_orphan`, because the re-imported component gets a different
 * copy of the Svelte runtime than the render context.
 *
 * So the service object is created once and hoisted, and only its methods are
 * reset per test. The component's import binding stays valid throughout.
 */
const { analyticsService } = vi.hoisted(() => ({
  analyticsService: {
    getOverview: vi.fn(),
    getTraffic: vi.fn(),
    getRaces: vi.fn(),
  },
}));

vi.mock("$lib/services/analyticsService", () => ({ analyticsService }));

import DashboardTab from "./DashboardTab.svelte";

function overviewPayload(overrides: Record<string, unknown> = {}) {
  return {
    total_requests: 10,
    unique_visitors: 5,
    avg_latency_ms: 25,
    error_rate: 0,
    error_count: 0,
    timeseries: [],
    hours: 24,
    ...overrides,
  };
}

function trafficPayload(overrides: Record<string, unknown> = {}) {
  return {
    configured: true,
    provider: "cloudflare",
    hours: 24,
    pageviews: 100,
    visits: 50,
    pages_per_visit: 2,
    timeseries: [],
    top_pages: [],
    top_referrers: [],
    countries: [],
    devices: [],
    fetched_at: "2026-06-13T00:00:00Z",
    error: null,
    ...overrides,
  };
}

function setHidden(hidden: boolean) {
  Object.defineProperty(document, "hidden", {
    configurable: true,
    get: () => hidden,
  });
}

beforeEach(() => {
  setHidden(false);
  analyticsService.getOverview.mockReset().mockResolvedValue(overviewPayload());
  analyticsService.getTraffic.mockReset().mockResolvedValue(trafficPayload());
  analyticsService.getRaces.mockReset().mockResolvedValue({ races: [] });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function renderDashboard(
  apiService: Partial<PipelineApiService> | undefined = {
    listRaces: vi.fn().mockResolvedValue([]),
  } as unknown as PipelineApiService,
) {
  const result = render(DashboardTab, {
    props: { apiService: apiService as PipelineApiService },
  });
  await waitFor(() => expect(analyticsService.getOverview).toHaveBeenCalled());
  return result;
}

function rangeButton(container: HTMLElement, label: string) {
  return Array.from(container.querySelectorAll("button")).find(
    (b) => b.textContent?.trim() === label,
  );
}

describe("DashboardTab time ranges", () => {
  it("loads the 24 hour window on mount", async () => {
    await renderDashboard();

    expect(analyticsService.getOverview).toHaveBeenCalledWith(24);
    expect(analyticsService.getTraffic).toHaveBeenCalledWith(24);
  });

  it.each([
    ["1h", 1],
    ["6h", 6],
    ["7d", 168],
    ["30d", 720],
  ])("reloads with %s selected", async (label, hours) => {
    const { container } = await renderDashboard();
    analyticsService.getOverview.mockClear();

    await fireEvent.click(rangeButton(container, label)!);

    await waitFor(() =>
      expect(analyticsService.getOverview).toHaveBeenCalledWith(hours),
    );
  });

  it("highlights the active range", async () => {
    const { container } = await renderDashboard();

    await fireEvent.click(rangeButton(container, "6h")!);

    await waitFor(() =>
      expect(rangeButton(container, "6h")?.className).toContain("bg-surface"),
    );
  });
});

describe("DashboardTab request de-duplication", () => {
  // Two refreshes racing (the 5-minute interval and a manual click, say) must
  // not double-fetch — loadData hands back the in-flight promise rather than
  // starting a second pass.
  it("collapses concurrent refreshes into one request pass", async () => {
    const { component } = await renderDashboard();

    // Stall only *after* mount has settled, so the pending call under test is
    // the one the two refreshes share rather than the mount's own.
    let release: (v: unknown) => void = () => {};
    analyticsService.getOverview.mockClear();
    analyticsService.getOverview.mockImplementation(
      () => new Promise((resolve) => (release = resolve)),
    );

    const first = component.refresh();
    const second = component.refresh();
    release(overviewPayload());
    await Promise.all([first, second]);

    expect(analyticsService.getOverview).toHaveBeenCalledTimes(1);
  });
});

describe("DashboardTab partial failures", () => {
  it("reports a failed overview request", async () => {
    analyticsService.getOverview.mockRejectedValue(new Error("down"));
    const { container } = await renderDashboard();

    await waitFor(() =>
      expect(container.textContent).toContain("1 dashboard request failed"),
    );
  });

  // A dead Cloudflare integration is a normal state, not a dashboard error —
  // it synthesises an "unconfigured" payload carrying the reason.
  it("treats a failed traffic request as unconfigured rather than an error", async () => {
    analyticsService.getTraffic.mockRejectedValue(new Error("no cf token"));
    const { container } = await renderDashboard();

    await waitFor(() => expect(container.textContent).toContain("no cf token"));
    expect(container.textContent).not.toContain("dashboard request failed");
  });

  it("survives an apiService that cannot list races", async () => {
    const listRaces = vi.fn().mockRejectedValue(new Error("api down"));
    const { container } = await renderDashboard({
      listRaces,
    } as unknown as PipelineApiService);

    await waitFor(() => expect(listRaces).toHaveBeenCalled());
    // The failure is swallowed as non-critical; the dashboard still renders.
    expect(container.textContent).not.toContain("api down");
  });

  it("works with no apiService at all", async () => {
    const { container } = await renderDashboard(undefined);

    await waitFor(() => expect(analyticsService.getTraffic).toHaveBeenCalled());
    expect(container.querySelector("button")).not.toBeNull();
  });
});

/**
 * NOT TESTED HERE: `aggregateRaceTraffic`, which groups top_pages into per-race
 * view counts. Its only consumer is the `<Doughnut>` dataset, so the aggregated
 * ids and totals never reach the DOM as text — and once the dataset is
 * non-empty, chart.js tries to acquire a canvas context and throws in jsdom
 * ("Cannot read properties of null (reading 'ownerDocument')").
 *
 * The logic is worth covering and currently cannot be, because it is a private
 * function feeding a canvas. Extracting it to `$lib/utils` would make it
 * directly unit-testable; that is a source change rather than a test one, so it
 * is flagged rather than done here. What is asserted below is the surrounding
 * lifecycle, which is observable.
 */

describe("DashboardTab background refresh", () => {
  it("skips the periodic refresh while the tab is hidden", async () => {
    vi.useFakeTimers();
    await renderDashboard();
    analyticsService.getOverview.mockClear();
    setHidden(true);

    await vi.advanceTimersByTimeAsync(5 * 60_000);

    expect(analyticsService.getOverview).not.toHaveBeenCalled();
  });

  it("refreshes on the interval while visible", async () => {
    vi.useFakeTimers();
    await renderDashboard();
    analyticsService.getOverview.mockClear();

    await vi.advanceTimersByTimeAsync(5 * 60_000);

    expect(analyticsService.getOverview).toHaveBeenCalled();
  });

  it("refreshes as soon as the tab becomes visible again", async () => {
    await renderDashboard();
    analyticsService.getOverview.mockClear();

    setHidden(false);
    await fireEvent(document, new Event("visibilitychange"));

    await waitFor(() =>
      expect(analyticsService.getOverview).toHaveBeenCalled(),
    );
  });

  it("does not refresh on a visibility event that hid the tab", async () => {
    await renderDashboard();
    analyticsService.getOverview.mockClear();

    setHidden(true);
    await fireEvent(document, new Event("visibilitychange"));

    expect(analyticsService.getOverview).not.toHaveBeenCalled();
  });

  // Leaving an interval or listener behind would keep polling the analytics API
  // after the admin navigates away from this tab.
  it("tears down its timer and listener on destroy", async () => {
    vi.useFakeTimers();
    const removeListener = vi.spyOn(document, "removeEventListener");
    const { unmount } = await renderDashboard();
    analyticsService.getOverview.mockClear();

    unmount();
    await vi.advanceTimersByTimeAsync(10 * 60_000);

    expect(analyticsService.getOverview).not.toHaveBeenCalled();
    expect(removeListener).toHaveBeenCalledWith(
      "visibilitychange",
      expect.any(Function),
    );
  });
});
