import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { getChamberForecasts, getRace, getRaceSummaries } from "./api";
import { sampleRaces } from "./sampleData";

describe("API Fallback Functionality", () => {
  beforeEach(() => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("should return live data when API is available", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          id: "test-race",
          title: "Live Data Race",
          candidates: [],
        }),
    });

    const result = await getRace("test-race", mockFetch);

    expect(result.title).toBe("Live Data Race");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringMatching(
        /^http:\/\/(localhost|127\.0\.0\.1):8080\/races\/test-race$/
      )
    );
  });

  it("should fallback to sample data when API fails", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("Network error"));

    const result = await getRace("mo-senate-2024", mockFetch, true);

    expect(result.id).toBe("mo-senate-2024");
    expect(result.title).toBe("Missouri U.S. Senate Race 2024");
    expect(result.jurisdiction).toBe("Missouri");
  });

  it("uses static race data only when VITE_PUBLIC_DATA_URL is configured", async () => {
    vi.stubEnv("VITE_PUBLIC_DATA_URL", "https://static.example/races");
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ id: "test-race", candidates: [] }),
    });

    const result = await getRace("test-race", mockFetch, false);

    expect(result.id).toBe("test-race");
    expect(mockFetch).toHaveBeenNthCalledWith(
      1,
      "https://static.example/races/test-race.json"
    );
  });

  it("throws when static summaries are unavailable in GCS mode", async () => {
    vi.stubEnv("VITE_PUBLIC_DATA_URL", "https://static.example/races");
    const mockFetch = vi.fn().mockResolvedValueOnce({ ok: false, status: 404 });

    await expect(getRaceSummaries(mockFetch, false)).rejects.toThrow(
      "Static data request failed: 404"
    );
  });

  it("uses configured static forecast data from GCS mode", async () => {
    vi.stubEnv("VITE_PUBLIC_DATA_URL", "https://static.example/races");
    const summariesPayload = [
      {
        id: "tx-senate-2026",
        title: "Texas Senate",
        office: "United States Senate",
        jurisdiction: "Texas",
        state: "Texas",
        election_date: "2026-11-03",
        updated_utc: "2026-01-01T00:00:00Z",
        candidates: [],
        forecast: {
          predicted_winner_party: "Republican",
          rating: "safe_r",
        },
      },
    ];
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(summariesPayload),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            house: "Republicans are favored in the House.",
            senate: "Republicans are favored in the Senate.",
            governors: "Republicans are favored in governor races.",
            updated_at: "2026-01-01T00:00:00Z",
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(summariesPayload),
      });

    const summaries = await getRaceSummaries(mockFetch, false);
    const chamberForecasts = await getChamberForecasts(mockFetch, false);

    expect(summaries.length).toBeGreaterThan(0);
    expect(chamberForecasts.chambers?.senate?.control_party).toBe("Republican");
    expect(mockFetch).toHaveBeenCalledWith(
      "https://static.example/races/summaries.json"
    );
    expect(mockFetch).toHaveBeenCalledWith(
      "https://static.example/races/chamber_forecasts.json"
    );
  });

  it("should fallback to generic sample data for unknown race IDs", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("Network error"));

    const result = await getRace("unknown-race", mockFetch, true);

    expect(result.id).toBe("unknown-race");
    expect(result.title).toBe("Sample Race Data (unknown-race)");
    expect(result.candidates).toHaveLength(3); // Updated to match actual sample data
  });

  it("should throw error when fallback is disabled", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("Network error"));

    await expect(getRace("test-race", mockFetch, false)).rejects.toThrow(
      "Network error"
    );
  });

  it("should have all required sample races", () => {
    const expectedRaces = [
      "mo-senate-2024",
      "ca-senate-2024",
      "ny-house-03-2024",
      "tx-governor-2024",
    ];

    expectedRaces.forEach((raceId) => {
      expect(sampleRaces[raceId]).toBeDefined();
      expect(sampleRaces[raceId].id).toBe(raceId);
    });
  });
});
