import type { ChamberForecasts, RaceSummary } from "../../src/lib/types";
import { FIXTURE_RACE_IDS, ohSenateRace, txHouseDiscoveryRace } from "./races";

/**
 * Race summary index used to back `summaries.json` for the whole e2e suite
 * (elections directory, ballot lookup, forecast page, and the homepage all
 * read from this single list). Kept deliberately small but varied: one
 * tossup Senate race, one lean-R House race, one likely-D Governor race, and
 * one race with no forecast yet, spread across three states so search/filter
 * and state-based ballot matching all have something real to exercise.
 */
export const FIXTURE_SUMMARIES: RaceSummary[] = [
  {
    id: FIXTURE_RACE_IDS.senate,
    title: ohSenateRace.title,
    office: ohSenateRace.office,
    jurisdiction: ohSenateRace.jurisdiction,
    state: ohSenateRace.state,
    contest_stage: ohSenateRace.contest_stage,
    election_date: ohSenateRace.election_date,
    updated_utc: ohSenateRace.updated_utc,
    quality_grade: "A",
    candidates: ohSenateRace.candidates.map((candidate) => ({
      name: candidate.name,
      party: candidate.party,
      incumbent: candidate.incumbent,
      image_url: candidate.image_url,
    })),
    forecast: ohSenateRace.forecast,
  },
  {
    id: FIXTURE_RACE_IDS.house,
    title: "Ohio's 5th Congressional District Race 2026",
    office: "U.S. House",
    jurisdiction: "Ohio's 5th Congressional District",
    state: "Ohio",
    contest_stage: "post_primary_general",
    election_date: "2026-11-03T00:00:00Z",
    updated_utc: "2026-05-28T00:00:00Z",
    quality_grade: "B",
    candidates: [
      {
        name: "Representative Alan Voss",
        party: "Republican",
        incumbent: true,
      },
      { name: "Priya Natarajan", party: "Democratic", incumbent: false },
      { name: "Sam Whitcombe", party: "Independent", incumbent: false },
    ],
    forecast: {
      predicted_winner_name: "Representative Alan Voss",
      predicted_winner_party: "Republican",
      win_probability: 0.68,
      party_probabilities: { Democratic: 0.3, Republican: 0.68, Other: 0.02 },
      margin_estimate: 8.5,
      rating: "lean_r",
      confidence: "medium",
      rationale:
        "The incumbent has a durable registration edge in this district despite a credible challenger.",
      based_on_poll_count: 1,
      generated_at: "2026-05-28T00:00:00Z",
      model: "openai/gpt-5.4-mini",
      source_urls: [],
    },
  },
  {
    id: FIXTURE_RACE_IDS.governor,
    title: "Nevada Governor Race 2026",
    office: "Governor",
    jurisdiction: "Nevada",
    state: "Nevada",
    contest_stage: "post_primary_general",
    election_date: "2026-11-03T00:00:00Z",
    updated_utc: "2026-05-10T00:00:00Z",
    quality_grade: "A",
    candidates: [
      { name: "Governor Denise Marlowe", party: "Democratic", incumbent: true },
      { name: "Todd Ibarra", party: "Republican", incumbent: false },
    ],
    forecast: {
      predicted_winner_name: "Governor Denise Marlowe",
      predicted_winner_party: "Democratic",
      win_probability: 0.71,
      party_probabilities: { Democratic: 0.71, Republican: 0.29 },
      margin_estimate: 6.2,
      rating: "likely_d",
      confidence: "high",
      rationale:
        "The incumbent governor maintains a comfortable, stable lead across independent polling.",
      based_on_poll_count: 4,
      generated_at: "2026-05-10T00:00:00Z",
      model: "openai/gpt-5.4-mini",
      source_urls: [],
    },
  },
  {
    id: FIXTURE_RACE_IDS.discovery,
    title: txHouseDiscoveryRace.title,
    office: txHouseDiscoveryRace.office,
    jurisdiction: txHouseDiscoveryRace.jurisdiction,
    state: txHouseDiscoveryRace.state,
    contest_stage: txHouseDiscoveryRace.contest_stage,
    election_date: txHouseDiscoveryRace.election_date,
    updated_utc: txHouseDiscoveryRace.updated_utc,
    candidates: txHouseDiscoveryRace.candidates.map((candidate) => ({
      name: candidate.name,
      party: candidate.party,
      incumbent: candidate.incumbent,
      image_url: candidate.image_url,
    })),
    // No forecast yet — exercises the "missing forecast" / discovery-only path.
    forecast: null,
  },
];

/**
 * Chamber forecast index used to back `chamber_forecasts.json`. Numbers are
 * intentionally simple/round so specs can assert on them directly rather than
 * recomputing expected aggregates.
 */
export const FIXTURE_CHAMBER_FORECASTS: ChamberForecasts = {
  schema_version: "chamber_forecasts.v2",
  house:
    "House control is a nailbiter, with several competitive suburban seats.",
  senate:
    "Democrats have a narrow but real path to holding the Senate majority.",
  governors: "Governor's races lean Democratic this cycle.",
  updated_at: "2026-06-01T00:00:00Z",
  chambers: {
    house: {
      narrative:
        "House control is a nailbiter, with several competitive suburban seats.",
      control_party: "Republican",
      control_probability: 0.55,
      outcome_probabilities: { Democratic: 0.45, Republican: 0.55 },
      projected_seats: { Democratic: 214, Republican: 220, Other: 1 },
      expected_seats: { Democratic: 214, Republican: 220, Other: 1 },
      threshold: 218,
      total_seats: 435,
      tossup_count: 1,
      competitive_race_count: 1,
      competitive_races: ["Ohio's 5th Congressional District Race 2026"],
      method: "e2e_fixture",
    },
    senate: {
      narrative:
        "Democrats have a narrow but real path to holding the Senate majority.",
      control_party: "Democratic",
      control_probability: 0.52,
      outcome_probabilities: { Democratic: 0.52, Republican: 0.48 },
      projected_seats: { Democratic: 51, Republican: 49 },
      expected_seats: { Democratic: 50.6, Republican: 49.4 },
      threshold: 51,
      total_seats: 100,
      tossup_count: 1,
      competitive_race_count: 1,
      competitive_races: ["Ohio U.S. Senate Race 2026"],
      method: "e2e_fixture",
    },
    governors: {
      narrative: "Governor's races lean Democratic this cycle.",
      control_party: "Democratic",
      control_probability: 0.6,
      outcome_probabilities: { Democratic: 0.6, Republican: 0.4 },
      projected_seats: { Democratic: 27, Republican: 23 },
      expected_seats: { Democratic: 26.7, Republican: 23.3 },
      threshold: 26,
      total_seats: 50,
      tossup_count: 0,
      competitive_race_count: 1,
      competitive_races: ["Nevada Governor Race 2026"],
      method: "e2e_fixture",
    },
  },
};
