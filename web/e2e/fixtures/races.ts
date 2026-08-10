import type { Race } from "../../src/lib/types";
import { fixtureSource } from "./sources";

/**
 * Race IDs used across the e2e suite. Kept as constants so specs and the
 * matching RaceSummary entries in `summaries.ts` never drift out of sync.
 */
export const FIXTURE_RACE_IDS = {
  senate: "e2e-oh-senate-2026",
  house: "e2e-oh-house-05-2026",
  governor: "e2e-nv-governor-2026",
  discovery: "e2e-tx-house-discovery-2026",
  uncontested: "e2e-fl-house-uncontested-2026",
} as const;

const longStance = (topic: string, lean: string): string =>
  `${lean} on ${topic}. This fixture stance is intentionally longer than the ` +
  `comparison view's inline preview so e2e specs can exercise the "Show more" ` +
  `and "Show less" toggle behavior deterministically instead of depending on ` +
  `whatever length real published data happens to have on a given day. ` +
  `It repeats a little to comfortably clear the truncation threshold.`;

/**
 * Full Race object for the Ohio Senate race — the primary "rich" fixture used
 * for race detail, candidate detail, and compare specs. Has two candidates,
 * a full issue set, polling, a forecast, validation grade, and AI reviews so
 * every major section of those pages renders.
 */
export const ohSenateRace: Race = {
  schema_version: "0.3",
  id: FIXTURE_RACE_IDS.senate,
  election_date: "2026-11-03T00:00:00Z",
  title: "Ohio U.S. Senate Race 2026",
  office: "U.S. Senate",
  jurisdiction: "Ohio",
  state: "Ohio",
  district: undefined,
  description:
    "A closely watched contest between the incumbent and a first-time statewide challenger.",
  contest_stage: "post_primary_general",
  updated_utc: "2026-06-01T00:00:00Z",
  generator: ["openai/gpt-5.4-mini", "anthropic/claude-haiku-4.5"],
  validation_grade: {
    grade: "A",
    score: 94,
    passed: true,
    summary: "Sourcing, methodology, and bias checks all passed review.",
  },
  reviews: [
    {
      model: "anthropic/claude-haiku-4.5",
      reviewed_at: "2026-06-01T00:00:00Z",
      verdict: "approved",
      score: 95,
      flags: [],
      summary: "Balanced coverage with well-sourced issue positions.",
    },
    {
      model: "x-ai/grok-4.3",
      reviewed_at: "2026-06-01T00:00:00Z",
      verdict: "approved",
      score: 92,
      flags: [
        {
          field: "candidates[1].donor_summary",
          concern: "Donor list could include one more recent filing.",
          suggestion: "Refresh from the latest FEC quarterly report.",
          severity: "info",
        },
      ],
      summary: "Minor freshness suggestion; no factual issues found.",
    },
  ],
  polling: [
    {
      pollster: "Fixture Polling Co.",
      date: "2026-05-20T00:00:00Z",
      sample_size: 812,
      matchups: [
        {
          candidates: ["Senator Jordan Ellsworth", "Casey Whitfield"],
          percentages: [49, 45],
        },
      ],
      source_url: "https://example.com/e2e-sources/poll-1",
    },
    {
      pollster: "Second Fixture Insights",
      date: "2026-04-02T00:00:00Z",
      sample_size: 640,
      matchups: [
        {
          candidates: ["Senator Jordan Ellsworth", "Casey Whitfield"],
          percentages: [48, 46],
        },
      ],
      source_url: "https://example.com/e2e-sources/poll-2",
    },
  ],
  forecast: {
    predicted_winner_name: "Senator Jordan Ellsworth",
    predicted_winner_party: "Democratic",
    win_probability: 0.52,
    party_probabilities: { Democratic: 0.52, Republican: 0.48 },
    margin_estimate: 1.4,
    rating: "tossup",
    confidence: "medium",
    rationale:
      "Polling has been within the margin of error all cycle, with the incumbent holding a narrow, stable lead.",
    takeaway: "One of the closest Senate races on the map this cycle.",
    key_reasons: [
      "Incumbency advantage offset by a strong statewide challenger.",
      "Turnout in suburban counties remains the key swing factor.",
    ],
    uncertainty:
      "Late undecided voters have historically broken toward the challenger's party in this state.",
    based_on_poll_count: 2,
    generated_at: "2026-06-01T00:00:00Z",
    model: "openai/gpt-5.4-mini",
    source_urls: ["https://example.com/e2e-sources/forecast-methodology"],
  },
  ballotpedia_url: "https://ballotpedia.org/e2e-fixture-oh-senate-2026",
  candidates: [
    {
      name: "Senator Jordan Ellsworth",
      party: "Democratic",
      incumbent: true,
      website: "https://example.com/ellsworth",
      social_media: {
        twitter: "https://twitter.com/SenEllsworth",
      },
      summary:
        "Two-term incumbent senator focused on manufacturing jobs, prescription drug costs, and infrastructure investment.",
      summary_sources: [fixtureSource("ellsworth-bio-1")],
      image_url: undefined,
      issues: {
        Healthcare: {
          stance: longStance("prescription drug pricing", "Supports"),
          confidence: "high",
          sources: [fixtureSource("ellsworth-healthcare")],
        },
        Economy: {
          stance: longStance("manufacturing and union jobs", "Champions"),
          confidence: "high",
          sources: [fixtureSource("ellsworth-economy")],
        },
        "Climate/Energy": {
          stance: longStance("clean energy manufacturing", "Backs"),
          confidence: "medium",
          sources: [fixtureSource("ellsworth-climate")],
        },
        Immigration: {
          stance: longStance("comprehensive immigration reform", "Favors"),
          confidence: "medium",
          sources: [fixtureSource("ellsworth-immigration")],
        },
        Education: {
          stance: longStance("community college funding", "Supports"),
          confidence: "low",
          sources: [fixtureSource("ellsworth-education")],
        },
        "Foreign Policy": {
          stance: longStance("NATO alliances", "Supports"),
          confidence: "high",
          sources: [fixtureSource("ellsworth-foreign-policy")],
        },
      },
      career_history: [
        {
          title: "U.S. Senator",
          organization: "United States Senate",
          start_year: 2020,
          description: "Serving Ohio's senior Senate seat.",
          source: fixtureSource("ellsworth-career-1"),
        },
        {
          title: "State Treasurer",
          organization: "State of Ohio",
          start_year: 2014,
          end_year: 2020,
          source: fixtureSource("ellsworth-career-2"),
        },
      ],
      education: [
        {
          institution: "Ohio State University",
          degree: "B.A.",
          field: "Economics",
          year: 2001,
          source: fixtureSource("ellsworth-edu-1"),
        },
      ],
      voting_summary:
        "Voted for the bipartisan infrastructure package and prescription drug pricing reform; voted against the most recent defense authorization amendment on unrelated spending grounds.",
      voting_source_url: "https://example.com/e2e-sources/ellsworth-voting",
      voting_sources: [fixtureSource("ellsworth-voting")],
      donor_summary:
        "Top contributors include the Machinists Union PAC ($22K), AFL-CIO PAC ($18K), and EMILY's List ($14K).",
      donor_source_url: "https://example.com/e2e-sources/ellsworth-donors",
      donor_sources: [fixtureSource("ellsworth-donors")],
      links: [
        {
          url: "https://example.com/e2e-sources/ellsworth-fec",
          title: "FEC Campaign Finance Data",
          type: "finance",
        },
      ],
    },
    {
      name: "Casey Whitfield",
      party: "Republican",
      incumbent: false,
      website: "https://example.com/whitfield",
      social_media: {
        twitter: "https://twitter.com/CaseyWhitfield",
      },
      summary:
        "Small business owner and first-time statewide candidate running on lower taxes and energy production.",
      summary_sources: [fixtureSource("whitfield-bio-1")],
      image_url: undefined,
      issues: {
        Healthcare: {
          stance: longStance("market-based healthcare reform", "Supports"),
          confidence: "medium",
          sources: [fixtureSource("whitfield-healthcare")],
        },
        Economy: {
          stance: longStance("small-business tax relief", "Champions"),
          confidence: "high",
          sources: [fixtureSource("whitfield-economy")],
        },
        "Climate/Energy": {
          stance: longStance("domestic energy production", "Prioritizes"),
          confidence: "high",
          sources: [fixtureSource("whitfield-climate")],
        },
        Immigration: {
          stance: longStance("border security", "Prioritizes"),
          confidence: "high",
          sources: [fixtureSource("whitfield-immigration")],
        },
        Education: {
          stance: longStance("school choice", "Supports"),
          confidence: "medium",
          sources: [fixtureSource("whitfield-education")],
        },
        "Foreign Policy": {
          stance: longStance("peace through strength", "Advocates for"),
          confidence: "low",
          sources: [fixtureSource("whitfield-foreign-policy")],
        },
      },
      career_history: [
        {
          title: "Owner",
          organization: "Whitfield Manufacturing",
          start_year: 2009,
          source: fixtureSource("whitfield-career-1"),
        },
      ],
      education: [
        {
          institution: "Miami University",
          degree: "B.S.",
          field: "Business",
          year: 2004,
          source: fixtureSource("whitfield-edu-1"),
        },
      ],
      voting_summary: undefined,
      donor_summary:
        "Top contributors include the Chamber of Commerce PAC ($20K), Club for Growth PAC ($16K), and American Energy Alliance ($10K).",
      donor_source_url: "https://example.com/e2e-sources/whitfield-donors",
      donor_sources: [fixtureSource("whitfield-donors")],
      links: [
        {
          url: "https://example.com/e2e-sources/whitfield-fec",
          title: "FEC Campaign Finance Data",
          type: "finance",
        },
      ],
    },
  ],
};

/**
 * Discovery-only race: candidate roster is known but no issue research has
 * run yet. Used to exercise the "Limited Data — Discovery Only" banner on
 * both the race detail page and the candidate detail page, plus the
 * "missing forecast" path on the forecast page.
 */
export const txHouseDiscoveryRace: Race = {
  schema_version: "0.3",
  id: FIXTURE_RACE_IDS.discovery,
  election_date: "2026-11-03T00:00:00Z",
  title: "Texas's 2nd Congressional District Race 2026",
  office: "U.S. House",
  jurisdiction: "Texas's 2nd Congressional District",
  state: "Texas",
  district: "2",
  contest_stage: "pre_primary",
  updated_utc: "2026-05-15T00:00:00Z",
  generator: ["openai/gpt-5.4-mini"],
  candidates: [
    {
      name: "Devon Marsh",
      party: "Republican",
      incumbent: true,
      summary: "Incumbent representative; detailed issue research not yet run.",
      summary_sources: [],
      issues: {},
      career_history: [],
      education: [],
      links: [],
      social_media: {},
    },
    {
      name: "Ines Okafor",
      party: "Democratic",
      incumbent: false,
      summary: "Challenger; detailed issue research not yet run.",
      summary_sources: [],
      issues: {},
      career_history: [],
      education: [],
      links: [],
      social_media: {},
    },
  ],
};

/**
 * Single-candidate (uncontested) race used to confirm the race detail page
 * degrades gracefully without a "Compare all" link or selection checkboxes
 * when there's nobody to compare against.
 */
export const flHouseUncontestedRace: Race = {
  schema_version: "0.3",
  id: FIXTURE_RACE_IDS.uncontested,
  election_date: "2026-11-03T00:00:00Z",
  title: "Florida's 9th Congressional District Race 2026",
  office: "U.S. House",
  jurisdiction: "Florida's 9th Congressional District",
  state: "Florida",
  district: "9",
  contest_stage: "uncontested",
  updated_utc: "2026-05-01T00:00:00Z",
  generator: ["openai/gpt-5.4-mini"],
  candidates: [
    {
      name: "Robin Castillo",
      party: "Democratic",
      incumbent: true,
      summary: "Running unopposed this cycle.",
      summary_sources: [fixtureSource("castillo-bio")],
      issues: {
        Healthcare: {
          stance: longStance("expanding rural clinics", "Supports"),
          confidence: "high",
          sources: [fixtureSource("castillo-healthcare")],
        },
      },
      career_history: [],
      education: [],
      links: [],
      social_media: {},
    },
  ],
};
