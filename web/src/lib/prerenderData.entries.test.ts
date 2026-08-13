import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * `prerenderData` holds module-level caches (`summariesCache`, `raceCache`), so
 * every test resets the module registry and re-imports rather than sharing
 * state. `publicDataBase` is mocked through a mutable holder so a single test
 * can choose between "static GCS hosting" and "same-origin" URL shapes.
 *
 * The `import.meta.env.SSR` branches (node:fs reads during prerender) are not
 * exercised here — vitest runs with SSR false, and forcing it would test the
 * build-time path rather than the browser path these functions take in prod.
 */
const { dataBase } = vi.hoisted(() => ({
  dataBase: { value: undefined as string | undefined },
}));

vi.mock("$lib/config/api", () => ({
  publicDataBase: () => dataBase.value,
  racesApiBase: () => "https://api.test",
}));

async function loadModule() {
  vi.resetModules();
  return import("./prerenderData");
}

function okJson(body: unknown) {
  return { ok: true, json: () => Promise.resolve(body) } as Response;
}

function notFound() {
  return {
    ok: false,
    status: 404,
    json: () => Promise.resolve({}),
  } as Response;
}

const summaries = [
  { id: "mo-senate-2024", candidates: [{ name: "Jane Q. Doe" }] },
  { id: "ks-house-01", candidates: [{ name: "Bob Roe" }] },
];

beforeEach(() => {
  dataBase.value = undefined;
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("fetchPublishedRaceSummaries", () => {
  it("reads same-origin summaries when no static base is configured", async () => {
    const { fetchPublishedRaceSummaries } = await loadModule();
    const fetchFn = vi.fn().mockResolvedValue(okJson(summaries));

    await expect(fetchPublishedRaceSummaries(fetchFn)).resolves.toEqual(
      summaries,
    );
    expect(fetchFn).toHaveBeenCalledWith("/summaries.json");
  });

  it("reads from the static data host when one is configured", async () => {
    dataBase.value = "https://data.test";
    const { fetchPublishedRaceSummaries } = await loadModule();
    const fetchFn = vi.fn().mockResolvedValue(okJson(summaries));

    await fetchPublishedRaceSummaries(fetchFn);

    expect(fetchFn).toHaveBeenCalledWith("https://data.test/summaries.json");
  });

  it("fetches once and serves later callers from cache", async () => {
    const { fetchPublishedRaceSummaries } = await loadModule();
    const fetchFn = vi.fn().mockResolvedValue(okJson(summaries));

    await fetchPublishedRaceSummaries(fetchFn);
    await fetchPublishedRaceSummaries(fetchFn);

    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it("reports the status code on a failed response", async () => {
    const { fetchPublishedRaceSummaries } = await loadModule();
    const fetchFn = vi.fn().mockResolvedValue(notFound());

    await expect(fetchPublishedRaceSummaries(fetchFn)).rejects.toThrow(
      "Failed to fetch race summaries: 404",
    );
  });
});

describe("fetchPublishedRace", () => {
  it("requests the race file by id", async () => {
    const { fetchPublishedRace } = await loadModule();
    const fetchFn = vi.fn().mockResolvedValue(okJson({ id: "mo-senate-2024" }));

    await fetchPublishedRace("mo-senate-2024", fetchFn);

    expect(fetchFn).toHaveBeenCalledWith("/mo-senate-2024.json");
  });

  it("percent-encodes an id so it cannot escape its path", async () => {
    const { fetchPublishedRace } = await loadModule();
    const fetchFn = vi.fn().mockResolvedValue(okJson({}));

    await fetchPublishedRace("mo/senate 2024", fetchFn);

    expect(fetchFn).toHaveBeenCalledWith("/mo%2Fsenate%202024.json");
  });

  it("caches per id rather than globally", async () => {
    const { fetchPublishedRace } = await loadModule();
    const fetchFn = vi.fn().mockResolvedValue(okJson({}));

    await fetchPublishedRace("a", fetchFn);
    await fetchPublishedRace("a", fetchFn);
    await fetchPublishedRace("b", fetchFn);

    expect(fetchFn).toHaveBeenCalledTimes(2);
  });

  it("reports the status code and id on failure", async () => {
    const { fetchPublishedRace } = await loadModule();
    const fetchFn = vi.fn().mockResolvedValue(notFound());

    await expect(fetchPublishedRace("gone", fetchFn)).rejects.toThrow(
      "Failed to fetch race gone: 404",
    );
  });
});

describe("prerender entry generation", () => {
  // Prerendering every race is opt-in; the default build must not enumerate
  // them, or a fast build turns into a full crawl.
  it("returns no entries unless dynamic prerendering is switched on", async () => {
    vi.stubEnv("MODE", "test");
    vi.stubEnv("VITE_PRERENDER_RACES", "false");
    const { raceEntries, candidateEntries } = await loadModule();

    await expect(raceEntries()).resolves.toEqual([]);
    await expect(candidateEntries()).resolves.toEqual([]);
  });

  it.each([
    ["crawl mode", "MODE", "crawl"],
    ["the explicit flag", "VITE_PRERENDER_RACES", "true"],
  ])("enumerates races when enabled by %s", async (_label, key, value) => {
    vi.stubEnv(key, value);
    const { raceEntries } = await loadModule();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okJson(summaries)));

    await expect(raceEntries()).resolves.toEqual([
      { slug: "mo-senate-2024" },
      { slug: "ks-house-01" },
    ]);
  });

  it("slugifies candidate names into per-candidate entries", async () => {
    vi.stubEnv("MODE", "crawl");
    const { candidateEntries } = await loadModule();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okJson(summaries)));

    await expect(candidateEntries()).resolves.toEqual([
      { slug: "mo-senate-2024", candidate: "jane-q-doe" },
      { slug: "ks-house-01", candidate: "bob-roe" },
    ]);
  });

  it("tolerates a race with no candidates array", async () => {
    vi.stubEnv("MODE", "crawl");
    const { candidateEntries } = await loadModule();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(okJson([{ id: "empty" }])),
    );

    await expect(candidateEntries()).resolves.toEqual([]);
  });

  // A build must not be blocked by an unreachable data host — it degrades to
  // prerendering the fixed routes only.
  it.each([
    ["raceEntries", "raceEntries"],
    ["candidateEntries", "candidateEntries"],
  ])("%s degrades to empty when summaries cannot be loaded", async (_l, fn) => {
    vi.stubEnv("MODE", "crawl");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const mod = await loadModule();
    const loadEntries =
      fn === "raceEntries" ? mod.raceEntries : mod.candidateEntries;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(notFound()));

    await expect(loadEntries()).resolves.toEqual([]);
    expect(warn).toHaveBeenCalled();
  });
});

describe("loadPrerenderChamberForecasts", () => {
  it("reads same-origin forecasts by default", async () => {
    const { loadPrerenderChamberForecasts } = await loadModule();
    const fetchFn = vi.fn().mockResolvedValue(okJson({ house: "" }));

    await loadPrerenderChamberForecasts(fetchFn);

    expect(fetchFn).toHaveBeenCalledWith("/chamber_forecasts.json");
  });

  it("reads from the static data host when configured", async () => {
    dataBase.value = "https://data.test";
    const { loadPrerenderChamberForecasts } = await loadModule();
    const fetchFn = vi.fn().mockResolvedValue(okJson({ house: "" }));

    await loadPrerenderChamberForecasts(fetchFn);

    expect(fetchFn).toHaveBeenCalledWith(
      "https://data.test/chamber_forecasts.json",
    );
  });

  it("reports the status code on failure", async () => {
    const { loadPrerenderChamberForecasts } = await loadModule();
    const fetchFn = vi.fn().mockResolvedValue(notFound());

    await expect(loadPrerenderChamberForecasts(fetchFn)).rejects.toThrow(
      "Failed to fetch chamber forecasts: 404",
    );
  });

  it("is not cached, so a later call re-reads", async () => {
    const { loadPrerenderChamberForecasts } = await loadModule();
    const fetchFn = vi.fn().mockResolvedValue(okJson({ house: "" }));

    await loadPrerenderChamberForecasts(fetchFn);
    await loadPrerenderChamberForecasts(fetchFn);

    expect(fetchFn).toHaveBeenCalledTimes(2);
  });
});
