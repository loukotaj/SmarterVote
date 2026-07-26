import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import ForecastRaceFilters from "./ForecastRaceFilters.svelte";

describe("ForecastRaceFilters", () => {
  afterEach(cleanup);

  it("calls the change callbacks for rating pills, party pills, sort and clear-state", async () => {
    const onFilterRatingChange = vi.fn();
    const onFilterPartyChange = vi.fn();
    const onSortByChange = vi.fn();
    const onClearState = vi.fn();

    render(ForecastRaceFilters, {
      filterRating: "all",
      filterParty: "all",
      sortBy: "control_relevance",
      selectedState: "Ohio",
      resultCount: 7,
      onFilterRatingChange,
      onFilterPartyChange,
      onSortByChange,
      onClearState,
    });

    expect(screen.getByText("7 races")).toBeTruthy();

    await fireEvent.click(screen.getByText("Toss-ups"));
    expect(onFilterRatingChange).toHaveBeenCalledWith("tossup");

    await fireEvent.click(screen.getByText("Republican"));
    expect(onFilterPartyChange).toHaveBeenCalledWith("Republican");

    await fireEvent.change(screen.getByLabelText("Sort by:"), {
      target: { value: "margin" },
    });
    expect(onSortByChange).toHaveBeenCalledWith("margin");

    await fireEvent.click(screen.getByText(/State: Ohio/));
    expect(onClearState).toHaveBeenCalledTimes(1);
  });

  it("hides the state filter chip when no state is selected", () => {
    render(ForecastRaceFilters, {
      filterRating: "all",
      filterParty: "all",
      sortBy: "control_relevance",
      selectedState: null,
      resultCount: 0,
      onFilterRatingChange: vi.fn(),
      onFilterPartyChange: vi.fn(),
      onSortByChange: vi.fn(),
      onClearState: vi.fn(),
    });

    expect(screen.queryByText(/State:/)).toBeNull();
  });
});
