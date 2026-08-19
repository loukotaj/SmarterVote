import { describe, expect, it } from "vitest";
import { researchEventChoices } from "./researchProgram";

describe("researchEventChoices", () => {
  it("uses the general event for a contest without a primary", () => {
    const choices = researchEventChoices({
      race_id: "ar-supreme-court-2026",
      state: "Arkansas",
      office: "state_supreme_court",
      event_type: "nonpartisan_general",
      primary_date: null,
      runoff_date: null,
      general_election_date: "2026-03-03",
      schedule_source_url: "https://example.gov/elections",
    });

    expect(choices).toEqual([
      {
        key: "general|2026-03-03",
        kind: "General",
        eventType: "nonpartisan_general",
        eventDate: "2026-03-03",
      },
    ]);
  });

  it("keeps primary and runoff checkpoints distinct", () => {
    const choices = researchEventChoices({
      race_id: "ga-senate-2026",
      state: "Georgia",
      office: "us_senate",
      event_type: "regular_primary",
      primary_date: "2026-05-19",
      runoff_date: "2026-06-16",
      general_election_date: "2026-11-03",
      schedule_source_url: "https://example.gov/elections",
    });

    expect(
      choices.map(({ eventType, eventDate }) => ({ eventType, eventDate })),
    ).toEqual([
      { eventType: "regular_primary", eventDate: "2026-05-19" },
      { eventType: "primary_runoff", eventDate: "2026-06-16" },
      { eventType: "general_election", eventDate: "2026-11-03" },
    ]);
  });
});
