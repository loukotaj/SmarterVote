import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchWithAuth } = vi.hoisted(() => ({ fetchWithAuth: vi.fn() }));
vi.mock("$lib/stores/apiStore", () => ({ fetchWithAuth }));

import { analyticsService } from "./analyticsService";

function jsonResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: () => Promise.resolve(body),
    text: () =>
      Promise.resolve(typeof body === "string" ? body : JSON.stringify(body)),
  } as Response;
}

/** The base URL is environment-derived, so assert on path + query only. */
function calledUrl() {
  return new URL(fetchWithAuth.mock.calls[0][0] as string);
}

beforeEach(() => {
  fetchWithAuth.mockReset();
  fetchWithAuth.mockResolvedValue(jsonResponse({}));
});

describe("analyticsService endpoint contract", () => {
  it.each([
    [
      "getOverview",
      () => analyticsService.getOverview(),
      "/analytics/overview",
      { hours: "24" },
    ],
    [
      "getTraffic",
      () => analyticsService.getTraffic(),
      "/analytics/traffic",
      { hours: "24" },
    ],
    [
      "getRaces",
      () => analyticsService.getRaces(),
      "/analytics/races",
      { hours: "24" },
    ],
    [
      "getTimeseries",
      () => analyticsService.getTimeseries(),
      "/analytics/timeseries",
      { hours: "24", bucket: "60" },
    ],
    [
      "getPipelineMetrics",
      () => analyticsService.getPipelineMetrics(),
      "/pipeline/metrics",
      { limit: "50" },
    ],
    [
      "getGcpCosts",
      () => analyticsService.getGcpCosts(),
      "/pipeline/gcp-costs",
      { days: "30" },
    ],
  ])(
    "%s calls its endpoint with documented defaults",
    async (_name, call, path, params) => {
      await call();

      const url = calledUrl();
      expect(url.pathname).toBe(path);
      for (const [key, value] of Object.entries(params)) {
        expect(url.searchParams.get(key)).toBe(value);
      }
    },
  );

  it.each([
    ["getOverview", (h: number) => analyticsService.getOverview(h), "hours"],
    ["getTraffic", (h: number) => analyticsService.getTraffic(h), "hours"],
    ["getRaces", (h: number) => analyticsService.getRaces(h), "hours"],
    [
      "getPipelineMetrics",
      (n: number) => analyticsService.getPipelineMetrics(n),
      "limit",
    ],
    ["getGcpCosts", (n: number) => analyticsService.getGcpCosts(n), "days"],
  ])("%s forwards an explicit argument", async (_name, call, param) => {
    await call(7);
    expect(calledUrl().searchParams.get(param)).toBe("7");
  });

  it("getTimeseries forwards both hours and bucket", async () => {
    await analyticsService.getTimeseries(6, 15);

    const url = calledUrl();
    expect(url.searchParams.get("hours")).toBe("6");
    expect(url.searchParams.get("bucket")).toBe("15");
  });

  it("sends a JSON content type on every request", async () => {
    await analyticsService.getOverview();

    expect(fetchWithAuth).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: { "Content-Type": "application/json" },
      }),
    );
  });
});

describe("analyticsService optional-parameter handling", () => {
  // `hours` is genuinely optional here: omitting it must send no query string
  // at all rather than `?hours=undefined`, which the API would reject.
  it("omits the query string entirely when hours is not supplied", async () => {
    await analyticsService.getPipelineMetricsSummary();

    const url = calledUrl();
    expect(url.pathname).toBe("/pipeline/metrics/summary");
    expect(url.search).toBe("");
  });

  it("includes hours when supplied", async () => {
    await analyticsService.getPipelineMetricsSummary(12);
    expect(calledUrl().searchParams.get("hours")).toBe("12");
  });

  // 0 is falsy, so a naive `hours ? {hours} : undefined` drops it. Pinning the
  // current behaviour so a future change to that ternary is a visible decision.
  it("treats hours=0 as absent, matching the falsy-check in the source", async () => {
    await analyticsService.getPipelineMetricsSummary(0);
    expect(calledUrl().search).toBe("");
  });
});

describe("analyticsService error handling", () => {
  it("throws with status and body text on a non-ok response", async () => {
    fetchWithAuth.mockResolvedValue(
      jsonResponse("upstream exploded", false, 502),
    );

    await expect(analyticsService.getOverview()).rejects.toThrow(
      "Analytics API error 502: upstream exploded",
    );
  });

  it("surfaces a 401 distinctly so the UI can prompt re-auth", async () => {
    fetchWithAuth.mockResolvedValue(jsonResponse("Missing token", false, 401));

    await expect(analyticsService.getGcpCosts()).rejects.toThrow(
      "Analytics API error 401: Missing token",
    );
  });

  it("propagates a transport failure from fetchWithAuth unchanged", async () => {
    fetchWithAuth.mockRejectedValue(
      new Error("Network request failed: GET /x"),
    );

    await expect(analyticsService.getTraffic()).rejects.toThrow(
      "Network request failed: GET /x",
    );
  });

  it("returns the parsed payload on success", async () => {
    const payload = { total_requests: 42, unique_visitors: 7 };
    fetchWithAuth.mockResolvedValue(jsonResponse(payload));

    await expect(analyticsService.getOverview()).resolves.toEqual(payload);
  });
});
