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

  it("renders stated claims with a safe external source link", () => {
    render(ForecastEvidenceLineage, { entries });

    expect(screen.getByTestId("evidence-lineage")).toBeTruthy();
    expect(screen.getByText("Evidence Lineage")).toBeTruthy();
    expect(
      screen.getByText(
        "Prediction markets imply roughly an 87% Democratic win probability in NV-3",
      ),
    ).toBeTruthy();

    const link = screen.getByText(/kalshi\.com/).closest("a");
    expect(link?.getAttribute("href")).toBe(
      "https://kalshi.com/markets/HOUSENV3-26-D",
    );
    expect(link?.getAttribute("target")).toBe("_blank");
    expect(link?.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("omits inferred filler entries entirely", () => {
    const { container } = render(ForecastEvidenceLineage, { entries });

    expect(screen.queryByText("Finance input used by the forecast")).toBeNull();
    expect(container.querySelectorAll("li")).toHaveLength(1);
    expect(screen.queryByText("Inferred")).toBeNull();
    expect(screen.queryByText("Stated in source")).toBeNull();
    expect(screen.queryByText("Campaign Finance")).toBeNull();
    expect(screen.queryByText("Prediction Markets")).toBeNull();
  });

  it("renders a non-http source as plain text rather than a link", () => {
    const { container } = render(ForecastEvidenceLineage, {
      entries: [
        {
          claim: "Internal model note",
          source_url: "javascript:alert(1)",
          kind: "other",
          inferred: false,
        },
      ],
    });

    expect(screen.getByText("Internal model note")).toBeTruthy();
    expect(screen.getByText("javascript:alert(1)")).toBeTruthy();
    expect(container.querySelector("a")).toBeNull();
  });

  it("renders nothing when every entry is inferred", () => {
    const { container } = render(ForecastEvidenceLineage, {
      entries: [entries[1]],
    });

    expect(container.textContent?.trim()).toBe("");
    expect(screen.queryByTestId("evidence-lineage")).toBeNull();
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
