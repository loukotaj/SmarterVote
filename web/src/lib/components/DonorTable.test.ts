import { cleanup, render } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import DonorTable from "./DonorTable.svelte";

describe("DonorTable", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders structured finance sources separately from the donor summary", () => {
    const { getByText, container } = render(DonorTable, {
      donorSummary: "Alice raised $1.2M, mostly from individual donors.",
      donorSourceUrl: "https://www.fec.gov/data/candidate/H0ALICE/",
      donorSources: [
        {
          url: "https://www.opensecrets.org/candidates/Alice",
          type: "finance",
          title: "OpenSecrets profile",
          last_accessed: "2026-05-16T00:00:00Z",
          is_fresh: false,
        },
      ],
    });

    expect(
      getByText("Alice raised $1.2M, mostly from individual donors."),
    ).toBeTruthy();
    expect(getByText("OpenSecrets profile")).toBeTruthy();
    expect(getByText("Full campaign finance data")).toBeTruthy();
    expect(container.querySelectorAll("a")).toHaveLength(2);
  });

  it("hides legacy inline Sources text and still exposes those links", () => {
    const { getByText, queryByText, container } = render(DonorTable, {
      donorSummary:
        "Alice raised $1.2M, mostly from individual donors. Sources: https://www.fec.gov/data/candidate/H0ALICE/ ; https://example.com/report.",
    });

    expect(
      getByText("Alice raised $1.2M, mostly from individual donors."),
    ).toBeTruthy();
    expect(queryByText(/Sources:/)).toBeNull();
    expect(getByText("fec.gov")).toBeTruthy();
    expect(getByText("example.com")).toBeTruthy();
    expect(container.querySelectorAll("a")).toHaveLength(2);
  });
});
