import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RaceSummary } from "$lib/types";
import SiteHeader from "./SiteHeader.svelte";

const { goto, getRaceSummaries, pageControl } = vi.hoisted(() => ({
  goto: vi.fn(),
  getRaceSummaries: vi.fn(),
  // Filled in by the $app/stores factory below so tests can drive the route.
  pageControl: { setUrl: (_: string) => {} },
}));

vi.mock("$app/environment", () => ({ browser: true }));
vi.mock("$app/navigation", () => ({ goto }));
vi.mock("$app/stores", async () => {
  const { writable } = await import("svelte/store");
  const store = writable({ url: new URL("https://smarter.vote/elections/") });
  pageControl.setUrl = (href: string) => store.set({ url: new URL(href) });
  return { page: store };
});
vi.mock("$lib/api", () => ({ getRaceSummaries }));

/**
 * On "/" the header treats the URL's `?q=` as the source of truth for the
 * search box: a reactive block copies it into `query` whenever it differs from
 * the last value the header itself wrote. In the real app `goto` updates
 * `$page.url`, closing that loop. Under test `goto` is a spy, so the URL never
 * changes and typing on "/" is immediately reset to "".
 *
 * Search behaviour is therefore exercised from a non-home route, and the
 * homepage URL-sync path gets its own describe block that drives the store by
 * hand. Getting this wrong makes every search assertion fail for a reason that
 * has nothing to do with search.
 */
const NON_HOME_ROUTE = "https://smarter.vote/elections/";

// jsdom has no ResizeObserver, and onMount observes the header for height.
class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function race(overrides: Partial<RaceSummary> = {}): RaceSummary {
  return {
    id: "mo-senate-2024",
    title: "2024 Missouri U.S. Senate Election",
    office: "U.S. Senate",
    state: "Missouri",
    jurisdiction: "Missouri",
    election_date: "2024-11-05",
    updated_utc: "2024-06-01T12:00:00Z",
    candidates: [{ name: "Jane Doe", party: "Democratic", incumbent: false }],
    ...overrides,
  } as RaceSummary;
}

function renderHeader(props: Record<string, unknown> = {}) {
  return render(SiteHeader, {
    races: [race()],
    isAuthenticated: false,
    darkMode: false,
    onToggleDark: vi.fn(),
    ...props,
  });
}

function searchBox(container: HTMLElement): HTMLInputElement {
  return container.querySelector("#site-search") as HTMLInputElement;
}

async function type(input: HTMLInputElement, value: string) {
  await fireEvent.input(input, { target: { value } });
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  pageControl.setUrl(NON_HOME_ROUTE);
  goto.mockReset();
  getRaceSummaries.mockReset();
  getRaceSummaries.mockResolvedValue([race()]);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("SiteHeader search matching", () => {
  it("shows no results panel until something is typed", () => {
    const { container } = renderHeader();

    expect(container.querySelector("#site-search-results")).toBeNull();
  });

  it("matches a race by title", async () => {
    const { container } = renderHeader();

    await type(searchBox(container), "Missouri");

    await waitFor(() =>
      expect(container.textContent).toContain("Missouri U.S. Senate"),
    );
  });

  it("matches a candidate by name", async () => {
    const { container } = renderHeader();

    await type(searchBox(container), "Jane");

    await waitFor(() => expect(container.textContent).toContain("Jane Doe"));
  });

  it("caps race results at five", async () => {
    const races = Array.from({ length: 9 }, (_, i) =>
      race({
        id: `race-${i}`,
        title: `Senate Race ${i}`,
        candidates: [],
      }),
    );
    const { container } = renderHeader({ races });

    await type(searchBox(container), "Senate");

    await waitFor(() => {
      const links = Array.from(container.querySelectorAll("li, button")).filter(
        (el) => el.textContent?.includes("Senate Race"),
      );
      expect(links.length).toBeLessThanOrEqual(5);
    });
  });

  it("finds nothing for a query that matches no race or candidate", async () => {
    const { container } = renderHeader();

    await type(searchBox(container), "zzzzz-no-match");

    await waitFor(() => {
      expect(container.textContent).not.toContain("Jane Doe");
    });
  });
});

describe("SiteHeader navigation", () => {
  it("navigates to a race when its result is chosen", async () => {
    const { container } = renderHeader();
    const input = searchBox(container);

    await type(input, "Missouri");
    await fireEvent.keyDown(input, { key: "ArrowDown" });
    await fireEvent.keyDown(input, { key: "Enter" });

    expect(goto).toHaveBeenCalledWith("/races/mo-senate-2024/");
  });

  it("slugifies a candidate name into the profile url", async () => {
    const { container } = renderHeader({
      races: [
        race({
          title: "No Match Here",
          office: "",
          state: "",
          jurisdiction: "",
          candidates: [
            { name: "Jane Q. Doe", party: "Democratic", incumbent: false },
          ],
        }),
      ],
    });
    const input = searchBox(container);

    await type(input, "Jane");
    await fireEvent.keyDown(input, { key: "ArrowDown" });
    await fireEvent.keyDown(input, { key: "Enter" });

    expect(goto).toHaveBeenCalledWith("/races/mo-senate-2024/jane-q-doe/");
  });

  it("falls back to the elections page when nothing is highlighted", async () => {
    const { container } = renderHeader();
    const input = searchBox(container);

    await type(input, "Missouri");
    await fireEvent.keyDown(input, { key: "Enter" });

    expect(goto).toHaveBeenCalledWith("/elections/?q=Missouri");
  });

  it("url-encodes the fallback query", async () => {
    const { container } = renderHeader();
    const input = searchBox(container);

    await type(input, "a & b");
    await fireEvent.keyDown(input, { key: "Enter" });

    expect(goto).toHaveBeenCalledWith("/elections/?q=a%20%26%20b");
  });

  it("does not navigate on Enter with an empty query", async () => {
    const { container } = renderHeader();

    await fireEvent.keyDown(searchBox(container), { key: "Enter" });

    expect(goto).not.toHaveBeenCalled();
  });
});

describe("SiteHeader keyboard navigation", () => {
  it("wraps around the end of the result list", async () => {
    const { container } = renderHeader();
    const input = searchBox(container);
    await type(input, "Missouri");

    // One race + one candidate = two results; three downs wraps to the first.
    await fireEvent.keyDown(input, { key: "ArrowDown" });
    await fireEvent.keyDown(input, { key: "ArrowDown" });
    await fireEvent.keyDown(input, { key: "ArrowDown" });
    await fireEvent.keyDown(input, { key: "Enter" });

    expect(goto).toHaveBeenCalledWith("/races/mo-senate-2024/");
  });

  // NOTE: with nothing highlighted (activeIndex === -1), ArrowUp computes
  // (-1 - 1 + total) % total, which lands on the FIRST result, not the last.
  // Conventional combobox behaviour would wrap to the last item. Pinned as-is
  // rather than "fixed" here — it is a deliberate-looking formula and changing
  // it is a UX decision, not a test concern.
  it("selects the first result when ArrowUp is pressed with nothing highlighted", async () => {
    const { container } = renderHeader();
    const input = searchBox(container);
    await type(input, "Missouri");

    await fireEvent.keyDown(input, { key: "ArrowUp" });
    await fireEvent.keyDown(input, { key: "Enter" });

    expect(goto).toHaveBeenCalledWith("/races/mo-senate-2024/");
  });

  it("steps backwards through results once one is highlighted", async () => {
    const { container } = renderHeader();
    const input = searchBox(container);
    await type(input, "Missouri");

    // Down to the race (0), down to the candidate (1), up back to the race (0).
    await fireEvent.keyDown(input, { key: "ArrowDown" });
    await fireEvent.keyDown(input, { key: "ArrowDown" });
    await fireEvent.keyDown(input, { key: "ArrowUp" });
    await fireEvent.keyDown(input, { key: "Enter" });

    expect(goto).toHaveBeenCalledWith("/races/mo-senate-2024/");
  });

  it("closes the panel on Escape", async () => {
    const { container } = renderHeader();
    const input = searchBox(container);

    await type(input, "Missouri");
    await waitFor(() =>
      expect(container.querySelector("#site-search-results")).not.toBeNull(),
    );

    await fireEvent.keyDown(input, { key: "Escape" });

    await waitFor(() =>
      expect(container.querySelector("#site-search-results")).toBeNull(),
    );
  });

  it("ignores arrow keys when there are no matches", async () => {
    const { container } = renderHeader();
    const input = searchBox(container);

    await type(input, "zzzzz-no-match");
    await fireEvent.keyDown(input, { key: "ArrowDown" });
    await fireEvent.keyDown(input, { key: "Enter" });

    // Falls through to the elections fallback rather than selecting nothing.
    expect(goto).toHaveBeenCalledWith("/elections/?q=zzzzz-no-match");
  });
});

describe("SiteHeader lazy race loading", () => {
  it("does not fetch summaries when races were supplied", async () => {
    const { container } = renderHeader({ races: [race()] });

    await type(searchBox(container), "Missouri");

    expect(getRaceSummaries).not.toHaveBeenCalled();
  });

  it("fetches summaries on first search when none were supplied", async () => {
    const { container } = renderHeader({ races: [] });

    await type(searchBox(container), "Missouri");

    await waitFor(() => expect(getRaceSummaries).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(container.textContent).toContain("Missouri U.S. Senate"),
    );
  });

  it("fetches only once across repeated searches", async () => {
    const { container } = renderHeader({ races: [] });
    const input = searchBox(container);

    await type(input, "Mis");
    await waitFor(() => expect(getRaceSummaries).toHaveBeenCalledTimes(1));
    await type(input, "Missouri");
    await type(input, "Missouri S");

    expect(getRaceSummaries).toHaveBeenCalledTimes(1);
  });

  // A failed summaries fetch must leave the header usable rather than throwing.
  it("survives a failed summaries fetch", async () => {
    getRaceSummaries.mockRejectedValue(new Error("offline"));
    const { container } = renderHeader({ races: [] });

    await type(searchBox(container), "Missouri");

    await waitFor(() => expect(getRaceSummaries).toHaveBeenCalled());
    expect(searchBox(container)).not.toBeNull();
  });
});

describe("SiteHeader homepage query sync", () => {
  const HOME = "https://smarter.vote/";

  it("seeds the search box from ?q= on the homepage", async () => {
    pageControl.setUrl(`${HOME}?q=Missouri`);
    const { container } = renderHeader();

    await waitFor(() => expect(searchBox(container).value).toBe("Missouri"));
  });

  it("loads summaries when arriving with a query already in the url", async () => {
    pageControl.setUrl(`${HOME}?q=Missouri`);
    renderHeader({ races: [] });

    await waitFor(() => expect(getRaceSummaries).toHaveBeenCalled());
  });

  it("does not seed the box from ?q= away from the homepage", async () => {
    pageControl.setUrl("https://smarter.vote/elections/?q=Missouri");
    const { container } = renderHeader();

    expect(searchBox(container).value).toBe("");
  });

  it("pushes the typed query into the homepage url without adding history", async () => {
    vi.useFakeTimers();
    pageControl.setUrl(HOME);
    const { container } = renderHeader();

    await fireEvent.input(searchBox(container), {
      target: { value: "Missouri" },
    });
    await vi.advanceTimersByTimeAsync(200);

    expect(goto).toHaveBeenCalledWith(
      "/?q=Missouri",
      expect.objectContaining({
        replaceState: true,
        keepFocus: true,
        noScroll: true,
      }),
    );
  });

  it("offers a clear button only while there is a query", async () => {
    pageControl.setUrl(HOME);
    const { container } = renderHeader();
    expect(container.querySelector('[aria-label="Clear search"]')).toBeNull();
    cleanup();

    pageControl.setUrl(`${HOME}?q=Missouri`);
    const seeded = renderHeader();

    await waitFor(() =>
      expect(
        seeded.container.querySelector('[aria-label="Clear search"]'),
      ).not.toBeNull(),
    );
  });

  it("drops the q parameter when the search is cleared", async () => {
    // Close the navigation feedback loop: the header only stays cleared once
    // $page.url loses its `q`, which real SvelteKit navigation does for it.
    goto.mockImplementation((href: string) => {
      pageControl.setUrl(new URL(href, HOME).href);
    });
    pageControl.setUrl(`${HOME}?q=Missouri`);
    const { container } = renderHeader();

    const clear = await waitFor(() => {
      const el = container.querySelector('[aria-label="Clear search"]');
      expect(el).not.toBeNull();
      return el as HTMLElement;
    });

    await fireEvent.click(clear);

    await waitFor(() =>
      expect(goto).toHaveBeenCalledWith("/?", expect.anything()),
    );
    await waitFor(() => expect(searchBox(container).value).toBe(""));
  });
});

describe("SiteHeader global shortcuts", () => {
  it("opens search when '/' is pressed outside a text field", async () => {
    const { container } = renderHeader();

    await fireEvent.keyDown(window, { key: "/" });

    await waitFor(() =>
      expect(document.activeElement).toBe(searchBox(container)),
    );
  });

  it("ignores '/' while typing in the search box", async () => {
    const { container } = renderHeader();
    const input = searchBox(container);
    input.focus();

    await fireEvent.keyDown(window, { key: "/" });

    // Still focused, but the shortcut must not have hijacked the keystroke.
    expect(document.activeElement).toBe(input);
  });

  it("closes overlays on Escape", async () => {
    const { container } = renderHeader();

    await fireEvent.keyDown(window, { key: "/" });
    await fireEvent.keyDown(window, { key: "Escape" });

    expect(container.querySelector("#site-search-results")).toBeNull();
  });

  it("closes the results panel on an outside click", async () => {
    const { container } = renderHeader();

    await type(searchBox(container), "Missouri");
    await waitFor(() =>
      expect(container.querySelector("#site-search-results")).not.toBeNull(),
    );

    await fireEvent.click(document.body);

    await waitFor(() =>
      expect(container.querySelector("#site-search-results")).toBeNull(),
    );
  });
});
