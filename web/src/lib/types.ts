/**
 * TypeScript definitions for SmarterVote RaceJSON v0.2
 */

export type ConfidenceLevel = "high" | "medium" | "low" | "unknown";

export type SourceType =
  | "website"
  | "pdf"
  | "api"
  | "social_media"
  | "news"
  | "government"
  | "fresh_search";

export type CanonicalIssue =
  | "Healthcare"
  | "Economy"
  | "Climate/Energy"
  | "Reproductive Rights"
  | "Immigration"
  | "Guns & Safety"
  | "Foreign Policy"
  | "Social Justice"
  | "Education"
  | "Tech & AI"
  | "Election Reform";

export interface Source {
  url: string;
  type: SourceType;
  title?: string;
  description?: string;
  last_accessed: string;
  checksum?: string;
  is_fresh?: boolean;
}

export interface IssueStance {
  stance: string;
  confidence: ConfidenceLevel;
  sources: Source[];
}

export interface TopDonor {
  name: string;
  amount?: number;
  organization?: string;
  source: Source;
}

export interface VotingRecord {
  bill_name: string;
  bill_description?: string;
  vote: "yes" | "no" | "abstain" | "absent";
  date: string;
  source: Source;
}

export interface Candidate {
  name: string;
  party?: string;
  incumbent: boolean;
  summary: string;
  issues: Record<CanonicalIssue, IssueStance>;
  top_donors: TopDonor[];
  voting_record?: VotingRecord[];
  website?: string;
  social_media: Record<string, string>;
}

export interface Race {
  id: string;
  election_date: string;
  candidates: Candidate[];
  updated_utc: string;
  generator: string[];
  title?: string;
  office?: string;
  jurisdiction?: string;
}

export const CANONICAL_ISSUES: CanonicalIssue[] = [
  "Healthcare",
  "Economy",
  "Climate/Energy",
  "Reproductive Rights",
  "Immigration",
  "Guns & Safety",
  "Foreign Policy",
  "Social Justice",
  "Education",
  "Tech & AI",
  "Election Reform",
];

export interface CandidateSummary {
  name: string;
  party?: string;
  incumbent: boolean;
}

export interface RaceSummary {
  id: string;
  title?: string;
  office?: string;
  jurisdiction?: string;
  election_date: string;
  updated_utc: string;
  candidates: CandidateSummary[];
}

// Pipeline run types
export type RunStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface RunStep {
  name: string;
  status: RunStatus;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  artifact_id?: string;
  error?: string;
}

export interface RunInfo {
  run_id: string;
  status: RunStatus;
  payload: Record<string, any>;
  options: Record<string, any>;
  started_at: string;
  completed_at?: string;
  duration_ms?: number;
  artifact_id?: string;
  error?: string;
  steps: RunStep[];
  logs?: Record<string, any>[];
}
