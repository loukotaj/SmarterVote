import type { Race } from "./types";

/**
 * Sample race data for fallback when API is unavailable
 * Based on the Missouri Senate 2024 example data
 */
export const sampleRace: Race = {
  id: "sample-race-fallback",
  election_date: "2025-11-05T00:00:00Z",
  title: "Sample State U.S. Senate Race 2025",
  office: "U.S. Senate",
  jurisdiction: "Sample State",
  updated_utc: "2025-01-15T12:00:00Z",
  generator: ["gpt-4o", "claude-3.5", "grok-4"],
  candidates: [
    {
      name: "Jane Smith",
      party: "Republican",
      incumbent: true,
      website: "https://www.example-candidate-website.com",
      social_media: {
        twitter: "https://twitter.com/example_candidate",
        facebook: "https://facebook.com/example.candidate"
      },
      summary: "Example conservative candidate with fictional policy positions for demonstration purposes only. This is dummy data for testing.",
      issues: {
        Healthcare: {
          stance: "Example stance on healthcare policy for demonstration purposes only. This is fictional test data.",
          confidence: "high",
          sources: ["src:example:dummy-source-1", "src:test:fake-voting-record"]
        },
        Economy: {
          stance: "Sample economic policy position. This is dummy data for testing the system.",
          confidence: "medium",
          sources: ["src:example:economic-plan", "src:test:sample-speech"]
        },
        "Climate/Energy": {
          stance: "Example climate and energy position for testing purposes only.",
          confidence: "low",
          sources: ["src:test:climate-statement", "src:example:energy-policy"]
        },
        Immigration: {
          stance: "Sample immigration policy stance. This is fictional test data.",
          confidence: "high",
          sources: ["src:example:border-policy", "src:test:immigration-speech"]
        },
        "Reproductive Rights": {
          stance: "Sample stance on reproductive rights. This is test data.",
          confidence: "medium",
          sources: ["src:example:repro-policy"]
        },
        "Guns & Safety": {
          stance: "Example gun safety position for testing.",
          confidence: "low",
          sources: ["src:test:gun-statement"]
        },
        "Foreign Policy": {
          stance: "Sample foreign policy stance for demonstration.",
          confidence: "medium",
          sources: ["src:example:foreign-plan"]
        },
        "Social Justice": {
          stance: "Example social justice position for testing.",
          confidence: "low",
          sources: ["src:test:social-justice-statement"]
        },
        Education: {
          stance: "Sample education policy for demonstration.",
          confidence: "medium",
          sources: ["src:example:edu-plan"]
        },
        "Tech & AI": {
          stance: "Example tech policy stance for testing.",
          confidence: "low",
          sources: ["src:test:tech-statement"]
        },
        "Election Reform": {
          stance: "Sample election reform position for demonstration.",
          confidence: "medium",
          sources: ["src:example:election-plan"]
        }
      },
      top_donors: [
        {
          name: "Example PAC Organization",
          amount: 10000.0,
          organization: "Test Political Action Committee",
          source: "src:example:dummy-donations"
        },
        {
          name: "Sample Industry Group",
          amount: 5000.0,
          organization: "Fictional Trade Association",
          source: "src:test:fake-fec-data"
        }
      ]
    },
    {
      name: "John Doe",
      party: "Democratic",
      incumbent: false,
      website: "https://www.example-democrat-candidate.com",
      social_media: {
        twitter: "https://twitter.com/example_dem",
        facebook: "https://facebook.com/example.democrat"
      },
      summary: "Example progressive candidate with fictional policy positions for demonstration purposes only. This is dummy test data.",
      issues: {
        Healthcare: {
          stance: "Sample healthcare policy position for testing purposes. This is fictional data.",
          confidence: "high",
          sources: ["src:example:health-plan", "src:test:dummy-interview"]
        },
        Economy: {
          stance: "Example economic policy stance for demonstration. This is test data only.",
          confidence: "medium",
          sources: ["src:test:economic-speech", "src:example:worker-policy"]
        },
        "Climate/Energy": {
          stance: "Sample climate action position for testing purposes only.",
          confidence: "high",
          sources: ["src:example:climate-plan", "src:test:green-energy"]
        },
        Education: {
          stance: "Example education policy for demonstration purposes. This is dummy data.",
          confidence: "medium",
          sources: ["src:test:education-forum", "src:example:school-funding"]
        },
        "Reproductive Rights": {
          stance: "Sample reproductive rights position for testing.",
          confidence: "high",
          sources: ["src:example:repro-plan"]
        },
        "Guns & Safety": {
          stance: "Example gun safety stance for demonstration.",
          confidence: "high",
          sources: ["src:test:gun-plan"]
        },
        "Foreign Policy": {
          stance: "Sample foreign policy position for testing.",
          confidence: "medium",
          sources: ["src:example:foreign-statement"]
        },
        "Social Justice": {
          stance: "Example social justice stance for demonstration.",
          confidence: "high",
          sources: ["src:test:social-justice-plan"]
        },
        Immigration: {
          stance: "Sample immigration policy for testing purposes.",
          confidence: "medium",
          sources: ["src:example:immigration-plan"]
        },
        "Tech & AI": {
          stance: "Example technology policy stance for demonstration.",
          confidence: "medium",
          sources: ["src:test:tech-plan"]
        },
        "Election Reform": {
          stance: "Sample election reform position for testing.",
          confidence: "high",
          sources: ["src:example:reform-plan"]
        }
      },
      top_donors: [
        {
          name: "Example Labor Union",
          amount: 15000.0,
          organization: "Test Workers Union",
          source: "src:example:union-donations"
        },
        {
          name: "Sample Advocacy Group",
          amount: 8000.0,
          organization: "Fictional Issue PAC",
          source: "src:test:advocacy-funding"
        }
      ]
    }
  ]
};

/**
 * Map of sample races by slug for fallback data
 */
export const sampleRaces: Record<string, Race> = {
  "sample-race": sampleRace,
  "mo-senate-2024": {
    ...sampleRace,
    id: "mo-senate-2024",
    title: "Missouri U.S. Senate Race 2024",
    jurisdiction: "Missouri"
  },
  "ca-senate-2024": {
    ...sampleRace,
    id: "ca-senate-2024",
    title: "California U.S. Senate Race 2024",
    jurisdiction: "California"
  },
  "ny-house-03-2024": {
    ...sampleRace,
    id: "ny-house-03-2024",
    title: "New York House District 3 Race 2024",
    office: "U.S. House",
    jurisdiction: "New York District 3"
  },
  "tx-governor-2024": {
    ...sampleRace,
    id: "tx-governor-2024",
    title: "Texas Governor Race 2024",
    office: "Governor",
    jurisdiction: "Texas"
  }
};
