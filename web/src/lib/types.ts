/**
 * TypeScript definitions for SmarterVote RaceJSON v0.3
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
  | "Election Reform"
  | "Local Issues";

export interface Source {
  url: string;
  type: SourceType;
  title?: string;
  description?: string;
  last_accessed: string;
  published_at?: string;
  checksum?: string;
  is_fresh?: boolean;
  is_official_campaign?: boolean;
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
  donation_year?: string;
  source?: Source;
}

export interface CareerEntry {
  title: string;
  organization?: string;
  start_year?: number;
  end_year?: number;
  description?: string;
  source?: Source;
}

export interface EducationEntry {
  institution: string;
  degree?: string;
  field?: string;
  year?: number;
  source?: Source;
}

export interface VotingRecord {
  bill_name: string;
  bill_description?: string;
  vote: "yes" | "no" | "abstain" | "absent";
  date?: string;
  source?: Source;
}

export interface ReviewFlag {
  field: string;
  concern: string;
  suggestion?: string;
  severity: "info" | "warning" | "error";
}

export interface AgentReview {
  model: string;
  reviewed_at: string;
  verdict: "approved" | "needs_revision" | "flagged";
  flags: ReviewFlag[];
  summary: string;
}

export interface Candidate {
  name: string;
  party?: string;
  incumbent: boolean;
  summary: string;
  summary_sources: Source[];
  image_url?: string;
  issues: Record<CanonicalIssue, IssueStance>;
  career_history: CareerEntry[];
  education: EducationEntry[];
  voting_record: VotingRecord[];
  voting_summary?: string;
  voting_source_url?: string;
  top_donors: TopDonor[];
  donor_source_url?: string;
  website?: string;
  social_media: Record<string, string>;
}

export interface PollMatchup {
  candidates: string[];
  percentages: number[];
}

export interface PollEntry {
  pollster: string;
  date?: string;
  sample_size?: number;
  matchups: PollMatchup[];
  source_url?: string;
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
  description?: string;
  polling?: PollEntry[];
  reviews?: AgentReview[];
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
  "Local Issues",
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

export interface RunOptions {
  save_artifact?: boolean;
  note?: string;
  enable_review?: boolean;
  cheap_mode?: boolean;
  research_model?: string;
  claude_model?: string;
  gemini_model?: string;
  grok_model?: string;
}

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
  payload: Record<string, unknown>;
  options: RunOptions;
  started_at: string;
  completed_at?: string;
  duration_ms?: number;
  artifact_id?: string;
  error?: string;
  steps: RunStep[];
  logs?: LogEntry[];
}

export interface Artifact {
  id: string;
  path: string;
  size: number;
  modified: number;
}

export interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  step?: string;
  run_id?: string;
  race_id?: string;
  duration_ms?: number;
  extra?: Record<string, unknown>;
}

export interface RunHistoryItem extends RunInfo {
  display_id: number;
  updated_at: string;
  last_step?: string;
}

// ---------------------------------------------------------------------------
// Analytics & Alerts (admin dashboard)
// ---------------------------------------------------------------------------

export interface TimeseriesBucket {
  time: string; // HH:MM
  requests: number;
}

export interface AnalyticsOverview {
  total_requests: number;
  unique_visitors: number;
  avg_latency_ms: number;
  error_rate: number; // percentage 0-100
  error_count: number;
  timeseries: TimeseriesBucket[];
  hours: number;
}

export interface RaceAnalytics {
  race_id: string;
  requests_24h: number;
  last_accessed?: string;
  updated_utc?: string;
  title?: string;
}

export interface Alert {
  id: string;
  severity: "info" | "warning" | "critical";
  category: "freshness" | "failures" | "quality" | "analytics";
  message: string;
  details: Record<string, unknown>;
  created_at: string;
  acknowledged: boolean;
}

// ---------------------------------------------------------------------------
// Pipeline cost metrics
// ---------------------------------------------------------------------------

export interface AgentMetrics {
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_usd: number;
  model_breakdown: Record<string, { prompt_tokens: number; completion_tokens: number }>;
  duration_s: number;
}

export interface PipelineRunRecord {
  run_id: string;
  race_id: string;
  status: string;
  timestamp: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_usd: number;
  model_breakdown: Record<string, { prompt_tokens: number; completion_tokens: number }>;
  duration_s: number;
}

export interface PipelineMetricsSummary {
  total_runs: number;
  total_usd: number;
  avg_usd: number;
  recent_30d_usd: number;
}
