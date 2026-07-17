import { beforeEach, describe, expect, it, vi } from "vitest";

describe("published data request caches", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("retries summaries after a failed request", async () => {
    const { fetchPublishedRaceSummaries } = await import("./prerenderData");
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 503 })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([{ id: "retry-race" }]),
      });

    await expect(fetchPublishedRaceSummaries(fetchFn)).rejects.toThrow(
      "Failed to fetch race summaries: 503",
    );
    await expect(fetchPublishedRaceSummaries(fetchFn)).resolves.toEqual([
      { id: "retry-race" },
    ]);
    expect(fetchFn).toHaveBeenCalledTimes(2);
  });

  it("retries an individual race after a failed request", async () => {
    const { fetchPublishedRace } = await import("./prerenderData");
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 404 })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ id: "retry-race", candidates: [] }),
      });

    await expect(fetchPublishedRace("retry-race", fetchFn)).rejects.toThrow(
      "Failed to fetch race retry-race: 404",
    );
    await expect(
      fetchPublishedRace("retry-race", fetchFn),
    ).resolves.toMatchObject({ id: "retry-race" });
    expect(fetchFn).toHaveBeenCalledTimes(2);
  });
});
