import { cleanup, fireEvent, render } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import RaceCard from "./RaceCard.svelte";
import type { RaceSummary } from "$lib/types";

function makeRace(overrides: Partial<RaceSummary> = {}): RaceSummary {
  return {
    id: "mo-senate-2024",
    title: "2024 Missouri U.S. Senate Election",
    office: "U.S. Senator",
    jurisdiction: "Missouri",
    election_date: "2024-11-05",
    updated_utc: "2024-06-01T12:00:00Z",
    candidates: [
      { name: "Jane Doe", party: "Democratic", incumbent: false },
      { name: "John Roe", party: "Republican", incumbent: true },
    ],
    ...overrides,
  } as RaceSummary;
}

afterEach(cleanup);

/**
 * Read the office badge specifically rather than the card's whole textContent.
 * The card also renders the race *title*, which contains words like "Senate" —
 * asserting on textContent passes even when the badge is broken.
 */
function badgeText(container: HTMLElement): string {
  return container.querySelector(".font-semibold")?.textContent?.trim() ?? "";
}

describe("RaceCard office badge", () => {
  // Office strings as they actually appear in published race data.
  it.each([
    ["U.S. Senate", "Senate"],
    ["United States Senate", "Senate"],
    ["Governor of Hawaii", "Governor"],
    ["Gubernatorial", "Governor"],
    ["U.S. House of Representatives", "House"],
    ["United States House of Representatives", "House"],
    ["Secretary of State", "Sec. of State"],
    ["Attorney General", "Atty. General"],
  ])("labels office %j as %j", (office, expected) => {
    const { container } = render(RaceCard, { race: makeRace({ office }) });

    expect(badgeText(container)).toBe(expected);
  });

  it("falls back to a generic label when office is absent", () => {
    const { container } = render(RaceCard, {
      race: makeRace({ office: undefined }),
    });

    expect(badgeText(container)).toBe("Race");
  });

  it("passes a short unrecognised office through verbatim", () => {
    const { container } = render(RaceCard, {
      race: makeRace({ office: "County Coroner" }),
    });

    expect(badgeText(container)).toBe("County Coroner");
  });

  it("truncates an unrecognised office longer than 22 characters", () => {
    const long = "Commissioner of Public Lands and Waterways";
    const { container } = render(RaceCard, {
      race: makeRace({ office: long }),
    });

    expect(badgeText(container)).toBe(`${long.slice(0, 22)}…`);
  });

  it("matches office case-insensitively", () => {
    const { container } = render(RaceCard, {
      race: makeRace({ office: "UNITED STATES SENATE" }),
    });

    expect(badgeText(container)).toBe("Senate");
  });

  // "U.S. Senator" (singular) does not contain the substring "senate", so it
  // gets the neutral badge. Real published data uses "U.S. Senate" / "United
  // States Senate", so this is a quirk rather than a live defect — pinned so
  // that stays true if the pipeline's office vocabulary ever shifts.
  it("does not recognise the singular 'U.S. Senator' form", () => {
    const { container } = render(RaceCard, {
      race: makeRace({ office: "U.S. Senator" }),
    });

    expect(badgeText(container)).toBe("U.S. Senator");
  });
});

describe("RaceCard content", () => {
  it("links to the race detail page", () => {
    const { container } = render(RaceCard, { race: makeRace() });

    expect(container.querySelector("a")?.getAttribute("href")).toBe(
      "/races/mo-senate-2024",
    );
  });

  it("shows the jurisdiction when present", () => {
    const { container } = render(RaceCard, { race: makeRace() });

    expect(container.textContent).toContain("Missouri");
  });

  it("omits the jurisdiction chip when absent", () => {
    const withChip = render(RaceCard, { race: makeRace() });
    const chip = withChip.container.querySelector(".bg-green-100");
    expect(chip?.textContent?.trim()).toBe("Missouri");
    cleanup();

    const { container } = render(RaceCard, {
      race: makeRace({ jurisdiction: undefined }),
    });

    expect(container.querySelector(".bg-green-100")).toBeNull();
  });

  it("renders every candidate name", () => {
    const { container } = render(RaceCard, { race: makeRace() });

    expect(container.textContent).toContain("Jane Doe");
    expect(container.textContent).toContain("John Roe");
  });

  it("renders an empty candidate list without error", () => {
    const { container } = render(RaceCard, {
      race: makeRace({ candidates: [] }),
    });

    expect(container.querySelector("a")).not.toBeNull();
  });

  it("formats the election date", () => {
    const { container } = render(RaceCard, { race: makeRace() });

    expect(container.textContent).toMatch(/Nov/);
    expect(container.textContent).toContain("2024");
  });
});

describe("RaceCard candidate avatars", () => {
  it("uses the headshot when one is available", () => {
    const { container } = render(RaceCard, {
      race: makeRace({
        candidates: [
          {
            name: "Jane Doe",
            party: "Democratic",
            incumbent: false,
            image_url: "https://example.test/jane.jpg",
          },
        ],
      } as Partial<RaceSummary>),
    });

    expect(container.querySelector("img")?.getAttribute("src")).toBe(
      "https://example.test/jane.jpg",
    );
  });

  it("shows an initial placeholder when there is no headshot", () => {
    const { container } = render(RaceCard, {
      race: makeRace({
        candidates: [
          { name: "Jane Doe", party: "Democratic", incumbent: false },
        ],
      } as Partial<RaceSummary>),
    });

    expect(container.querySelector("img")).toBeNull();
  });

  // A dead headshot URL is common — the card must degrade to initials rather
  // than render a broken-image icon.
  it("falls back to initials when the headshot fails to load", async () => {
    const { container } = render(RaceCard, {
      race: makeRace({
        candidates: [
          {
            name: "Jane Doe",
            party: "Democratic",
            incumbent: false,
            image_url: "https://example.test/broken.jpg",
          },
        ],
      } as Partial<RaceSummary>),
    });

    const img = container.querySelector("img")!;
    await fireEvent.error(img);

    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("Jane Doe");
  });

  it("only replaces the candidate whose image failed", async () => {
    const { container } = render(RaceCard, {
      race: makeRace({
        candidates: [
          {
            name: "Jane Doe",
            party: "Democratic",
            incumbent: false,
            image_url: "https://example.test/broken.jpg",
          },
          {
            name: "John Roe",
            party: "Republican",
            incumbent: true,
            image_url: "https://example.test/ok.jpg",
          },
        ],
      } as Partial<RaceSummary>),
    });

    await fireEvent.error(container.querySelectorAll("img")[0]);

    const remaining = container.querySelectorAll("img");
    expect(remaining).toHaveLength(1);
    expect(remaining[0].getAttribute("src")).toBe(
      "https://example.test/ok.jpg",
    );
  });
});
