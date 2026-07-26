import { cleanup, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import ForecastUnavailable from "./ForecastUnavailable.svelte";

describe("ForecastUnavailable", () => {
  afterEach(cleanup);

  it("renders the empty-state message", () => {
    render(ForecastUnavailable);

    expect(screen.getByText("Forecast Data Unavailable")).toBeTruthy();
    expect(
      screen.getByText(/currently updating our election models/),
    ).toBeTruthy();
  });
});
