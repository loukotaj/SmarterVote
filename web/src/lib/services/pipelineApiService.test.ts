import { describe, expect, it, vi, beforeEach } from "vitest";

const { fetchWithAuth } = vi.hoisted(() => ({
  fetchWithAuth: vi.fn(),
}));

vi.mock("$lib/stores/apiStore", () => ({
  fetchWithAuth,
}));

import { PipelineApiService } from "./pipelineApiService";

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

describe("PipelineApiService production admin API contract", () => {
  beforeEach(() => {
    fetchWithAuth.mockReset();
  });

  it("loads draft race summaries from the canonical draft endpoint", async () => {
    fetchWithAuth.mockResolvedValueOnce(
      jsonResponse({
        races: [
          {
            id: "az-senate-2026",
            title: "Arizona Senate 2026",
            office: "U.S. Senate",
            jurisdiction: "Arizona",
            election_date: "2026-11-03",
            updated_utc: "2026-05-01T00:00:00Z",
            candidates: [{ name: "Alice Example", party: "D" }],
          },
        ],
      }),
    );

    const api = new PipelineApiService("https://api.example.test");
    const drafts = await api.loadDraftRaces();

    expect(fetchWithAuth).toHaveBeenCalledWith(
      "https://api.example.test/api/races/drafts",
      {},
      expect.any(Number),
    );
    expect(drafts).toHaveLength(1);
    expect(drafts[0].id).toBe("az-senate-2026");
    expect(drafts[0].candidates[0].name).toBe("Alice Example");
  });

  it("queues races through the production /api/races/queue endpoint", async () => {
    fetchWithAuth.mockResolvedValueOnce(
      jsonResponse({
        added: [{ race_id: "az-senate-2026", status: "queued" }],
        errors: [],
      }),
    );

    const api = new PipelineApiService("https://api.example.test");
    await api.queueRaces(["az-senate-2026"], {
      cheap_mode: false,
      enabled_steps: ["review", "iteration"],
      gemini_model: "gemini-test",
      grok_model: "grok-test",
    });

    expect(fetchWithAuth).toHaveBeenCalledWith(
      "https://api.example.test/api/races/queue",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          race_ids: ["az-senate-2026"],
          options: {
            cheap_mode: false,
            enabled_steps: ["review", "iteration"],
            gemini_model: "gemini-test",
            grok_model: "grok-test",
          },
        }),
      },
    );
  });

  it("publishes drafts through the production race publish endpoint", async () => {
    fetchWithAuth.mockResolvedValueOnce(jsonResponse({ message: "published" }));

    const api = new PipelineApiService("https://api.example.test");
    await api.publishDraft("az-senate-2026");

    expect(fetchWithAuth).toHaveBeenCalledWith(
      "https://api.example.test/api/races/az-senate-2026/publish",
      { method: "POST" },
      expect.any(Number),
    );
  });

  it("reconciles active race state when loading the admin race list", async () => {
    fetchWithAuth.mockResolvedValueOnce(jsonResponse({ races: [] }));

    const api = new PipelineApiService("https://api.example.test");
    await api.listRaces();

    expect(fetchWithAuth).toHaveBeenCalledWith(
      "https://api.example.test/api/races?reconcile_active=true",
      {},
      expect.any(Number),
    );
  });

  it("parses admin chat action responses", async () => {
    fetchWithAuth.mockResolvedValueOnce(
      jsonResponse({
        reply: "This race should be refreshed.",
        action: {
          type: "queue_run",
          race_ids: ["az-senate-2026"],
          options: { cheap_mode: true },
          description: "Refresh Arizona Senate",
        },
        race_records: [],
        question: null,
        thinking_steps: ["Prepared run for 1 race(s)"],
      }),
    );

    const api = new PipelineApiService("https://api.example.test");
    const result = await api.adminChat([
      { role: "user", content: "Refresh Arizona" },
    ]);

    expect(result.action?.type).toBe("queue_run");
    expect(result.action?.race_ids).toEqual(["az-senate-2026"]);
    expect(result.thinking_steps).toEqual(["Prepared run for 1 race(s)"]);
  });

  it("loads, saves, generates, and publishes chamber forecasts", async () => {
    fetchWithAuth
      .mockResolvedValueOnce(
        jsonResponse({
          schema_version: "chamber_forecasts.v2",
          house: "House narrative",
          senate: "Senate narrative",
          governors: "Governors narrative",
          chambers: {},
          updated_at: "2026-06-01T00:00:00Z",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          message: "generated",
          updated_at: "2026-06-03T00:00:00Z",
          forecast: {
            house: "Generated house",
            senate: "Generated senate",
            governors: "Generated governors",
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          message: "published",
          updated_at: "2026-06-04T00:00:00Z",
        }),
      );

    const api = new PipelineApiService("https://api.example.test");

    await api.getChamberForecastDraft();
    await api.generateChamberForecastDraft("test-model");
    await api.publishChamberForecastDraft();

    expect(fetchWithAuth).toHaveBeenNthCalledWith(
      1,
      "https://api.example.test/api/races/chamber_forecasts/draft",
      {},
      expect.any(Number),
    );
    expect(fetchWithAuth).toHaveBeenNthCalledWith(
      2,
      "https://api.example.test/api/races/chamber_forecasts/generate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ model: "test-model" }),
      }),
      120000,
    );
    expect(fetchWithAuth).toHaveBeenNthCalledWith(
      3,
      "https://api.example.test/api/races/chamber_forecasts/publish",
      { method: "POST" },
      expect.any(Number),
    );
  });

  it("normalizes Firestore run stage fields into steps", async () => {
    fetchWithAuth.mockResolvedValueOnce(
      jsonResponse({
        run_id: "run-1",
        race_id: "az-senate-2026",
        status: "running",
        progress: 20,
        progress_message: "Issues checkpoint - Alice - Healthcare",
        current_step: "issues",
        current_step_progress: 37,
        remaining_steps: ["issues", "finance"],
        started_at: "2026-05-01T00:00:00Z",
        options: { enabled_steps: ["discovery", "issues", "finance"] },
      }),
    );

    const api = new PipelineApiService("https://api.example.test");
    const run = await api.getRunDetails("run-1");

    expect(fetchWithAuth).toHaveBeenCalledWith(
      "https://api.example.test/runs/run-1",
      {},
      expect.any(Number),
    );
    expect(run.current_step).toBe("issues");
    expect(run.progress).toBe(20);
    expect(run.progress_message).toBe("Issues checkpoint - Alice - Healthcare");
    expect(run.current_step_progress).toBe(37);
    expect(run.steps?.find((s) => s.name === "discovery")?.status).toBe(
      "completed",
    );
    expect(run.steps?.find((s) => s.name === "issues")?.status).toBe("running");
    expect(run.steps?.find((s) => s.name === "issues")?.progress_pct).toBe(37);
    expect(run.steps?.find((s) => s.name === "images")?.status).toBe("skipped");
  });
});
