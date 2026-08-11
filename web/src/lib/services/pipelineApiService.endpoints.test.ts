/**
 * Endpoint-surface tests for PipelineApiService.
 *
 * `pipelineApiService.test.ts` covers a handful of behaviours in depth. This
 * file covers the *shape* of the whole surface: every method's URL, HTTP verb,
 * timeout class, envelope unwrapping, and error text. Those are the details a
 * refactor silently gets wrong — a wrong verb or a dropped `?draft=true` still
 * type-checks and still returns a promise.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchWithAuth } = vi.hoisted(() => ({ fetchWithAuth: vi.fn() }));
vi.mock("$lib/stores/apiStore", () => ({ fetchWithAuth }));

import { PipelineApiService } from "./pipelineApiService";
import {
  API_TIMEOUT_SHORT,
  API_TIMEOUT_DEFAULT,
  API_TIMEOUT_ARTIFACT,
} from "$lib/config/constants";

const BASE = "https://api.test";
const svc = new PipelineApiService(BASE);

function jsonResponse(
  body: unknown,
  ok = true,
  status = 200,
  statusText = "OK",
) {
  return {
    ok,
    status,
    statusText,
    json: () => Promise.resolve(body),
    text: () =>
      Promise.resolve(typeof body === "string" ? body : JSON.stringify(body)),
  } as Response;
}

function lastCall() {
  const [url, init, timeout] = fetchWithAuth.mock.calls.at(-1) as [
    string,
    RequestInit | undefined,
    number | undefined,
  ];
  return { url, init: init ?? {}, timeout };
}

beforeEach(() => {
  fetchWithAuth.mockReset();
});

// ---------------------------------------------------------------------------
// Endpoint shape: URL, verb, timeout class
// ---------------------------------------------------------------------------

type Case = {
  name: string;
  run: () => Promise<unknown>;
  path: string;
  method?: string;
  timeout?: number;
  payload?: unknown;
};

const cases: Case[] = [
  // -- Runs -----------------------------------------------------------------
  {
    name: "loadRunHistory",
    run: () => svc.loadRunHistory(),
    path: "/runs",
    timeout: API_TIMEOUT_SHORT,
    payload: { runs: [] },
  },
  {
    name: "pruneRuns",
    run: () => svc.pruneRuns(),
    path: "/runs",
    method: "DELETE",
    timeout: API_TIMEOUT_SHORT,
  },
  {
    name: "deleteRun",
    run: () => svc.deleteRun("run-1"),
    path: "/runs/run-1",
    method: "DELETE",
    timeout: API_TIMEOUT_SHORT,
  },
  {
    name: "getRunDetails",
    run: () => svc.getRunDetails("run-1"),
    path: "/runs/run-1",
    timeout: API_TIMEOUT_DEFAULT,
  },
  {
    name: "getRunDiagnostics",
    run: () => svc.getRunDiagnostics("run-1"),
    path: "/runs/run-1/diagnostics",
    timeout: API_TIMEOUT_ARTIFACT,
  },
  // -- Published races ------------------------------------------------------
  {
    name: "loadPublishedRaces",
    run: () => svc.loadPublishedRaces(),
    path: "/races/summaries",
    timeout: API_TIMEOUT_SHORT,
    payload: [],
  },
  {
    name: "getPublishedRace",
    run: () => svc.getPublishedRace("mo-senate-2024"),
    path: "/races/mo-senate-2024",
    timeout: API_TIMEOUT_DEFAULT,
  },
  {
    name: "deletePublishedRace",
    run: () => svc.deletePublishedRace("mo-senate-2024"),
    path: "/api/races/mo-senate-2024/unpublish",
    method: "POST",
    timeout: API_TIMEOUT_DEFAULT,
  },
  // -- Drafts ---------------------------------------------------------------
  {
    name: "getDraftRace",
    run: () => svc.getDraftRace("mo-senate-2024"),
    path: "/api/races/mo-senate-2024/data?draft=true",
    timeout: API_TIMEOUT_DEFAULT,
  },
  {
    name: "unpublishRace",
    run: () => svc.unpublishRace("mo-senate-2024"),
    path: "/api/races/mo-senate-2024/unpublish",
    method: "POST",
    timeout: API_TIMEOUT_DEFAULT,
  },
  {
    name: "deleteDraftRace",
    run: () => svc.deleteDraftRace("mo-senate-2024"),
    path: "/api/races/mo-senate-2024/draft",
    method: "DELETE",
    timeout: API_TIMEOUT_DEFAULT,
  },
  // -- Queue ----------------------------------------------------------------
  {
    name: "loadQueue",
    run: () => svc.loadQueue(),
    path: "/api/queue",
    timeout: API_TIMEOUT_SHORT,
  },
  {
    name: "addToQueue",
    run: () => svc.addToQueue(["a"]),
    path: "/api/races/queue",
    method: "POST",
    timeout: undefined,
  },
  {
    name: "removeQueueItem",
    run: () => svc.removeQueueItem("item-1"),
    path: "/api/queue/item-1",
    method: "DELETE",
    timeout: API_TIMEOUT_SHORT,
  },
  {
    name: "clearFinishedQueue",
    run: () => svc.clearFinishedQueue(),
    path: "/api/queue/finished",
    method: "DELETE",
    timeout: undefined,
  },
  {
    name: "clearPendingQueue",
    run: () => svc.clearPendingQueue(),
    path: "/api/queue/pending",
    method: "DELETE",
    timeout: undefined,
  },
  // -- Race records ---------------------------------------------------------
  {
    name: "getRaceRecord",
    run: () => svc.getRaceRecord("mo-senate-2024"),
    path: "/api/races/mo-senate-2024",
    timeout: API_TIMEOUT_SHORT,
  },
  {
    name: "deleteRaceRecord",
    run: () => svc.deleteRaceRecord("mo-senate-2024"),
    path: "/api/races/mo-senate-2024",
    method: "DELETE",
    timeout: API_TIMEOUT_DEFAULT,
  },
  {
    name: "cancelRace",
    run: () => svc.cancelRace("mo-senate-2024"),
    path: "/api/races/mo-senate-2024/cancel",
    method: "POST",
    timeout: API_TIMEOUT_SHORT,
  },
  {
    name: "recheckRace",
    run: () => svc.recheckRace("mo-senate-2024"),
    path: "/api/races/mo-senate-2024/recheck",
    method: "POST",
    timeout: API_TIMEOUT_DEFAULT,
  },
  {
    name: "recheckAllRaces",
    run: () => svc.recheckAllRaces(),
    path: "/api/races/recheck",
    method: "POST",
    timeout: API_TIMEOUT_ARTIFACT,
  },
  {
    name: "runRace",
    run: () => svc.runRace("mo-senate-2024"),
    path: "/api/races/mo-senate-2024/run",
    method: "POST",
    timeout: undefined,
  },
  {
    name: "publishRace",
    run: () => svc.publishRace("mo-senate-2024"),
    path: "/api/races/mo-senate-2024/publish",
    method: "POST",
    timeout: API_TIMEOUT_DEFAULT,
  },
  {
    name: "batchPublishRaces",
    run: () => svc.batchPublishRaces(["a", "b"]),
    path: "/api/races/publish",
    method: "POST",
    timeout: API_TIMEOUT_ARTIFACT,
  },
  {
    name: "unpublishRaceRecord",
    run: () => svc.unpublishRaceRecord("mo-senate-2024"),
    path: "/api/races/mo-senate-2024/unpublish",
    method: "POST",
    timeout: API_TIMEOUT_DEFAULT,
  },
  // -- Per-race runs --------------------------------------------------------
  {
    name: "listRaceRuns",
    run: () => svc.listRaceRuns("mo-senate-2024"),
    path: "/api/races/mo-senate-2024/runs?limit=20",
    timeout: API_TIMEOUT_SHORT,
    payload: { runs: [] },
  },
  {
    name: "getRaceRun",
    run: () => svc.getRaceRun("mo-senate-2024", "run-1"),
    path: "/api/races/mo-senate-2024/runs/run-1",
    timeout: API_TIMEOUT_DEFAULT,
  },
  {
    name: "deleteRaceRun",
    run: () => svc.deleteRaceRun("mo-senate-2024", "run-1"),
    path: "/api/races/mo-senate-2024/runs/run-1",
    method: "DELETE",
    timeout: API_TIMEOUT_SHORT,
  },
  // -- Race data and versions ----------------------------------------------
  {
    name: "getRaceData (published)",
    run: () => svc.getRaceData("mo-senate-2024"),
    path: "/api/races/mo-senate-2024/data",
    timeout: API_TIMEOUT_DEFAULT,
  },
  {
    name: "getRaceData (draft)",
    run: () => svc.getRaceData("mo-senate-2024", true),
    path: "/api/races/mo-senate-2024/data?draft=true",
    timeout: API_TIMEOUT_DEFAULT,
  },
  {
    name: "listRaceVersions",
    run: () => svc.listRaceVersions("mo-senate-2024"),
    path: "/api/races/mo-senate-2024/versions",
    timeout: API_TIMEOUT_SHORT,
    payload: { versions: [], count: 0 },
  },
  {
    name: "getRaceVersionData",
    run: () => svc.getRaceVersionData("mo-senate-2024", "v1.json"),
    path: "/api/races/mo-senate-2024/versions/v1.json",
    timeout: API_TIMEOUT_DEFAULT,
  },
  {
    name: "restoreVersionAsDraft",
    run: () => svc.restoreVersionAsDraft("mo-senate-2024", "v1.json"),
    path: "/api/races/mo-senate-2024/versions/v1.json/restore",
    method: "POST",
    timeout: API_TIMEOUT_DEFAULT,
  },
  // -- Chamber forecasts ----------------------------------------------------
  {
    name: "getPublishedChamberForecasts",
    run: () => svc.getPublishedChamberForecasts(),
    path: "/races/chamber_forecasts",
    timeout: API_TIMEOUT_SHORT,
  },
  {
    name: "publishChamberForecastDraft",
    run: () => svc.publishChamberForecastDraft(),
    path: "/api/races/chamber_forecasts/publish",
    method: "POST",
    timeout: API_TIMEOUT_DEFAULT,
  },
];

describe("PipelineApiService endpoint shape", () => {
  it.each(cases.map((c) => [c.name, c] as const))(
    "%s targets the documented URL, verb, and timeout",
    async (_name, testCase) => {
      fetchWithAuth.mockResolvedValue(jsonResponse(testCase.payload ?? {}));

      await testCase.run();

      const { url, init, timeout } = lastCall();
      expect(url).toBe(`${BASE}${testCase.path}`);
      expect(init.method ?? "GET").toBe(testCase.method ?? "GET");
      expect(timeout).toBe(testCase.timeout);
    },
  );
});

// ---------------------------------------------------------------------------
// Error propagation
// ---------------------------------------------------------------------------

describe("PipelineApiService error propagation", () => {
  it.each(cases.map((c) => [c.name, c] as const))(
    "%s rejects on a non-ok response",
    async (_name, testCase) => {
      fetchWithAuth.mockResolvedValue(
        jsonResponse("upstream boom", false, 500, "Internal Server Error"),
      );

      await expect(testCase.run()).rejects.toThrow(/HTTP 500/);
    },
  );

  // The mutating endpoints append the response body, because "HTTP 400" alone
  // is useless when the API is explaining *why* a publish was refused.
  it.each([
    ["deleteRun", () => svc.deleteRun("r")],
    ["pruneRuns", () => svc.pruneRuns()],
    ["deletePublishedRace", () => svc.deletePublishedRace("r")],
    ["unpublishRace", () => svc.unpublishRace("r")],
    ["addToQueue", () => svc.addToQueue(["r"])],
    ["runRace", () => svc.runRace("r")],
    ["publishRace", () => svc.publishRace("r")],
    ["batchPublishRaces", () => svc.batchPublishRaces(["r"])],
    ["unpublishRaceRecord", () => svc.unpublishRaceRecord("r")],
  ])("%s includes the response body in its error", async (_name, run) => {
    fetchWithAuth.mockResolvedValue(
      jsonResponse("race is not publishable", false, 400, "Bad Request"),
    );

    await expect(run()).rejects.toThrow(
      "HTTP 400: Bad Request. race is not publishable",
    );
  });

  // Every method that appends a body has its own `.catch(() => "Unknown error")`.
  // An unreadable body must still produce a usable error rather than a rejected
  // promise from inside the error path itself.
  it.each([
    ["deleteRun", () => svc.deleteRun("r")],
    ["pruneRuns", () => svc.pruneRuns()],
    ["deletePublishedRace", () => svc.deletePublishedRace("r")],
    ["unpublishRace", () => svc.unpublishRace("r")],
    ["deleteDraftRace", () => svc.deleteDraftRace("r")],
    ["addToQueue", () => svc.addToQueue(["r"])],
    ["queueRaces", () => svc.queueRaces(["r"])],
    ["runRace", () => svc.runRace("r")],
    ["publishRace", () => svc.publishRace("r")],
    ["batchPublishRaces", () => svc.batchPublishRaces(["r"])],
    ["unpublishRaceRecord", () => svc.unpublishRaceRecord("r")],
  ])(
    "%s falls back to 'Unknown error' when the body cannot be read",
    async (_name, run) => {
      fetchWithAuth.mockResolvedValue({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        text: () => Promise.reject(new Error("stream already consumed")),
      } as unknown as Response);

      await expect(run()).rejects.toThrow(
        "HTTP 500: Internal Server Error. Unknown error",
      );
    },
  );
});

// ---------------------------------------------------------------------------
// Behaviours that are not just URL shape
// ---------------------------------------------------------------------------

describe("PipelineApiService special-case behaviour", () => {
  it("percent-encodes ids so a slug with a slash cannot escape its path", async () => {
    fetchWithAuth.mockResolvedValue(jsonResponse({}));

    await svc.getRaceRecord("mo/senate 2024");

    expect(lastCall().url).toBe(`${BASE}/api/races/mo%2Fsenate%202024`);
  });

  it("adds ?force=true only when force is requested", async () => {
    fetchWithAuth.mockResolvedValue(jsonResponse({}));

    await svc.removeQueueItem("item-1");
    expect(lastCall().url).toBe(`${BASE}/api/queue/item-1`);

    await svc.removeQueueItem("item-1", true);
    expect(lastCall().url).toBe(`${BASE}/api/queue/item-1?force=true`);
  });

  it("forwards an explicit run limit", async () => {
    fetchWithAuth.mockResolvedValue(jsonResponse({ runs: [] }));

    await svc.listRaceRuns("mo-senate-2024", 5);

    expect(lastCall().url).toContain("?limit=5");
  });

  it("treats a missing draft as already deleted", async () => {
    fetchWithAuth.mockResolvedValue(
      jsonResponse("Draft not found", false, 404, "Not Found"),
    );

    await expect(svc.deleteDraftRace("gone")).resolves.toBeUndefined();
  });

  it("still throws on a 404 that is not a missing draft", async () => {
    fetchWithAuth.mockResolvedValue(
      jsonResponse("race not found", false, 404, "Not Found"),
    );

    await expect(svc.deleteDraftRace("gone")).rejects.toThrow(/HTTP 404/);
  });

  it("posts the race ids for a batch publish", async () => {
    fetchWithAuth.mockResolvedValue(
      jsonResponse({ published: ["a"], errors: [] }),
    );

    await svc.batchPublishRaces(["a", "b"]);

    expect(JSON.parse(lastCall().init.body as string)).toEqual({
      race_ids: ["a", "b"],
    });
  });

  it("posts race ids and options when queueing", async () => {
    fetchWithAuth.mockResolvedValue(jsonResponse({ queued: [] }));

    await svc.addToQueue(["a"], { model_profile: "default" });

    expect(JSON.parse(lastCall().init.body as string)).toEqual({
      race_ids: ["a"],
      options: { model_profile: "default" },
    });
  });

  // The default model deliberately lives server-side; the browser must not
  // invent one. An omitted/blank model has to send {} so the API decides.
  it.each([
    ["omitted", undefined, {}],
    ["blank", "   ", {}],
    ["provided", "  some/model  ", { model: "some/model" }],
  ])(
    "sends %s chamber-forecast model as %j",
    async (_label, model, expected) => {
      fetchWithAuth.mockResolvedValue(jsonResponse({}));

      await svc.generateChamberForecastDraft(model as string | undefined);

      const { url, init, timeout } = lastCall();
      expect(url).toBe(`${BASE}/api/races/chamber_forecasts/generate`);
      expect(timeout).toBe(120_000);
      expect(JSON.parse(init.body as string)).toEqual(expected);
    },
  );

  it("unwraps list envelopes and tolerates a missing key", async () => {
    fetchWithAuth.mockResolvedValue(jsonResponse({}));
    await expect(svc.listRaces()).resolves.toEqual([]);

    fetchWithAuth.mockResolvedValue(jsonResponse({}));
    await expect(svc.loadDraftRaces()).resolves.toEqual([]);

    fetchWithAuth.mockResolvedValue(jsonResponse({}));
    await expect(svc.listRaceVersions("r")).resolves.toEqual([]);

    fetchWithAuth.mockResolvedValue(jsonResponse({}));
    await expect(svc.listRaceRuns("r")).resolves.toEqual([]);
  });

  it("routes publishDraft through the shared publish endpoint", async () => {
    fetchWithAuth.mockResolvedValue(jsonResponse({}));

    await svc.publishDraft("mo-senate-2024");

    expect(lastCall().url).toBe(`${BASE}/api/races/mo-senate-2024/publish`);
  });
});

// ---------------------------------------------------------------------------
// normalizeRun — the only real logic in this file
// ---------------------------------------------------------------------------

describe("normalizeRun", () => {
  async function normalizeVia(raw: Record<string, unknown>) {
    fetchWithAuth.mockResolvedValue(jsonResponse(raw));
    return svc.getRunDetails("run-1");
  }

  it("prefers run_id but falls back to id", async () => {
    expect((await normalizeVia({ run_id: "a", id: "b" })).run_id).toBe("a");
    expect((await normalizeVia({ id: "b" })).run_id).toBe("b");
    expect((await normalizeVia({})).run_id).toBe("");
  });

  it("recovers race_id from the payload when absent at top level", async () => {
    const run = await normalizeVia({ payload: { race_id: "mo-senate-2024" } });

    expect(run.race_id).toBe("mo-senate-2024");
  });

  it("synthesizes a payload from race_id when none is present", async () => {
    const run = await normalizeVia({ race_id: "mo-senate-2024" });

    expect(run.payload).toEqual({ race_id: "mo-senate-2024" });
  });

  it("defaults status to pending", async () => {
    expect((await normalizeVia({})).status).toBe("pending");
  });

  it("keeps an existing steps array untouched", async () => {
    const steps = [{ name: "discovery", label: "D", weight: 1, status: "x" }];

    const run = await normalizeVia({ steps });

    expect(run.steps).toEqual(steps);
  });

  it("marks steps outside enabled_steps as skipped", async () => {
    const run = await normalizeVia({
      options: { enabled_steps: ["discovery"] },
    });

    const discovery = run.steps?.find((s) => s.name === "discovery");
    const issues = run.steps?.find((s) => s.name === "issues");
    expect(discovery?.status).toBe("pending");
    expect(issues?.status).toBe("skipped");
  });

  it("derives completed steps from remaining_steps", async () => {
    const run = await normalizeVia({
      status: "running",
      options: { enabled_steps: ["discovery", "issues"] },
      remaining_steps: ["issues"],
      current_step: "issues",
    });

    expect(run.steps?.find((s) => s.name === "discovery")?.status).toBe(
      "completed",
    );
    expect(run.steps?.find((s) => s.name === "issues")?.status).toBe("running");
  });

  it("marks every enabled step completed when the run is completed", async () => {
    const run = await normalizeVia({
      status: "completed",
      options: { enabled_steps: ["discovery", "issues"] },
    });

    const enabled = run.steps?.filter((s) =>
      ["discovery", "issues"].includes(s.name),
    );
    expect(enabled?.every((s) => s.status === "completed")).toBe(true);
  });

  it("attaches per-step progress only to the current step", async () => {
    const run = await normalizeVia({
      status: "running",
      options: { enabled_steps: ["discovery", "issues"] },
      current_step: "discovery",
      current_step_progress: 42,
    });

    expect(run.steps?.find((s) => s.name === "discovery")?.progress_pct).toBe(
      42,
    );
    expect(
      run.steps?.find((s) => s.name === "issues")?.progress_pct,
    ).toBeUndefined();
  });

  it("falls back to the full step list when enabled_steps is empty", async () => {
    const run = await normalizeVia({ options: { enabled_steps: [] } });

    expect(run.steps?.length).toBeGreaterThan(1);
    expect(run.steps?.every((s) => s.status === "pending")).toBe(true);
  });

  it("drops non-numeric progress and non-string current_step", async () => {
    const run = await normalizeVia({
      progress: "80",
      progress_message: 12,
      current_step: 5,
      current_step_progress: "40",
    });

    expect(run.progress).toBeUndefined();
    expect(run.progress_message).toBeUndefined();
    expect(run.current_step).toBeNull();
    expect(run.current_step_progress).toBeUndefined();
  });
});

describe("loadRunHistory shaping", () => {
  it("numbers runs newest-first and derives updated_at", async () => {
    fetchWithAuth.mockResolvedValue(
      jsonResponse({
        runs: [
          { run_id: "a", started_at: "2026-01-01", completed_at: "2026-01-02" },
          { run_id: "b", started_at: "2026-01-03" },
        ],
      }),
    );

    const history = await svc.loadRunHistory();

    expect(history.map((h) => h.display_id)).toEqual([2, 1]);
    // completed_at wins when present, else started_at.
    expect(history[0].updated_at).toBe("2026-01-02");
    expect(history[1].updated_at).toBe("2026-01-03");
  });

  it("tolerates a response with no runs key", async () => {
    fetchWithAuth.mockResolvedValue(jsonResponse({}));

    await expect(svc.loadRunHistory()).resolves.toEqual([]);
  });
});
