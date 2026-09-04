import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import InteractiveRaceCompare from "./InteractiveRaceCompare.svelte";
import type { Candidate, Race } from "$lib/types";

function candidate(name: string, withdrawn = false): Candidate {
  return {
    name,
    party: "Independent",
    incumbent: false,
    summary: `${name} summary`,
    issues: {},
    career_history: [],
    education: [],
    links: [],
    social_media: {},
    summary_sources: [],
    roster_sources: [],
    voting_sources: [],
    donor_sources: [],
    withdrawn,
  } as unknown as Candidate;
}

function race(id: string, candidates: Candidate[] = []): Race {
  return {
    id,
    title: `${id} title`,
    office: "U.S. Senate",
    jurisdiction: "Missouri",
    state: "Missouri",
    election_date: "2024-11-05",
    updated_utc: "2024-06-01T12:00:00Z",
    generator: [],
    candidates: candidates.length
      ? candidates
      : [candidate("Jane Doe"), candidate("John Roe")],
    polling: [],
  } as unknown as Race;
}

function pills(container: HTMLElement) {
  return Array.from(container.querySelectorAll("button[aria-pressed]"));
}

/**
 * Pills are labelled "01 <jurisdiction> · <office>", not by race id, so the
 * selected race must be identified by *position*. Asserting on pill text is a
 * trap: with a shared office every label contains most letters, so an id-based
 * assertion passes whatever is selected.
 */
function selectedIndex(container: HTMLElement): number {
  return pills(container).findIndex(
    (b) => b.getAttribute("aria-pressed") === "true",
  );
}

function arrow(container: HTMLElement, direction: "Previous" | "Next") {
  return container.querySelector(
    `[aria-label="${direction} featured race"]`,
  ) as HTMLButtonElement;
}

beforeEach(() => {
  // The pill strip auto-scrolls the active pill into view; jsdom elements have
  // no scrollTo, and the component guards on that, but stubbing it lets the
  // centring path actually run.
  Element.prototype.scrollTo =
    vi.fn() as unknown as typeof Element.prototype.scrollTo;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("InteractiveRaceCompare visibility", () => {
  it("renders nothing without races", () => {
    const { container } = render(InteractiveRaceCompare, { races: [] });

    expect(container.textContent?.trim()).toBe("");
  });

  // The whole point is a side-by-side comparison; one candidate cannot be
  // compared against anything, so the widget hides rather than half-rendering.
  it("hides when the selected race has fewer than two candidates", () => {
    const { container } = render(InteractiveRaceCompare, {
      races: [race("solo", [candidate("Only One")])],
    });

    expect(container.textContent?.trim()).toBe("");
  });

  it("renders once a race has two comparable candidates", () => {
    const { container } = render(InteractiveRaceCompare, {
      races: [race("a")],
    });

    expect(container.textContent).toContain("Featured comparison");
  });

  it("excludes withdrawn candidates from the comparison", () => {
    const { container } = render(InteractiveRaceCompare, {
      races: [
        race("a", [
          candidate("Jane Doe"),
          candidate("John Roe"),
          candidate("Gone Away", true),
        ]),
      ],
    });

    expect(container.textContent).toContain("Jane Doe");
    expect(container.textContent).not.toContain("Gone Away");
  });

  it("includes every active candidate and links to the full comparison", () => {
    const { container } = render(InteractiveRaceCompare, {
      races: [
        race("a", [
          candidate("Jane Doe"),
          candidate("John Roe"),
          candidate("Alex Smith"),
        ]),
      ],
    });

    expect(container.textContent).toContain("Alex Smith");
    expect(
      container.querySelector(
        'a[href="/races/a/compare/?candidates=jane-doe,john-roe,alex-smith"]',
      ),
    ).not.toBeNull();
  });

  it("hides when withdrawals leave fewer than two candidates", () => {
    const { container } = render(InteractiveRaceCompare, {
      races: [
        race("a", [candidate("Jane Doe"), candidate("Withdrawn One", true)]),
      ],
    });

    expect(container.textContent?.trim()).toBe("");
  });
});

describe("InteractiveRaceCompare race selection", () => {
  const threeRaces = [race("a"), race("b"), race("c")];

  it("starts on the first race", () => {
    const { container } = render(InteractiveRaceCompare, {
      races: threeRaces,
    });

    expect(selectedIndex(container)).toBe(0);
  });

  it("offers one pill per race", () => {
    const { container } = render(InteractiveRaceCompare, {
      races: threeRaces,
    });

    expect(pills(container)).toHaveLength(3);
  });

  it("switches race when a pill is clicked", async () => {
    const { container } = render(InteractiveRaceCompare, {
      races: threeRaces,
    });

    await fireEvent.click(pills(container)[2]);

    await waitFor(() => expect(selectedIndex(container)).toBe(2));
  });

  it("advances with the next arrow", async () => {
    const { container } = render(InteractiveRaceCompare, {
      races: threeRaces,
    });

    await fireEvent.click(arrow(container, "Next"));

    await waitFor(() => expect(selectedIndex(container)).toBe(1));
  });

  it("wraps forward past the last race", async () => {
    const { container } = render(InteractiveRaceCompare, {
      races: threeRaces,
    });

    await fireEvent.click(arrow(container, "Next"));
    await fireEvent.click(arrow(container, "Next"));
    await fireEvent.click(arrow(container, "Next"));

    await waitFor(() => expect(selectedIndex(container)).toBe(0));
  });

  it("wraps backward from the first race to the last", async () => {
    const { container } = render(InteractiveRaceCompare, {
      races: threeRaces,
    });

    await fireEvent.click(arrow(container, "Previous"));

    await waitFor(() => expect(selectedIndex(container)).toBe(2));
  });

  it("marks exactly one pill as pressed at a time", async () => {
    const { container } = render(InteractiveRaceCompare, {
      races: threeRaces,
    });

    await fireEvent.click(pills(container)[1]);

    await waitFor(() => {
      const pressed = pills(container).filter(
        (b) => b.getAttribute("aria-pressed") === "true",
      );
      expect(pressed).toHaveLength(1);
    });
  });

  it("scrolls the active pill into view on selection", async () => {
    const { container } = render(InteractiveRaceCompare, {
      races: threeRaces,
    });
    const scrollTo = Element.prototype.scrollTo as unknown as ReturnType<
      typeof vi.fn
    >;
    scrollTo.mockClear();

    await fireEvent.click(pills(container)[2]);

    await waitFor(() => expect(scrollTo).toHaveBeenCalled());
    expect(scrollTo.mock.calls[0][0]).toMatchObject({ behavior: "smooth" });
  });

  it("still works with a single race", async () => {
    const { container } = render(InteractiveRaceCompare, {
      races: [race("only")],
    });

    // Wrapping with one race lands back on itself rather than going undefined.
    await fireEvent.click(arrow(container, "Next"));

    await waitFor(() => expect(selectedIndex(container)).toBe(0));
  });
});
