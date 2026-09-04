import { cleanup, fireEvent, render } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import IssueTable from "./IssueTable.svelte";
import type { IssueKey, IssueStance, Source } from "$lib/types";

/**
 * IssueTable renders a desktop <table> and a parallel mobile card list. jsdom
 * applies no CSS, so *both* are in the DOM at once and a bare querySelector
 * would match whichever comes first. Every assertion below scopes to one view,
 * and the two are exercised separately because they key their expand/tooltip
 * state differently (`issue` vs `issue + "-mobile"`).
 */
function desktop(container: HTMLElement): HTMLElement {
  return container.querySelector("table") as HTMLElement;
}

function mobile(container: HTMLElement): HTMLElement {
  return container.querySelector('[class~="lg:hidden"]') as HTMLElement;
}

function source(n: number): Source {
  return {
    url: `https://example.test/source-${n}`,
    type: "website",
    title: `Source ${n}`,
    last_accessed: "2026-01-01T00:00:00Z",
  } as Source;
}

function stance(overrides: Partial<IssueStance> = {}): IssueStance {
  return {
    stance: "Supports expanding coverage.",
    confidence: "high",
    sources: [],
    ...overrides,
  } as IssueStance;
}

function renderTable(
  issues: Partial<Record<IssueKey, IssueStance>>,
  props: Record<string, unknown> = {},
) {
  return render(IssueTable, {
    issues,
    raceId: "mo-senate-2024",
    candidateName: "Jane Doe",
    ...props,
  });
}

afterEach(cleanup);

describe("IssueTable empty state", () => {
  it("falls back when there are no issues", () => {
    const { container } = renderTable({});

    expect(container.querySelector("table")).toBeNull();
  });

  it("renders the table once at least one issue exists", () => {
    const { container } = renderTable({
      Healthcare: stance(),
    } as Partial<Record<IssueKey, IssueStance>>);

    expect(container.querySelector("table")).not.toBeNull();
  });
});

describe("IssueTable content", () => {
  it("renders the issue name and stance in both views", () => {
    const { container } = renderTable({
      Healthcare: stance({ stance: "Supports a public option." }),
    } as Partial<Record<IssueKey, IssueStance>>);

    expect(desktop(container).textContent).toContain("Healthcare");
    expect(desktop(container).textContent).toContain(
      "Supports a public option.",
    );
    expect(mobile(container).textContent).toContain(
      "Supports a public option.",
    );
  });

  it("renders every supplied issue", () => {
    const { container } = renderTable({
      Healthcare: stance(),
      Economy: stance({ stance: "Favours targeted tax relief." }),
    } as Partial<Record<IssueKey, IssueStance>>);

    expect(desktop(container).querySelectorAll("tbody tr")).toHaveLength(2);
  });

  it("shows one selected issue at a time in the mobile view", async () => {
    const { container } = renderTable({
      Healthcare: stance({ stance: "Healthcare position." }),
      Economy: stance({ stance: "Economy position." }),
    } as Partial<Record<IssueKey, IssueStance>>);
    const mobileView = mobile(container);
    const select = mobileView.querySelector(
      "#candidate-issue-select",
    ) as HTMLSelectElement;

    expect(mobileView.textContent).toContain("Healthcare position.");
    expect(mobileView.textContent).not.toContain("Economy position.");

    await fireEvent.change(select, { target: { value: "Economy" } });
    expect(mobileView.textContent).toContain("Economy position.");
    expect(mobileView.textContent).not.toContain("Healthcare position.");
  });

  it("says so when an issue has no supporting sources", () => {
    const { container } = renderTable({
      Healthcare: stance({ sources: [] }),
    } as Partial<Record<IssueKey, IssueStance>>);

    expect(desktop(container).textContent).toContain("No supporting sources");
  });
});

describe("IssueTable source expansion", () => {
  const fiveSources = {
    Healthcare: stance({ sources: [1, 2, 3, 4, 5].map(source) }),
  } as Partial<Record<IssueKey, IssueStance>>;

  it("shows only the first three sources initially", () => {
    const { container } = renderTable(fiveSources);

    expect(desktop(container).querySelectorAll("a")).toHaveLength(3);
  });

  it("offers to reveal exactly the remaining sources", () => {
    const { container } = renderTable(fiveSources);
    const toggle = desktop(container).querySelector("button")!;

    expect(toggle.textContent?.trim()).toBe("Show 2 more");
    expect(toggle.getAttribute("aria-label")).toContain(
      "Show 2 more sources for Healthcare",
    );
  });

  it("expands to every source and offers to collapse again", async () => {
    const { container } = renderTable(fiveSources);
    const toggle = desktop(container).querySelector("button")!;

    await fireEvent.click(toggle);

    expect(desktop(container).querySelectorAll("a")).toHaveLength(5);
    const collapse = desktop(container).querySelector("button")!;
    expect(collapse.textContent?.trim()).toBe("Show fewer");
    expect(collapse.getAttribute("aria-label")).toContain(
      "Show fewer sources for Healthcare",
    );

    await fireEvent.click(collapse);
    expect(desktop(container).querySelectorAll("a")).toHaveLength(3);
  });

  it("omits the toggle when there are three or fewer sources", () => {
    const { container } = renderTable({
      Healthcare: stance({ sources: [1, 2, 3].map(source) }),
    } as Partial<Record<IssueKey, IssueStance>>);

    expect(desktop(container).querySelector("button")).toBeNull();
    expect(desktop(container).querySelectorAll("a")).toHaveLength(3);
  });

  // Desktop and mobile track expansion under different keys, so expanding one
  // must not expand the other — that would be a state-collision bug.
  it("keeps desktop and mobile expansion independent", async () => {
    const { container } = renderTable(fiveSources);

    await fireEvent.click(desktop(container).querySelector("button")!);

    expect(desktop(container).querySelectorAll("a")).toHaveLength(5);
    expect(mobile(container).querySelectorAll("a")).toHaveLength(3);
  });

  it("expands the mobile view on its own", async () => {
    const { container } = renderTable(fiveSources);
    const mobileToggle = Array.from(
      mobile(container).querySelectorAll("button"),
    ).find((b) => b.textContent?.includes("Show 2 more"))!;

    await fireEvent.click(mobileToggle);

    expect(mobile(container).querySelectorAll("a")).toHaveLength(5);
  });
});

describe("IssueTable renamed-issue tooltip", () => {
  const renamed = {
    "Reproductive Rights": stance(),
  } as unknown as Partial<Record<IssueKey, IssueStance>>;

  it("offers an explanation only for issues that were renamed", () => {
    const { container } = renderTable(renamed);

    expect(
      desktop(container).querySelector('[aria-label="About this issue name"]'),
    ).not.toBeNull();
  });

  it("shows no explanation button for a current issue name", () => {
    const { container } = renderTable({
      Healthcare: stance(),
    } as Partial<Record<IssueKey, IssueStance>>);

    expect(
      desktop(container).querySelector('[aria-label="About this issue name"]'),
    ).toBeNull();
  });

  it("reveals the rename note on click and dismisses it again", async () => {
    const { container } = renderTable(renamed);
    const info = desktop(container).querySelector(
      '[aria-label="About this issue name"]',
    )!;

    expect(desktop(container).querySelector('[role="tooltip"]')).toBeNull();

    await fireEvent.click(info);
    const tooltip = desktop(container).querySelector('[role="tooltip"]');
    expect(tooltip?.textContent).toContain("has been renamed");

    const dismiss = Array.from(
      desktop(container).querySelectorAll("button"),
    ).find((b) => b.textContent?.trim() === "Dismiss")!;
    await fireEvent.click(dismiss);
    expect(desktop(container).querySelector('[role="tooltip"]')).toBeNull();
  });

  it("toggles the note closed when the info button is clicked twice", async () => {
    const { container } = renderTable(renamed);
    const info = desktop(container).querySelector(
      '[aria-label="About this issue name"]',
    )!;

    await fireEvent.click(info);
    expect(desktop(container).querySelector('[role="tooltip"]')).not.toBeNull();

    await fireEvent.click(info);
    expect(desktop(container).querySelector('[role="tooltip"]')).toBeNull();
  });

  it("keeps the desktop and mobile tooltips independent", async () => {
    const { container } = renderTable(renamed);

    await fireEvent.click(
      desktop(container).querySelector('[aria-label="About this issue name"]')!,
    );

    expect(desktop(container).querySelector('[role="tooltip"]')).not.toBeNull();
    expect(mobile(container).querySelector('[role="tooltip"]')).toBeNull();
  });
});
