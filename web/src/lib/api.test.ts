import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { getRace, getRaceSummaries } from "./api";
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
      "http://localhost:8080/races/test-race"
    );
  });

  it("should fallback to sample data when API fails", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("Network error"));

    const result = await getRace("mo-senate-2024", mockFetch, true);

    expect(result.id).toBe("mo-senate-2024");
    expect(result.title).toBe("Missouri U.S. Senate Race 2024");
    expect(result.jurisdiction).toBe("Missouri");
  });

  it("falls back to the API when static race data is unavailable", async () => {
    vi.stubEnv("VITE_PUBLIC_DATA_URL", "https://static.example/races");
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 403 })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ id: "test-race", candidates: [] }),
      });

    const result = await getRace("test-race", mockFetch, false);

    expect(result.id).toBe("test-race");
    expect(mockFetch).toHaveBeenNthCalledWith(
      1,
      "https://static.example/races/test-race.json"
    );
    expect(mockFetch).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8080/races/test-race"
    );
  });

  it("falls back to API summaries when the static index is missing", async () => {
    vi.stubEnv("VITE_PUBLIC_DATA_URL", "https://static.example/races");
    const mockFetch = vi
      .fn()
      .mockRejectedValueOnce(new Error("static unavailable"))
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([{ id: "test-race", candidates: [] }]),
      });

    const result = await getRaceSummaries(mockFetch, false);

    expect(result).toHaveLength(1);
    expect(mockFetch).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8080/races/summaries"
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
