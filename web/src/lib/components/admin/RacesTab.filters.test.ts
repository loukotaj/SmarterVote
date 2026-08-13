import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RaceRecord } from "$lib/types";

/**
 * Covers the table's filtering surface — the global search box, the status
 * dropdown, and the quality-grade badge — which `RacesTab.status-flow.test.ts`
 * does not touch.
 *
 * The service mock is hoisted and created once. The sibling file achieves the
 * same thing with `mockFetchWithAuth ??= vi.fn()` inside `beforeEach`; both work
 * because the component binds the mock at import time and the *object identity*
 * has to survive across tests. Reassigning a fresh `vi.fn()` each time silently
 * detaches the spy the component actually calls.
 */
const { fetchWithAuth } = vi.hoisted(() => ({ fetchWithAuth: vi.fn() }));
vi.mock("$lib/stores/apiStore", () => ({ fetchWithAuth }));

import RacesTab from "./RacesTab.svelte";

function makeRace(overrides: Partial<RaceRecord> = {}): RaceRecord {
  return {
    race_id: "ga-senate-2026",
    title: "Georgia Senate 2026",
    office: "Senate",
    jurisdiction: "Georgia",
    election_date: "2026-11-03",
    status: "empty",
    published_at: undefined,
    draft_updated_at: undefined,
    candidate_count: 2,
    freshness: "recent",
    total_runs: 0,
    requests_24h: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

let rows: RaceRecord[] = [];

async function renderTab() {
  const result = render(RacesTab);
  await result.component.refresh();
  await waitFor(() => expect(fetchWithAuth).toHaveBeenCalled());
  return result;
}

function searchBox(container: HTMLElement) {
  return container.querySelector(
    'input[placeholder="Search visible races..."]',
  ) as HTMLInputElement;
}

function statusSelect(container: HTMLElement) {
  return container.querySelector(
    '[aria-label="Filter by status"]',
  ) as HTMLSelectElement;
}

beforeEach(() => {
  rows = [];
  fetchWithAuth.mockReset();
  fetchWithAuth.mockImplementation(async () => jsonResponse({ races: rows }));
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("RacesTab global search", () => {
  beforeEach(() => {
    rows = [
      // Distinct titles matter: makeRace defaults every row to the same title,
      // so leaving it would make "georgia" match both and the filter look broken.
      makeRace({
        race_id: "ga-senate-2026",
        title: "Georgia Senate 2026",
        jurisdiction: "Georgia",
      }),
      makeRace({
        race_id: "ca-house-12",
        title: "California House 12",
        jurisdiction: "California",
      }),
    ];
  });

  it("shows every race before filtering", async () => {
    const { container } = await renderTab();

    await waitFor(() =>
      expect(container.textContent).toContain("ga-senate-2026"),
    );
    expect(container.textContent).toContain("ca-house-12");
  });

  it("narrows the table to matching races", async () => {
    const { container } = await renderTab();
    await waitFor(() => expect(container.textContent).toContain("ca-house-12"));

    await fireEvent.input(searchBox(container), {
      target: { value: "georgia" },
    });

    await waitFor(() =>
      expect(container.textContent).not.toContain("ca-house-12"),
    );
    expect(container.textContent).toContain("ga-senate-2026");
  });

  // `normalize` lower-cases and trims, so search is forgiving of both.
  it.each([
    ["upper case", "GEORGIA"],
    ["surrounding whitespace", "  georgia  "],
  ])("matches despite %s", async (_label, needle) => {
    const { container } = await renderTab();
    await waitFor(() => expect(container.textContent).toContain("ca-house-12"));

    await fireEvent.input(searchBox(container), { target: { value: needle } });

    await waitFor(() =>
      expect(container.textContent).not.toContain("ca-house-12"),
    );
  });

  it("restores every race when the search is cleared", async () => {
    const { container } = await renderTab();

    await fireEvent.input(searchBox(container), {
      target: { value: "georgia" },
    });
    await waitFor(() =>
      expect(container.textContent).not.toContain("ca-house-12"),
    );

    await fireEvent.input(searchBox(container), { target: { value: "" } });

    await waitFor(() => expect(container.textContent).toContain("ca-house-12"));
  });

  it("shows nothing when the search matches no race", async () => {
    const { container } = await renderTab();

    await fireEvent.input(searchBox(container), {
      target: { value: "zzzz-no-match" },
    });

    await waitFor(() =>
      expect(container.textContent).not.toContain("ga-senate-2026"),
    );
  });
});

describe("RacesTab status filter", () => {
  beforeEach(() => {
    rows = [
      makeRace({ race_id: "published-race", status: "published" }),
      makeRace({ race_id: "draft-race", status: "draft" }),
    ];
  });

  it("filters down to a single status", async () => {
    const { container } = await renderTab();
    await waitFor(() => expect(container.textContent).toContain("draft-race"));

    await fireEvent.change(statusSelect(container), {
      target: { value: "published" },
    });

    await waitFor(() =>
      expect(container.textContent).not.toContain("draft-race"),
    );
    expect(container.textContent).toContain("published-race");
  });

  // "all" clears the column filter rather than filtering on the literal
  // string "all", which would match nothing.
  it("restores every race when set back to all", async () => {
    const { container } = await renderTab();

    await fireEvent.change(statusSelect(container), {
      target: { value: "published" },
    });
    await waitFor(() =>
      expect(container.textContent).not.toContain("draft-race"),
    );

    await fireEvent.change(statusSelect(container), {
      target: { value: "all" },
    });

    await waitFor(() => expect(container.textContent).toContain("draft-race"));
  });

  it("combines the status filter with the search box", async () => {
    rows = [
      makeRace({
        race_id: "ga-published",
        title: "Georgia Senate 2026",
        status: "published",
        jurisdiction: "Georgia",
      }),
      makeRace({
        race_id: "ca-published",
        title: "California House 12",
        status: "published",
        jurisdiction: "California",
      }),
      makeRace({
        race_id: "ga-draft",
        title: "Georgia House 4",
        status: "draft",
        jurisdiction: "Georgia",
      }),
    ];
    const { container } = await renderTab();

    await fireEvent.change(statusSelect(container), {
      target: { value: "published" },
    });
    await fireEvent.input(searchBox(container), {
      target: { value: "georgia" },
    });

    await waitFor(() =>
      expect(container.textContent).toContain("ga-published"),
    );
    expect(container.textContent).not.toContain("ca-published");
    expect(container.textContent).not.toContain("ga-draft");
  });
});

describe("RacesTab quality grade badge", () => {
  it.each([
    ["A", "green"],
    ["B", "yellow"],
    ["C", "orange"],
    ["D", "red"],
    ["F", "red"],
  ])("colours grade %s with the %s ramp", async (grade, hue) => {
    rows = [
      makeRace({
        race_id: "graded",
        quality_grade: grade as RaceRecord["quality_grade"],
      }),
    ];
    const { container } = await renderTab();

    const badge = await waitFor(() => {
      const el = Array.from(container.querySelectorAll("span")).find(
        (s) =>
          s.textContent?.trim() === grade &&
          s.className.includes("rounded-full"),
      );
      expect(el).toBeTruthy();
      return el!;
    });

    expect(badge.className).toContain(hue);
  });

  it("renders no badge for an ungraded race", async () => {
    rows = [makeRace({ race_id: "ungraded", quality_grade: undefined })];
    const { container } = await renderTab();

    await waitFor(() => expect(container.textContent).toContain("ungraded"));
    const badge = Array.from(container.querySelectorAll("span")).find(
      (s) =>
        s.className.includes("rounded-full") &&
        ["A", "B", "C", "D", "F"].includes(s.textContent?.trim() ?? ""),
    );
    expect(badge).toBeUndefined();
  });
});
