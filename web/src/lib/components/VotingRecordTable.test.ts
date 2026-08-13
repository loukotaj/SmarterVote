import { cleanup, render } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import VotingRecordTable from "./VotingRecordTable.svelte";
import type { Source } from "$lib/types";

function source(url: string, title?: string): Source {
  return {
    url,
    type: "website",
    title,
    last_accessed: "2026-01-01T00:00:00Z",
  } as Source;
}

function renderTable(props: Record<string, unknown> = {}) {
  return render(VotingRecordTable, {
    votingSummary: "",
    votingSourceUrl: "",
    votingSources: [],
    raceId: "mo-senate-2024",
    candidateName: "Jane Doe",
    ...props,
  });
}

afterEach(cleanup);

describe("VotingRecordTable empty state", () => {
  it("falls back when there is neither a summary nor a source", () => {
    const { container } = renderTable();

    expect(container.querySelector(".voting-summary")).toBeNull();
    expect(container.querySelector(".source-list")).toBeNull();
  });

  it("renders the summary alone when no sources exist", () => {
    const { container } = renderTable({ votingSummary: "Voted for the bill." });

    expect(container.textContent).toContain("Voted for the bill.");
    expect(container.querySelector(".source-list")).toBeNull();
  });

  it("renders sources alone when there is no summary", () => {
    const { container } = renderTable({
      votingSourceUrl: "https://govtrack.us/x",
    });

    expect(container.querySelector(".source-list")).not.toBeNull();
    expect(container.querySelector(".voting-summary")).toBeNull();
  });
});

describe("VotingRecordTable inline-source handling", () => {
  // Some records arrive with citations glued onto the end of the prose. The
  // summary must render clean while those URLs still surface as real links.
  it("strips a trailing 'Sources: <url>' block from the prose", () => {
    const { container } = renderTable({
      votingSummary:
        "Consistently voted for expansion. Sources: https://govtrack.us/a https://congress.gov/b",
    });

    const summary = container.querySelector(".summary-text")?.textContent ?? "";
    expect(summary).toBe("Consistently voted for expansion.");
    expect(summary).not.toContain("http");
  });

  it("promotes inline URLs to source links", () => {
    const { container } = renderTable({
      votingSummary: "Voted yes. Sources: https://govtrack.us/a",
    });

    const links = Array.from(container.querySelectorAll("a")).map((a) =>
      a.getAttribute("href"),
    );
    expect(links).toContain("https://govtrack.us/a");
  });

  it("trims trailing punctuation off an extracted URL", () => {
    const { container } = renderTable({
      votingSummary: "See Sources: https://govtrack.us/a).",
    });

    const links = Array.from(container.querySelectorAll("a")).map((a) =>
      a.getAttribute("href"),
    );
    expect(links).toContain("https://govtrack.us/a");
  });

  it("leaves prose untouched when there is no source marker", () => {
    const { container } = renderTable({
      votingSummary: "No citations here at all.",
    });

    expect(container.querySelector(".summary-text")?.textContent).toBe(
      "No citations here at all.",
    );
  });
});

describe("VotingRecordTable source links", () => {
  it("labels the primary source url explicitly and lists it first", () => {
    const { container } = renderTable({
      votingSourceUrl: "https://govtrack.us/primary",
      votingSources: [source("https://congress.gov/other", "Congress")],
    });

    const anchors = Array.from(container.querySelectorAll("a"));
    expect(anchors[0].getAttribute("href")).toBe("https://govtrack.us/primary");
    expect(anchors[0].textContent).toContain("View full voting record");
  });

  it("uses a source's own title when present", () => {
    const { container } = renderTable({
      votingSources: [source("https://congress.gov/x", "Congress.gov record")],
    });

    expect(container.textContent).toContain("Congress.gov record");
  });

  it("falls back to a bare hostname when a source has no title", () => {
    const { container } = renderTable({
      votingSources: [source("https://www.congress.gov/x")],
    });

    // www. is stripped so the label reads as a publisher, not a URL.
    expect(container.textContent).toContain("congress.gov");
    expect(container.textContent).not.toContain("www.congress.gov");
  });

  it("deduplicates a url that appears as both primary and listed source", () => {
    const { container } = renderTable({
      votingSourceUrl: "https://govtrack.us/same",
      votingSources: [source("https://govtrack.us/same", "Duplicate")],
    });

    const hrefs = Array.from(container.querySelectorAll("a")).map((a) =>
      a.getAttribute("href"),
    );
    expect(hrefs.filter((h) => h === "https://govtrack.us/same")).toHaveLength(
      1,
    );
    // The first-wins title is the explicit one.
    expect(container.textContent).toContain("View full voting record");
  });

  it.each([
    ["a relative path", "/internal/path"],
    ["a javascript url", "javascript:alert(1)"],
    ["an empty string", ""],
  ])("rejects %s as a source", (_label, url) => {
    const { container } = renderTable({ votingSourceUrl: url });

    expect(container.querySelector(".source-list")).toBeNull();
  });

  it("opens external links safely in a new tab", () => {
    const { container } = renderTable({
      votingSourceUrl: "https://govtrack.us/x",
    });

    const anchor = container.querySelector("a")!;
    expect(anchor.getAttribute("target")).toBe("_blank");
    expect(anchor.getAttribute("rel")).toBe("noopener noreferrer");
  });
});
