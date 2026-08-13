import { cleanup, render } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import FeaturedElections from "./FeaturedElections.svelte";
import type { RaceSummary } from "$lib/types";

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

function manyRaces(n: number) {
  return Array.from({ length: n }, (_, i) =>
    race({ id: `race-${i}`, title: `Race ${i}` }),
  );
}

function links(container: HTMLElement) {
  return Array.from(container.querySelectorAll('a[href^="/races/"]'));
}

afterEach(cleanup);

describe("FeaturedElections empty state", () => {
  // The whole section is hidden rather than rendering an empty shell — the
  // homepage should not show a "Featured races" heading with nothing under it.
  it("renders nothing at all without races", () => {
    const { container } = render(FeaturedElections, { races: [] });

    expect(container.querySelector("section")).toBeNull();
    expect(container.textContent?.trim()).toBe("");
  });

  it("renders the section as soon as there is one race", () => {
    const { container } = render(FeaturedElections, { races: [race()] });

    expect(container.querySelector("section")).not.toBeNull();
    expect(container.textContent).toContain("Featured races");
  });
});

describe("FeaturedElections lead race", () => {
  it("promotes the first race into the lead slot", () => {
    const { container } = render(FeaturedElections, {
      races: [race({ id: "lead", title: "Lead Race" })],
    });

    const lead = links(container)[0];
    expect(lead.getAttribute("href")).toBe("/races/lead/");
    expect(lead.textContent).toContain("Lead Race");
    expect(lead.textContent).toContain("Featured");
  });

  it.each([
    ["title", { title: "A Title" }, "A Title"],
    ["office when the title is absent", { title: undefined }, "U.S. Senate"],
    [
      "a generic label when both are absent",
      { title: undefined, office: undefined },
      "Election research",
    ],
  ])("labels the lead race by %s", (_label, overrides, expected) => {
    const { container } = render(FeaturedElections, {
      races: [race(overrides as Partial<RaceSummary>)],
    });

    expect(links(container)[0].textContent).toContain(expected);
  });

  it("falls back to United States when the lead race has no jurisdiction", () => {
    const { container } = render(FeaturedElections, {
      races: [race({ jurisdiction: undefined })],
    });

    expect(links(container)[0].textContent).toContain("United States");
  });

  it("shows at most four candidate chips on the lead race", () => {
    const { container } = render(FeaturedElections, {
      races: [
        race({
          candidates: Array.from({ length: 7 }, (_, i) => ({
            name: `Candidate ${i}`,
            party: "Independent",
            incumbent: false,
          })),
        }),
      ],
    });

    const lead = links(container)[0];
    const shown = [0, 1, 2, 3].filter((i) =>
      lead.textContent?.includes(`Candidate ${i}`),
    );
    expect(shown).toHaveLength(4);
    expect(lead.textContent).not.toContain("Candidate 4");
  });
});

describe("FeaturedElections secondary list", () => {
  it("lists the next four races after the lead", () => {
    const { container } = render(FeaturedElections, { races: manyRaces(10) });

    // 1 lead + 4 secondary = 5 race links (index links use a different href).
    // Assert on hrefs: unlike the lead slot, the secondary list renders a
    // *derived* title via raceDisplayTitle rather than race.title.
    const hrefs = links(container).map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual([
      "/races/race-0/",
      "/races/race-1/",
      "/races/race-2/",
      "/races/race-3/",
      "/races/race-4/",
    ]);
    expect(hrefs).not.toContain("/races/race-5/");
  });

  it("renders only the lead when a single race is supplied", () => {
    const { container } = render(FeaturedElections, { races: [race()] });

    expect(links(container)).toHaveLength(1);
  });

  it("reports how many candidates each secondary race has", () => {
    const { container } = render(FeaturedElections, {
      races: [
        race({ id: "lead" }),
        race({
          id: "second",
          candidates: [
            { name: "A", party: "D", incumbent: false },
            { name: "B", party: "R", incumbent: false },
          ],
        }),
      ],
    });

    expect(container.textContent).toContain("2 candidates researched");
  });

  it("falls back to National for a secondary race with no jurisdiction", () => {
    const { container } = render(FeaturedElections, {
      races: [race({ id: "lead" }), race({ id: "b", jurisdiction: undefined })],
    });

    expect(container.textContent).toContain("National");
  });
});

describe("FeaturedElections index links", () => {
  // Two links to the index exist by design — one for wide screens in the
  // header, one for narrow screens at the foot of the section.
  it("offers a route to the full index at both breakpoints", () => {
    const { container } = render(FeaturedElections, { races: [race()] });

    const indexLinks = Array.from(
      container.querySelectorAll('a[href="/elections/"]'),
    );
    expect(indexLinks).toHaveLength(2);
    expect(indexLinks.every((a) => a.textContent?.includes("full index"))).toBe(
      true,
    );
  });
});
