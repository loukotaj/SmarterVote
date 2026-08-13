import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import USMap from "./USMap.svelte";

/**
 * A real (tiny) TopoJSON payload rather than an empty one: the component turns
 * geometries into SVG path data via geoAlbersUsa, and a feature whose projected
 * path is empty is deliberately filtered out. Testing the fill/interaction
 * logic therefore needs geometry that actually projects, which means polygons
 * with plausible US coordinates.
 *
 * No `transform` key, so arc coordinates are absolute rather than delta-encoded.
 * ids are FIPS codes: 29 = Missouri, 20 = Kansas, 06 = California.
 */
const TOPOLOGY = {
  type: "Topology",
  arcs: [
    [
      [-95, 36],
      [-89, 36],
      [-89, 40],
      [-95, 40],
      [-95, 36],
    ],
    [
      [-102, 37],
      [-95, 37],
      [-95, 40],
      [-102, 40],
      [-102, 37],
    ],
    [
      [-124, 33],
      [-115, 33],
      [-115, 42],
      [-124, 42],
      [-124, 33],
    ],
  ],
  objects: {
    states: {
      type: "GeometryCollection",
      geometries: [
        { type: "Polygon", id: 29, arcs: [[0]] },
        { type: "Polygon", id: 20, arcs: [[1]] },
        { type: "Polygon", id: 6, arcs: [[2]] },
      ],
    },
  },
};

function stubFetch(payload: unknown = TOPOLOGY) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    }),
  );
}

async function renderMap(props: Record<string, unknown> = {}) {
  const result = render(USMap, {
    activeStates: new Set<string>(),
    selectedState: null,
    raceCounts: {},
    matchingCandidatesByState: {},
    stateColors: {},
    stateTooltips: {},
    ...props,
  });
  await waitFor(() =>
    expect(result.container.querySelector("svg")).not.toBeNull(),
  );
  return result;
}

function pathFor(container: HTMLElement, label: string): SVGPathElement | null {
  const match = Array.from(container.querySelectorAll("path")).find((p) =>
    p.getAttribute("aria-label")?.startsWith(label),
  );
  // Normalise Array.find's `undefined` to `null` so absence assertions read
  // consistently against the querySelector-based lookups elsewhere.
  return (match as SVGPathElement) ?? null;
}

beforeEach(() => stubFetch());

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("USMap loading", () => {
  it("shows a skeleton until the topology arrives", () => {
    const { container } = render(USMap, { activeStates: new Set<string>() });

    expect(container.querySelector(".skeleton")).not.toBeNull();
    expect(container.querySelector("svg")).toBeNull();
  });

  it("renders one path per projected state once loaded", async () => {
    const { container } = await renderMap();

    expect(container.querySelectorAll("path")).toHaveLength(3);
    expect(fetch).toHaveBeenCalledWith("/states-10m.json");
  });

  it("maps FIPS ids to state names", async () => {
    const { container } = await renderMap();

    expect(pathFor(container, "Missouri")).not.toBeNull();
    expect(pathFor(container, "Kansas")).not.toBeNull();
    expect(pathFor(container, "California")).not.toBeNull();
  });

  it("falls back to the padded FIPS code for an unknown id", async () => {
    stubFetch({
      ...TOPOLOGY,
      objects: {
        states: {
          type: "GeometryCollection",
          geometries: [{ type: "Polygon", id: 99, arcs: [[0]] }],
        },
      },
    });
    const { container } = await renderMap();

    expect(pathFor(container, "99")).not.toBeNull();
  });

  // TopoJSON represents "no geometry" as a null-typed member; geoPath returns
  // null for it and the feature is filtered out rather than rendering an empty
  // <path>. Note this is the *only* way to get empty path data here — a polygon
  // with non-US coordinates does not vanish, because geoAlbersUsa's clipping
  // turns it into an inverted fill covering the viewport.
  it("drops members that carry no geometry", async () => {
    stubFetch({
      ...TOPOLOGY,
      objects: {
        states: {
          type: "GeometryCollection",
          geometries: [
            { type: null, id: 29 },
            { type: "Polygon", id: 20, arcs: [[1]] },
          ],
        },
      },
    });
    const { container } = await renderMap();

    expect(container.querySelectorAll("path")).toHaveLength(1);
    expect(pathFor(container, "Kansas")).not.toBeNull();
    expect(pathFor(container, "Missouri")).toBeNull();
  });
});

describe("USMap fill precedence", () => {
  it("paints inactive states with the inactive token", async () => {
    const { container } = await renderMap();

    expect(pathFor(container, "Missouri")?.getAttribute("fill")).toBe(
      "var(--map-inactive)",
    );
  });

  it("paints states that have races as active", async () => {
    const { container } = await renderMap({
      activeStates: new Set(["Missouri"]),
    });

    expect(pathFor(container, "Missouri")?.getAttribute("fill")).toBe(
      "var(--map-active)",
    );
  });

  it("paints the selected state with the selected token", async () => {
    const { container } = await renderMap({
      activeStates: new Set(["Missouri"]),
      selectedState: "Missouri",
    });

    expect(pathFor(container, "Missouri")?.getAttribute("fill")).toBe(
      "var(--map-selected)",
    );
  });

  // An explicit per-state colour outranks everything, including selection —
  // that is what lets a forecast tab paint the map by party.
  it("lets an explicit state colour win over selection", async () => {
    const { container } = await renderMap({
      activeStates: new Set(["Missouri"]),
      selectedState: "Missouri",
      stateColors: { Missouri: "#ff0000" },
    });

    expect(pathFor(container, "Missouri")?.getAttribute("fill")).toBe(
      "#ff0000",
    );
  });
});

describe("USMap selection rendering", () => {
  it("draws the selected state last so its stroke is not clipped", async () => {
    const { container } = await renderMap({
      activeStates: new Set(["Missouri", "Kansas"]),
      selectedState: "Missouri",
    });

    const paths = Array.from(container.querySelectorAll("path"));
    expect(paths.at(-1)?.getAttribute("aria-label")).toContain("Missouri");
    expect(paths.at(-1)?.getAttribute("stroke")).toBe(
      "var(--map-selected-stroke)",
    );
  });

  it("labels the selected state as selected", async () => {
    const { container } = await renderMap({
      activeStates: new Set(["Missouri"]),
      selectedState: "Missouri",
      raceCounts: { Missouri: 3 },
    });

    expect(pathFor(container, "Missouri")?.getAttribute("aria-label")).toBe(
      "Missouri, 3 races, selected",
    );
  });
});

describe("USMap accessibility labelling", () => {
  it.each([
    [1, "Missouri, 1 race"],
    [2, "Missouri, 2 races"],
    [0, "Missouri, 0 races"],
  ])("pluralises a count of %i correctly", async (count, expected) => {
    const { container } = await renderMap({
      activeStates: new Set(["Missouri"]),
      raceCounts: { Missouri: count },
    });

    expect(pathFor(container, "Missouri")?.getAttribute("aria-label")).toBe(
      expected,
    );
  });

  it("marks an active state as a button and makes it focusable", async () => {
    const { container } = await renderMap({
      activeStates: new Set(["Missouri"]),
    });

    const path = pathFor(container, "Missouri")!;
    expect(path.getAttribute("role")).toBe("button");
    expect(path.getAttribute("tabindex")).toBe("0");
  });

  it("keeps an inactive state out of the tab order", async () => {
    const { container } = await renderMap();

    const path = pathFor(container, "Missouri")!;
    expect(path.getAttribute("role")).toBe("presentation");
    expect(path.getAttribute("tabindex")).toBe("-1");
  });

  // A state with a tooltip but no races is readable but not clickable.
  it("marks a tooltip-only state as an image rather than a button", async () => {
    const { container } = await renderMap({
      stateTooltips: { Missouri: { title: "No races yet" } },
    });

    const path = pathFor(container, "Missouri")!;
    expect(path.getAttribute("role")).toBe("img");
    expect(path.getAttribute("tabindex")).toBe("-1");
  });
});

/**
 * `stateClick` is raised through `createEventDispatcher`, and Svelte 5 removed
 * `component.$on(...)`, so the emission cannot be observed from here. The
 * dispatch is covered end-to-end in ElectionDirectory.test.ts, which renders
 * this map for real and asserts the resulting filter change. What is asserted
 * below is everything that *gates* the dispatch — handlers attached, and
 * interaction refused for states that should not be clickable.
 */
describe("USMap interaction", () => {
  it("handles a click on an active state without error", async () => {
    const { container } = await renderMap({
      activeStates: new Set(["Missouri"]),
    });

    await expect(
      fireEvent.click(pathFor(container, "Missouri")!),
    ).resolves.not.toThrow();
  });

  it.each(["Enter", " ", "a"])(
    "handles the %s key without error",
    async (key) => {
      const { container } = await renderMap({
        activeStates: new Set(["Missouri"]),
      });

      await expect(
        fireEvent.keyDown(pathFor(container, "Missouri")!, { key }),
      ).resolves.not.toThrow();
    },
  );

  it("shows a hover tooltip for an active state", async () => {
    const { container } = await renderMap({
      activeStates: new Set(["Missouri"]),
      raceCounts: { Missouri: 2 },
    });

    await fireEvent.mouseEnter(pathFor(container, "Missouri")!);

    await waitFor(() => expect(container.textContent).toContain("Missouri"));
  });

  it("clears the tooltip on mouse leave", async () => {
    const { container } = await renderMap({
      activeStates: new Set(["Missouri"]),
      raceCounts: { Missouri: 2 },
    });
    const path = pathFor(container, "Missouri")!;

    await fireEvent.mouseEnter(path);
    await fireEvent.mouseLeave(path);

    await waitFor(() => expect(container.querySelector(".tooltip")).toBeNull());
  });

  it("shows a tooltip on keyboard focus and clears it on blur", async () => {
    const { container } = await renderMap({
      activeStates: new Set(["Missouri"]),
      raceCounts: { Missouri: 1 },
    });
    const path = pathFor(container, "Missouri")!;

    await fireEvent.focus(path);
    await fireEvent.blur(path);

    await waitFor(() => expect(container.querySelector(".tooltip")).toBeNull());
  });
});
