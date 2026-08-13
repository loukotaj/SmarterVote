import { cleanup, fireEvent, render } from "@testing-library/svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import ValidationGradeBadge from "./ValidationGradeBadge.svelte";
import type { ValidationGrade } from "$lib/types";

function makeGrade(overrides: Partial<ValidationGrade> = {}): ValidationGrade {
  return {
    grade: "A",
    score: 92,
    passed: true,
    summary: "Sources are complete and consistent.",
    ...overrides,
  } as ValidationGrade;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("ValidationGradeBadge rendering", () => {
  it("shows the grade letter and an accessible label", () => {
    const { getByLabelText, container } = render(ValidationGradeBadge, {
      grade: makeGrade({ grade: "B" }),
    });

    expect(getByLabelText("Automated Research Score: B")).toBeTruthy();
    expect(container.textContent).toContain("B");
    expect(container.textContent).toContain("Research score");
  });

  it.each([
    ["A", "green"],
    ["B", "blue"],
    ["C", "yellow"],
    ["D", "orange"],
    ["F", "red"],
  ])("colours grade %s with the %s ramp", (grade, hue) => {
    const { container } = render(ValidationGradeBadge, {
      grade: makeGrade({ grade: grade as ValidationGrade["grade"] }),
    });

    expect(container.querySelector(".grade-badge")?.className).toContain(hue);
  });

  it("falls back to a neutral style for an unrecognised grade", () => {
    const { container } = render(ValidationGradeBadge, {
      grade: makeGrade({ grade: "Z" as ValidationGrade["grade"] }),
    });

    const className = container.querySelector(".grade-badge")?.className ?? "";
    expect(className).toContain("bg-surface-alt");
  });

  it("keeps the popover closed until asked", () => {
    const { container } = render(ValidationGradeBadge, { grade: makeGrade() });

    expect(container.querySelector(".popover")).toBeNull();
  });
});

describe("ValidationGradeBadge popover", () => {
  it("opens on click and shows the score, summary, and caveat", async () => {
    const { container, getByLabelText } = render(ValidationGradeBadge, {
      grade: makeGrade({ score: 74, summary: "Two issues lack sources." }),
    });

    await fireEvent.click(getByLabelText(/Automated Research Score/));

    const popover = container.querySelector(".popover");
    expect(popover).not.toBeNull();
    expect(popover?.textContent).toContain("Score: 74/100");
    expect(popover?.textContent).toContain("Two issues lack sources.");
    // The caveat is the product's honesty disclaimer — it must not be quietly
    // dropped. Collapse whitespace first: the source wraps mid-sentence, so
    // textContent carries the newline and indentation.
    const caveat = (popover?.textContent ?? "").replace(/\s+/g, " ");
    expect(caveat).toContain("not a guarantee that every claim is correct");
  });

  it("toggles closed on a second click", async () => {
    const { container, getByLabelText } = render(ValidationGradeBadge, {
      grade: makeGrade(),
    });
    const badge = getByLabelText(/Automated Research Score/);

    await fireEvent.click(badge);
    expect(container.querySelector(".popover")).not.toBeNull();

    await fireEvent.click(badge);
    expect(container.querySelector(".popover")).toBeNull();
  });

  it("closes on Escape", async () => {
    const { container, getByLabelText } = render(ValidationGradeBadge, {
      grade: makeGrade(),
    });
    const badge = getByLabelText(/Automated Research Score/);

    await fireEvent.click(badge);
    expect(container.querySelector(".popover")).not.toBeNull();

    await fireEvent.keyDown(badge, { key: "Escape" });
    expect(container.querySelector(".popover")).toBeNull();
  });

  it("ignores other keys", async () => {
    const { container, getByLabelText } = render(ValidationGradeBadge, {
      grade: makeGrade(),
    });
    const badge = getByLabelText(/Automated Research Score/);

    await fireEvent.click(badge);
    await fireEvent.keyDown(badge, { key: "a" });

    expect(container.querySelector(".popover")).not.toBeNull();
  });

  it("closes when the backdrop is clicked", async () => {
    const { container, getByLabelText } = render(ValidationGradeBadge, {
      grade: makeGrade(),
    });

    await fireEvent.click(getByLabelText(/Automated Research Score/));
    const backdrop = container.querySelector(".popover-backdrop");
    expect(backdrop).not.toBeNull();

    await fireEvent.click(backdrop!);
    expect(container.querySelector(".popover")).toBeNull();
  });

  it("repeats the grade inside the popover header", async () => {
    const { container, getByLabelText } = render(ValidationGradeBadge, {
      grade: makeGrade({ grade: "C" }),
    });

    await fireEvent.click(getByLabelText(/Automated Research Score/));

    expect(container.querySelector(".popover-grade")?.textContent).toContain(
      "C",
    );
  });
});

describe("ValidationGradeBadge review link", () => {
  it("scrolls to the review section and closes the popover", async () => {
    const target = document.createElement("div");
    target.id = "ai-review";
    const scrollIntoView = vi.fn();
    target.scrollIntoView = scrollIntoView;
    document.body.appendChild(target);

    const { container, getByLabelText, getByText } = render(
      ValidationGradeBadge,
      { grade: makeGrade() },
    );

    await fireEvent.click(getByLabelText(/Automated Research Score/));
    await fireEvent.click(getByText("View review details"));

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth" });
    expect(container.querySelector(".popover")).toBeNull();
  });

  // The badge renders on pages that have no review section; a missing anchor
  // must close the popover rather than throw.
  it("still closes cleanly when there is no review section on the page", async () => {
    const { container, getByLabelText, getByText } = render(
      ValidationGradeBadge,
      { grade: makeGrade() },
    );

    await fireEvent.click(getByLabelText(/Automated Research Score/));
    await fireEvent.click(getByText("View review details"));

    expect(container.querySelector(".popover")).toBeNull();
  });
});
