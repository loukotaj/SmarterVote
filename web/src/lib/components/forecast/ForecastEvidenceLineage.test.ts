import { cleanup, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import type { ForecastEvidence } from "$lib/types";
import ForecastEvidenceLineage from "./ForecastEvidenceLineage.svelte";

const entries: ForecastEvidence[] = [
  {
    claim:
      "Prediction markets imply roughly an 87% Democratic win probability in NV-3",
    source_url: "https://kalshi.com/markets/HOUSENV3-26-D",
    kind: "market",
    inferred: false,
  },
  {
    claim: "Finance input used by the forecast",
    source_url: "https://www.fec.gov/data/candidate/H6NV03204/",
    kind: "finance",
    inferred: true,
  },
];

describe("ForecastEvidenceLineage", () => {
  afterEach(cleanup);

  it("renders each claim grouped by kind with a safe external source link", () => {
    render(ForecastEvidenceLineage, { entries });

    expect(screen.getByTestId("evidence-lineage")).toBeTruthy();
    expect(screen.getByText("Evidence Lineage")).toBeTruthy();
    expect(screen.getByText("2 claims - 1 inferred")).toBeTruthy();
    expect(screen.getByText("Prediction Markets")).toBeTruthy();
    expect(screen.getByText("Campaign Finance")).toBeTruthy();
    expect(
      screen.getByText(
        "Prediction markets imply roughly an 87% Democratic win probability in NV-3",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Finance input used by the forecast")).toBeTruthy();

    const link = screen.getByText(/kalshi\.com/).closest("a");
    expect(link?.getAttribute("href")).toBe(
      "https://kalshi.com/markets/HOUSENV3-26-D",
    );
    expect(link?.getAttribute("target")).toBe("_blank");
    expect(link?.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("visually distinguishes inferred entries from directly stated ones", () => {
    render(ForecastEvidenceLineage, { entries });

    const stated = screen.getByText("Stated in source");
    const inferred = screen.getByText("Inferred");

    // Distinct badge labels and distinct color treatments.
    expect(stated.className).toContain("emerald");
    expect(inferred.className).toContain("amber");
    expect(stated.className).not.toBe(inferred.className);

    // The row itself is also differentiated, not just the badge.
    const statedRow = stated.closest("li");
    const inferredRow = inferred.closest("li");
    expect(statedRow?.className).toContain("border-l-emerald-500");
    expect(inferredRow?.className).toContain("border-dashed");

    // The distinction is explained in plain language when inferred rows exist.
    expect(screen.getByText(/does not state the claim outright/)).toBeTruthy();
  });

  it("omits the inferred footnote when every claim is directly stated", () => {
    render(ForecastEvidenceLineage, {
      entries: [{ ...entries[0] }],
    });

    expect(screen.getByText("1 claim")).toBeTruthy();
    expect(screen.getByText("Stated in source")).toBeTruthy();
    expect(screen.queryByText("Inferred")).toBeNull();
    expect(screen.queryByText(/does not state the claim outright/)).toBeNull();
  });

  it("renders nothing when lineage is undefined, null or empty", () => {
    const { container: undefinedContainer } = render(ForecastEvidenceLineage, {
      entries: undefined,
    });
    expect(undefinedContainer.textContent?.trim()).toBe("");
    cleanup();

    const { container: nullContainer } = render(ForecastEvidenceLineage, {
      entries: null,
    });
    expect(nullContainer.textContent?.trim()).toBe("");
    cleanup();

    const { container: emptyContainer } = render(ForecastEvidenceLineage, {
      entries: [],
    });
    expect(emptyContainer.textContent?.trim()).toBe("");
    expect(screen.queryByTestId("evidence-lineage")).toBeNull();
  });
});
