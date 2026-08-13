import { cleanup, fireEvent, render } from "@testing-library/svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Candidate, IssueStance, Race, RaceForecast } from "$lib/types";
import CandidateComparison from "./CandidateComparison.svelte";

/**
 * Complements `CandidateComparison.test.ts` (stance previews, sticky labels,
 * review banner) with the derived logic: the candidate picker, compact-mode
 * issue selection, avatar fallback, and forecast probability matching.
 */
function candidate(
  name: string,
  overrides: Partial<Candidate> = {},
): Candidate {
  return {
    name,
    party: "Independent",
    incumbent: false,
    summary: `${name} summary`,
    summary_sources: [],
    issues: {},
    career_history: [],
    education: [],
    links: [],
    social_media: {},
    roster_sources: [],
    voting_sources: [],
    donor_sources: [],
    withdrawn: false,
    ...overrides,
  } as Candidate;
}

function race(overrides: Partial<Race> = {}): Race {
  return {
    schema_version: "0.3",
    id: "test-race-2026",
    title: "Test Race",
    office: "U.S. Senate",
    election_date: "2026-11-03",
    contest_stage: "unknown",
    updated_utc: "2026-07-01T00:00:00Z",
    generator: [],
    polling: [],
    reviews: [],
    candidates: [],
    ...overrides,
  } as Race;
}

function sourced(stance: string): IssueStance {
  return {
    stance,
    confidence: "high",
    sources: [
      {
        url: "https://example.test/a",
        type: "website",
        title: "Source",
        last_accessed: "2026-01-01T00:00:00Z",
        is_fresh: true,
      },
    ],
  };
}

function checkboxes(container: HTMLElement) {
  return Array.from(
    container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]'),
  );
}

afterEach(cleanup);

describe("CandidateComparison candidate picker", () => {
  it("is absent unless a toggle handler is supplied", () => {
    const jane = candidate("Jane Doe");
    const { container } = render(CandidateComparison, {
      race: race({ candidates: [jane] }),
      candidates: [jane],
    });

    expect(checkboxes(container)).toHaveLength(0);
  });

  it("offers a checkbox per candidate when a handler is supplied", () => {
    const jane = candidate("Jane Doe");
    const john = candidate("John Roe");
    const { container } = render(CandidateComparison, {
      race: race({ candidates: [jane, john] }),
      candidates: [jane],
      onToggle: vi.fn(),
    });

    expect(checkboxes(container)).toHaveLength(2);
  });

  it("checks only the candidates currently being compared", () => {
    const jane = candidate("Jane Doe");
    const john = candidate("John Roe");
    const { container } = render(CandidateComparison, {
      race: race({ candidates: [jane, john] }),
      candidates: [jane],
      onToggle: vi.fn(),
    });

    const [first, second] = checkboxes(container);
    expect(first.checked).toBe(true);
    expect(second.checked).toBe(false);
  });

  // A withdrawn candidate stays in race.candidates so their data is preserved,
  // but offering them as a comparison target would be misleading.
  it("omits withdrawn candidates from the picker", () => {
    const jane = candidate("Jane Doe");
    const gone = candidate("Gone Away", { withdrawn: true });
    const { container } = render(CandidateComparison, {
      race: race({ candidates: [jane, gone] }),
      candidates: [jane],
      onToggle: vi.fn(),
    });

    expect(checkboxes(container)).toHaveLength(1);
    expect(container.textContent).not.toContain("Gone Away");
  });

  it("reports the candidate name when a box is toggled", async () => {
    const onToggle = vi.fn();
    const jane = candidate("Jane Doe");
    const john = candidate("John Roe");
    const { container } = render(CandidateComparison, {
      race: race({ candidates: [jane, john] }),
      candidates: [jane],
      onToggle,
    });

    await fireEvent.change(checkboxes(container)[1]);

    expect(onToggle).toHaveBeenCalledWith("John Roe");
  });
});

describe("CandidateComparison compact mode", () => {
  const withIssues = candidate("Jane Doe", {
    issues: {
      Healthcare: sourced("Healthcare stance"),
      Economy: sourced("Economy stance"),
      Immigration: sourced("Immigration stance"),
      Education: sourced("Education stance"),
      "Tech & AI": sourced("Tech stance"),
      // Present but unsourced — compact mode should skip it.
      "Foreign Policy": {
        stance: "Unsourced stance",
        confidence: "low",
        sources: [],
      },
    } as Candidate["issues"],
  });

  it("shows every canonical issue in full mode", () => {
    const { container } = render(CandidateComparison, {
      race: race({ candidates: [withIssues] }),
      candidates: [withIssues],
    });

    // Full mode includes issues with no data at all, e.g. Local Issues.
    expect(container.textContent).toContain("Local Issues");
  });

  it("limits compact mode to four issues", () => {
    const { container } = render(CandidateComparison, {
      race: race({ candidates: [withIssues] }),
      candidates: [withIssues],
      compact: true,
    });

    expect(container.textContent).not.toContain("Local Issues");
  });

  // Compact mode is for previews, so it only surfaces issues backed by a
  // source — an unsourced stance would look like researched data.
  it("skips issues whose stance has no sources", () => {
    const { container } = render(CandidateComparison, {
      race: race({ candidates: [withIssues] }),
      candidates: [withIssues],
      compact: true,
    });

    expect(container.textContent).not.toContain("Unsourced stance");
  });
});

describe("CandidateComparison avatars", () => {
  it("shows the headshot when one is available", () => {
    const jane = candidate("Jane Doe", {
      image_url: "https://example.test/jane.jpg",
    });
    const { container } = render(CandidateComparison, {
      race: race({ candidates: [jane] }),
      candidates: [jane],
    });

    expect(container.querySelector("img")?.getAttribute("src")).toBe(
      "https://example.test/jane.jpg",
    );
  });

  it("falls back to two initials when there is no headshot", () => {
    const jane = candidate("Jane Doe");
    const { container } = render(CandidateComparison, {
      race: race({ candidates: [jane] }),
      candidates: [jane],
    });

    expect(container.textContent).toContain("JD");
  });

  it("uses at most two initials for a long name", () => {
    const person = candidate("Ana Maria Gomez Ruiz");
    const { container } = render(CandidateComparison, {
      race: race({ candidates: [person] }),
      candidates: [person],
    });

    expect(container.textContent).toContain("AM");
    expect(container.textContent).not.toContain("AMGR");
  });

  // The desktop table and the embedded MobileCandidateComparison each render
  // their own <img> with independent failure state, so a dead headshot has to
  // be reported to both before the fallback is complete.
  it("swaps to initials when the headshot fails to load", async () => {
    const jane = candidate("Jane Doe", {
      image_url: "https://example.test/broken.jpg",
    });
    const { container } = render(CandidateComparison, {
      race: race({ candidates: [jane] }),
      candidates: [jane],
    });

    const images = Array.from(container.querySelectorAll("img"));
    expect(images.length).toBeGreaterThan(0);
    for (const image of images) await fireEvent.error(image);

    expect(container.querySelectorAll("img")).toHaveLength(0);
    expect(container.textContent).toContain("JD");
  });
});

describe("CandidateComparison forecast probability", () => {
  const jane = candidate("Jane Doe", { party: "Democratic" });

  function renderWithForecast(overrides: Partial<RaceForecast> | undefined) {
    const forecast: RaceForecast | undefined = overrides
      ? {
          party_probabilities: {},
          rating: "tossup",
          confidence: "medium",
          rationale: "Test rationale",
          key_reasons: [],
          based_on_poll_count: 0,
          generated_at: "2026-01-01T00:00:00Z",
          model: "test",
          source_urls: [],
          market_signals: [],
          ...overrides,
        }
      : undefined;
    return render(CandidateComparison, {
      race: race({ candidates: [jane], forecast }),
      candidates: [jane],
    });
  }

  it("uses the headline win probability for the predicted winner", () => {
    const { container } = renderWithForecast({
      predicted_winner_name: "Jane Doe",
      win_probability: 0.72,
      party_probabilities: {},
      rating: "lean_d",
      generated_at: "2026-01-01T00:00:00Z",
      model: "test",
    });

    expect(container.textContent).toContain("72%");
  });

  // Anyone who is not the predicted winner falls back to their party's
  // probability, matched loosely because the two vocabularies disagree
  // ("Democratic" vs "Democrat" vs "D").
  it.each([
    ["a full party name", { Democratic: 0.44 }],
    ["a shorter party key", { Democrat: 0.44 }],
    ["a single-letter key", { D: 0.44 }],
  ])("matches %s to the candidate's party", (_label, partyProbabilities) => {
    const { container } = renderWithForecast({
      predicted_winner_name: "Someone Else",
      win_probability: 0.9,
      party_probabilities: partyProbabilities,
      rating: "lean_d",
      generated_at: "2026-01-01T00:00:00Z",
      model: "test",
    });

    expect(container.textContent).toContain("44%");
  });

  it("shows no probability when the race has no forecast", () => {
    const { container } = renderWithForecast(undefined);

    expect(container.textContent).not.toContain("estimated win probability");
  });

  it("shows no probability when no party key matches", () => {
    const { container } = renderWithForecast({
      predicted_winner_name: "Someone Else",
      win_probability: 0.9,
      party_probabilities: { Republican: 0.9 },
      rating: "lean_r",
      generated_at: "2026-01-01T00:00:00Z",
      model: "test",
    });

    expect(container.textContent).not.toContain("estimated win probability");
  });
});
