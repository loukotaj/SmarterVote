import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import ForecastOutlookAnalysis from "./ForecastOutlookAnalysis.svelte";

describe("ForecastOutlookAnalysis", () => {
  afterEach(cleanup);

  it("summarizes structured analysis and reveals the details on request", async () => {
    render(ForecastOutlookAnalysis, {
      activeTab: "senate",
      chamberSummary: {
        narrative: "",
        control_party: "Republican",
        control_probability: 0.7,
        outcome_probabilities: {},
        projected_seats: {},
        expected_seats: {},
        threshold: 51,
        total_seats: 100,
        tossup_count: 3,
        competitive_races: [],
        method: "test",
        bottom_line: "Republicans hold a narrow edge.",
        why_party_favored: "Favorable map in red-leaning states.",
        opposing_party_path: "Democrats need to sweep the tossups.",
        key_uncertainty: "Late-breaking undecided voters.",
      },
      chamberNarrative: "",
    });

    expect(screen.getByText("Republicans hold a narrow edge.")).toBeTruthy();
    const details = screen
      .getByText("Why Republicans Are Favored")
      .closest("[id]");
    expect(details?.classList).toContain("hidden");

    await fireEvent.click(
      screen.getByRole("button", { name: "Show full analysis" }),
    );

    expect(screen.getByText("Why Republicans Are Favored")).toBeTruthy();
    expect(details?.classList).not.toContain("hidden");
    expect(screen.getByText("Democratic Path to Control")).toBeTruthy();
    expect(screen.getByText("Key Risk & Uncertainty")).toBeTruthy();
  });

  it("falls back to the chamber narrative when no structured outlook fields are set", () => {
    render(ForecastOutlookAnalysis, {
      activeTab: "house",
      chamberSummary: undefined,
      chamberNarrative: "The House is a coin flip this cycle.",
    });

    expect(
      screen.getByText("The House is a coin flip this cycle."),
    ).toBeTruthy();
    expect(screen.queryByText("The Bottom Line")).toBeNull();
  });
});
