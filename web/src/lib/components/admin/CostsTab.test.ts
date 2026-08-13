import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CostsTab from "./CostsTab.svelte";

const { getPipelineMetricsSummary, getPipelineMetrics, getGcpCosts } =
  vi.hoisted(() => ({
    getPipelineMetricsSummary: vi.fn(),
    getPipelineMetrics: vi.fn(),
    getGcpCosts: vi.fn(),
  }));

vi.mock("$lib/services/analyticsService", () => ({
  analyticsService: {
    getPipelineMetricsSummary,
    getPipelineMetrics,
    getGcpCosts,
  },
}));

const DAY_MS = 86_400_000;

function record(overrides: Record<string, unknown> = {}) {
  return {
    race_id: "mo-senate-2024",
    cost_usd: 1,
    serper_calls: 0,
    timestamp: new Date().toISOString(),
    ...overrides,
  };
}

function setup({
  summary = { total_usd: 100 },
  windowSummary = { total_usd: 10 },
  records = [] as ReturnType<typeof record>[],
  gcp = { configured: true, total_net_usd: 5, by_service: [] } as {
    configured: boolean;
    total_net_usd?: number;
    by_service?: unknown[];
    reason?: string;
  },
} = {}) {
  // First call is the all-time summary (no args), second is the window.
  getPipelineMetricsSummary
    .mockResolvedValueOnce(summary)
    .mockResolvedValueOnce(windowSummary)
    .mockResolvedValue(windowSummary);
  getPipelineMetrics.mockResolvedValue({ records, count: records.length });
  getGcpCosts.mockResolvedValue(gcp);
}

/** Wait for the initial onMount load to settle. */
async function renderLoaded() {
  const result = render(CostsTab);
  await waitFor(() => expect(getGcpCosts).toHaveBeenCalled());
  await waitFor(() =>
    expect(result.container.textContent).not.toContain("Loading"),
  );
  return result;
}

function rangeButton(container: HTMLElement, label: string) {
  return Array.from(container.querySelectorAll("button")).find(
    (b) => b.textContent?.trim() === label,
  );
}

beforeEach(() => {
  getPipelineMetricsSummary.mockReset();
  getPipelineMetrics.mockReset();
  getGcpCosts.mockReset();
});

afterEach(cleanup);

describe("CostsTab loading", () => {
  it("requests all four cost sources on mount", async () => {
    setup();
    await renderLoaded();

    expect(getPipelineMetricsSummary).toHaveBeenCalledTimes(2);
    // All-time summary takes no window; the second call scopes to 30 days.
    expect(getPipelineMetricsSummary).toHaveBeenNthCalledWith(1);
    expect(getPipelineMetricsSummary).toHaveBeenNthCalledWith(2, 30 * 24);
    expect(getPipelineMetrics).toHaveBeenCalledWith(500);
    expect(getGcpCosts).toHaveBeenCalledWith(30);
  });

  it("defaults to the 30 day window", async () => {
    setup();
    const { container } = await renderLoaded();

    expect(rangeButton(container, "30d")?.className).toContain("bg-surface");
  });

  it.each([
    ["7d", 7],
    ["90d", 90],
  ])("reloads scoped to %s when that range is chosen", async (label, days) => {
    setup();
    const { container } = await renderLoaded();
    getGcpCosts.mockClear();
    getPipelineMetrics.mockClear();

    await fireEvent.click(rangeButton(container, label)!);

    await waitFor(() => expect(getGcpCosts).toHaveBeenCalledWith(days));
    expect(getPipelineMetrics).toHaveBeenCalledWith(500);
  });

  it("refetches on demand", async () => {
    setup();
    const { container } = await renderLoaded();
    getGcpCosts.mockClear();

    await fireEvent.click(rangeButton(container, "Refresh")!);

    await waitFor(() => expect(getGcpCosts).toHaveBeenCalledTimes(1));
  });
});

describe("CostsTab partial failure handling", () => {
  // Promise.allSettled means one dead endpoint must not blank the whole tab.
  it("reports how many cost requests failed", async () => {
    getPipelineMetricsSummary.mockRejectedValue(new Error("down"));
    getPipelineMetrics.mockResolvedValue({ records: [], count: 0 });
    getGcpCosts.mockResolvedValue({ configured: true, total_net_usd: 0 });

    const { container } = await renderLoaded();

    await waitFor(() =>
      expect(container.textContent).toContain("2 cost requests failed"),
    );
  });

  it("uses the singular form for a lone failure", async () => {
    setup();
    getPipelineMetrics.mockReset();
    getPipelineMetrics.mockRejectedValue(new Error("down"));

    const { container } = await renderLoaded();

    await waitFor(() =>
      expect(container.textContent).toContain("1 cost request failed"),
    );
  });

  it("treats a failed GCP call as 'not configured' rather than an error", async () => {
    setup();
    getGcpCosts.mockReset();
    getGcpCosts.mockRejectedValue(new Error("no billing export"));

    const { container } = await renderLoaded();

    // A rejected GCP call must not count toward the failure banner.
    expect(container.textContent).not.toContain("cost request");
    expect(container.textContent).toContain("no billing export");
  });

  it("renders without error when everything resolves", async () => {
    setup();
    const { container } = await renderLoaded();

    expect(container.textContent).not.toContain("cost requests failed");
  });
});

describe("CostsTab cost arithmetic", () => {
  it("estimates search spend from serper call volume", async () => {
    setup({
      records: [record({ serper_calls: 1500 }), record({ serper_calls: 500 })],
    });
    const { container } = await renderLoaded();

    // 2,000 calls at $1 per 1,000 = $2.00
    await waitFor(() => expect(container.textContent).toContain("$2.00"));
  });

  it("excludes records older than the selected window from the estimate", async () => {
    setup({
      records: [
        record({ serper_calls: 1000 }),
        record({
          serper_calls: 5000,
          timestamp: new Date(Date.now() - 60 * DAY_MS).toISOString(),
        }),
      ],
    });
    const { container } = await renderLoaded();

    // Only the in-window 1,000 calls count: $1.00, not $6.00.
    await waitFor(() => expect(container.textContent).toContain("$1.00"));
    expect(container.textContent).not.toContain("$6.00");
  });

  // A record with no parseable timestamp is kept rather than silently dropped —
  // losing spend from the total would understate the bill.
  it("keeps records whose timestamp cannot be parsed", async () => {
    setup({
      records: [record({ serper_calls: 3000, timestamp: "not-a-date" })],
    });
    const { container } = await renderLoaded();

    await waitFor(() => expect(container.textContent).toContain("$3.00"));
  });

  it("ranks the costliest races", async () => {
    setup({
      records: [
        record({ race_id: "cheap", cost_usd: 1 }),
        record({ race_id: "pricey", cost_usd: 7 }),
        record({ race_id: "pricey", cost_usd: 3 }),
      ],
    });
    const { container } = await renderLoaded();

    await waitFor(() => expect(container.textContent).toContain("pricey"));
    const text = container.textContent ?? "";
    expect(text.indexOf("pricey")).toBeLessThan(text.indexOf("cheap"));
    // 7 + 3 summed into one row.
    expect(text).toContain("$10.00");
  });

  it("falls back to the estimate when a run has no billed cost", async () => {
    setup({
      records: [
        record({ race_id: "est", cost_usd: undefined, estimated_usd: 4 }),
      ],
    });
    const { container } = await renderLoaded();

    await waitFor(() => expect(container.textContent).toContain("$4.00"));
  });

  it("treats a run with neither cost as zero", async () => {
    setup({
      records: [
        record({
          race_id: "free",
          cost_usd: undefined,
          estimated_usd: undefined,
        }),
      ],
    });
    const { container } = await renderLoaded();

    await waitFor(() => expect(container.textContent).toContain("free"));
    expect(container.textContent).toContain("$0.00");
  });

  it("ignores records with no race id when ranking", async () => {
    setup({
      records: [
        record({ race_id: undefined, cost_usd: 99 }),
        record({ race_id: "named", cost_usd: 1 }),
      ],
    });
    const { container } = await renderLoaded();

    await waitFor(() => expect(container.textContent).toContain("named"));
    expect(container.textContent).not.toContain("$99.00");
  });

  it("adds pipeline, search, and GCP spend into one figure", async () => {
    setup({
      windowSummary: { total_usd: 10 },
      records: [record({ serper_calls: 2000, cost_usd: 0 })],
      gcp: { configured: true, total_net_usd: 5, by_service: [] },
    });
    const { container } = await renderLoaded();

    // 10 pipeline + 2 search + 5 GCP = 17
    await waitFor(() => expect(container.textContent).toContain("$17.00"));
  });

  it("omits GCP spend from the total when billing export is off", async () => {
    setup({
      windowSummary: { total_usd: 10 },
      records: [record({ serper_calls: 2000, cost_usd: 0 })],
      gcp: { configured: false, reason: "not enabled" },
    });
    const { container } = await renderLoaded();

    await waitFor(() => expect(container.textContent).toContain("$12.00"));
  });
});
