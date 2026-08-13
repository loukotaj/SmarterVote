import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ForecastsTab from "./ForecastsTab.svelte";
import type { PipelineApiService } from "$lib/services/pipelineApiService";

/**
 * ForecastsTab receives its service as a prop, so no module mocking is needed —
 * a plain stub object is enough. Every destructive action is behind a
 * `confirm()`, so that global is stubbed per-test and its return value is part
 * of the behaviour under test.
 */
function makeService(overrides: Record<string, unknown> = {}) {
  return {
    getPublishedChamberForecasts: vi.fn().mockResolvedValue(forecasts("pub")),
    getChamberForecastDraft: vi.fn().mockResolvedValue(forecasts("draft")),
    generateChamberForecastDraft: vi
      .fn()
      .mockResolvedValue({ forecast: forecasts("generated") }),
    publishChamberForecastDraft: vi.fn().mockResolvedValue({ message: "ok" }),
    ...overrides,
  } as unknown as PipelineApiService;
}

// The panels render `chambers[chamber].narrative`, not the top-level
// house/senate/governors strings — those are the v1 shape. Tag the chamber
// narrative so assertions can tell published from draft from generated.
function forecasts(tag: string) {
  const chamber = (name: string) => ({
    narrative: `${tag} ${name} narrative`,
    control_party: "Democratic",
    control_probability: 0.6,
    projected_seats: { Democratic: 0, Republican: 0 },
    expected_seats: { Democratic: 0, Republican: 0 },
    bottom_line: `${tag} ${name} bottom line`,
    why_party_favored: "",
    tossup_count: 0,
    competitive_race_count: 0,
  });
  return {
    schema_version: "chamber_forecasts.v2",
    updated_at: "2026-01-15T00:00:00Z",
    house: `${tag} house summary`,
    senate: `${tag} senate summary`,
    governors: `${tag} governors summary`,
    chambers: {
      house: chamber("house"),
      senate: chamber("senate"),
      governors: chamber("governors"),
    },
  };
}

function renderTab(apiService = makeService()) {
  const result = render(ForecastsTab, { apiService });
  return { ...result, apiService };
}

async function renderLoaded(apiService = makeService()) {
  const result = renderTab(apiService);
  await waitFor(() =>
    expect(apiService.getChamberForecastDraft).toHaveBeenCalled(),
  );
  return result;
}

function button(container: HTMLElement, label: string) {
  return Array.from(container.querySelectorAll("button")).find((b) =>
    b.textContent?.toLowerCase().includes(label.toLowerCase()),
  );
}

function allowConfirm(value: boolean) {
  vi.stubGlobal(
    "confirm",
    vi.fn(() => value),
  );
}

beforeEach(() => {
  allowConfirm(true);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ForecastsTab loading", () => {
  it("loads published and draft forecasts on mount", async () => {
    const { apiService, container } = await renderLoaded();

    expect(apiService.getPublishedChamberForecasts).toHaveBeenCalledTimes(1);
    expect(apiService.getChamberForecastDraft).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(container.textContent).toContain("pub house narrative"),
    );
    expect(container.textContent).toContain("draft house narrative");
  });

  // allSettled: a missing draft is the normal state before anyone generates one.
  it("still shows the published forecast when no draft exists", async () => {
    const service = makeService({
      getChamberForecastDraft: vi.fn().mockRejectedValue(new Error("404")),
    });
    const { container } = await renderLoaded(service);

    await waitFor(() =>
      expect(container.textContent).toContain("pub house narrative"),
    );
    expect(container.textContent).not.toContain("draft house narrative");
  });

  it("still shows a draft when nothing is published yet", async () => {
    const service = makeService({
      getPublishedChamberForecasts: vi.fn().mockRejectedValue(new Error("404")),
    });
    const { container } = await renderLoaded(service);

    await waitFor(() =>
      expect(container.textContent).toContain("draft house narrative"),
    );
    expect(container.textContent).not.toContain("pub house narrative");
  });

  it("survives both sources failing", async () => {
    const service = makeService({
      getPublishedChamberForecasts: vi.fn().mockRejectedValue(new Error("x")),
      getChamberForecastDraft: vi.fn().mockRejectedValue(new Error("y")),
    });
    const { container } = await renderLoaded(service);

    await waitFor(() => expect(container.textContent).not.toContain("Loading"));
    expect(container.textContent).not.toContain("narrative");
  });

  it("reloads on demand", async () => {
    const { apiService, container } = await renderLoaded();

    const refresh = container.querySelector(
      '[aria-label="Refresh forecasts"]',
    ) as HTMLElement;
    await fireEvent.click(refresh);

    await waitFor(() =>
      expect(apiService.getChamberForecastDraft).toHaveBeenCalledTimes(2),
    );
  });
});

describe("ForecastsTab draft generation", () => {
  it("asks before spending on a generation", async () => {
    allowConfirm(false);
    const { apiService, container } = await renderLoaded();

    await fireEvent.click(button(container, "Generate")!);

    expect(apiService.generateChamberForecastDraft).not.toHaveBeenCalled();
  });

  // The model box is intentionally blank so the server's default applies —
  // keeping a model id in the browser is what let this control drift stale.
  it("sends an empty model so the server default wins", async () => {
    const { apiService, container } = await renderLoaded();

    await fireEvent.click(button(container, "Generate")!);

    await waitFor(() =>
      expect(apiService.generateChamberForecastDraft).toHaveBeenCalledWith(""),
    );
  });

  it("forwards an explicitly chosen model", async () => {
    const { apiService, container } = await renderLoaded();
    const input = container.querySelector("#model-select") as HTMLInputElement;

    await fireEvent.input(input, { target: { value: "some/model" } });
    await fireEvent.click(button(container, "Generate")!);

    await waitFor(() =>
      expect(apiService.generateChamberForecastDraft).toHaveBeenCalledWith(
        "some/model",
      ),
    );
  });

  it("swaps in the newly generated draft and says so", async () => {
    const { container } = await renderLoaded();

    await fireEvent.click(button(container, "Generate")!);

    await waitFor(() =>
      expect(container.textContent).toContain("generated house narrative"),
    );
    expect(container.textContent).toContain(
      "Generated a new chamber forecast draft.",
    );
  });

  it("surfaces a generation failure without wiping the existing draft", async () => {
    const service = makeService({
      generateChamberForecastDraft: vi
        .fn()
        .mockRejectedValue(new Error("model unavailable")),
    });
    const { container } = await renderLoaded(service);

    await fireEvent.click(button(container, "Generate")!);

    await waitFor(() =>
      expect(container.textContent).toContain(
        "Generate failed: model unavailable",
      ),
    );
    expect(container.textContent).toContain("draft house narrative");
  });

  it("describes a non-Error rejection rather than dropping it", async () => {
    const service = makeService({
      generateChamberForecastDraft: vi.fn().mockRejectedValue("plain string"),
    });
    const { container } = await renderLoaded(service);

    await fireEvent.click(button(container, "Generate")!);

    await waitFor(() =>
      expect(container.textContent).toContain("Generate failed: plain string"),
    );
  });
});

describe("ForecastsTab publishing", () => {
  it("asks before publishing", async () => {
    allowConfirm(false);
    const { apiService, container } = await renderLoaded();

    await fireEvent.click(button(container, "Publish")!);

    expect(apiService.publishChamberForecastDraft).not.toHaveBeenCalled();
  });

  it("publishes and then refetches so the published pane is current", async () => {
    const { apiService, container } = await renderLoaded();

    await fireEvent.click(button(container, "Publish")!);

    await waitFor(() =>
      expect(apiService.publishChamberForecastDraft).toHaveBeenCalledTimes(1),
    );
    // A reload follows the publish, so the loaders run a second time.
    await waitFor(() =>
      expect(apiService.getPublishedChamberForecasts).toHaveBeenCalledTimes(2),
    );
    expect(container.textContent).toContain(
      "Chamber forecast draft published.",
    );
  });

  it("surfaces a publish failure", async () => {
    const service = makeService({
      publishChamberForecastDraft: vi
        .fn()
        .mockRejectedValue(new Error("no draft to publish")),
    });
    const { container } = await renderLoaded(service);

    await fireEvent.click(button(container, "Publish")!);

    await waitFor(() =>
      expect(container.textContent).toContain(
        "Publish failed: no draft to publish",
      ),
    );
  });

  it("does not reload when the publish itself failed", async () => {
    const service = makeService({
      publishChamberForecastDraft: vi.fn().mockRejectedValue(new Error("nope")),
    });
    const { apiService, container } = await renderLoaded(service);

    await fireEvent.click(button(container, "Publish")!);

    await waitFor(() =>
      expect(container.textContent).toContain("Publish failed"),
    );
    expect(apiService.getPublishedChamberForecasts).toHaveBeenCalledTimes(1);
  });
});
