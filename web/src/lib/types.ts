/**
 * TypeScript definitions for SmarterVote RaceJSON v0.3
 */

export type ConfidenceLevel = "high" | "medium" | "low" | "unknown";

export type SourceType =
  | "website"
  | "finance"
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
  | "Abortion & Reproductive Health"
  | "Immigration"
  | "Firearms & Second Amendment"
  | "Foreign Policy"
  | "Civil Rights & Equality"
  | "Education"
  | "Tech & AI"
  | "Election Policy"
  | "Local Issues";

/**
 * All valid issue keys — includes current canonical names plus legacy names from
 * pre-rename published data. Used for the Candidate.issues record type.
 */
export type IssueKey =
  | CanonicalIssue
  | "Reproductive Rights"
  | "Guns & Safety"
  | "Social Justice"
  | "Election Reform";

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
  issue?: IssueKey;
  stance: string;
  confidence: ConfidenceLevel;
  sources: Source[];
}

export interface CandidateLink {
  url: string;
  title: string;
  type:
    | "finance"
    | "ballotpedia"
    | "wiki"
    | "official"
    | "legislature"
    | "votesmart"
    | "govtrack"
    | "news"
    | "other";
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
  score?: number;
  flags: ReviewFlag[];
  summary: string;
}

export interface ValidationGrade {
  grade: "A" | "B" | "C" | "D" | "F";
  score: number;
  passed: boolean;
  summary: string;
}

export type ForecastRating =
  | "safe_d"
  | "likely_d"
  | "lean_d"
  | "tilt_d"
  | "tossup"
  | "tilt_r"
  | "lean_r"
  | "likely_r"
  | "safe_r"
  | "other";

export interface RaceForecast {
  predicted_winner_name?: string;
  predicted_winner_party?: string;
  win_probability?: number;
  party_probabilities: Record<string, number>;
  margin_estimate?: number;
  rating: ForecastRating;
  confidence: ConfidenceLevel;
  rationale: string;
  based_on_poll_count: number;
  generated_at: string;
  model: string;
  source_urls: string[];
}

export interface Candidate {
  name: string;
  party?: string;
  incumbent: boolean;
  summary: string;
  summary_sources: Source[];
  image_url?: string;
  issues: Partial<Record<IssueKey, IssueStance>>;
  career_history: CareerEntry[];
  education: EducationEntry[];
  voting_summary?: string;
  voting_source_url?: string;
  voting_sources?: Source[];
  donor_summary?: string;
  donor_source_url?: string;
  donor_sources?: Source[];
  links: CandidateLink[];
  website?: string;
  social_media: Record<string, string>;
  withdrawn?: boolean;
  withdrawal_reason?: string;
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

export interface PipelineState {
  complete: boolean;
  remaining_candidates: string[];
  remaining_steps: string[];
  completed_units: string[];
}

export interface Race {
  schema_version?: string;
  id: string;
  election_date: string;
  candidates: Candidate[];
  updated_utc: string;
  generator: string[];
  title?: string;
  office?: string;
  jurisdiction?: string; // Full geographic scope (e.g. "Missouri's 1st Congressional District")
  state?: string; // US state name for map highlighting; null for national races
  district?: string;
  description?: string;
  polling?: PollEntry[];
  polling_note?: string;
  forecast?: RaceForecast;
  reviews?: AgentReview[];
  validation_grade?: ValidationGrade;
  pipeline_state?: PipelineState;
  agent_metrics?: AgentMetrics;
  ballotpedia_url?: string;
  register_to_vote_url?: string;
  how_to_vote_url?: string;
}

export const CANONICAL_ISSUES: CanonicalIssue[] = [
  "Healthcare",
  "Economy",
  "Climate/Energy",
  "Abortion & Reproductive Health",
  "Immigration",
  "Firearms & Second Amendment",
  "Foreign Policy",
  "Civil Rights & Equality",
  "Education",
  "Tech & AI",
  "Election Policy",
  "Local Issues",
];

/**
 * Maps legacy (biased) issue names to their current neutral display names.
 * Old published JSON data uses the legacy keys; the frontend resolves them here.
 */
export const LEGACY_ISSUE_NAMES: Partial<Record<string, CanonicalIssue>> = {
  "Reproductive Rights": "Abortion & Reproductive Health",
  "Guns & Safety": "Firearms & Second Amendment",
  "Social Justice": "Civil Rights & Equality",
  "Election Reform": "Election Policy",
};

/**
 * Tooltip note shown next to renamed issues so users understand why the name
 * changed and that existing data was researched under the old terminology.
 */
export const RENAMED_ISSUE_NOTES: Partial<Record<string, string>> = {
  "Reproductive Rights":
    'Data was researched using the term "Reproductive Rights" which has been renamed to "Abortion & Reproductive Health" in an effort to reduce bias. We are working to update all of our data as quickly as possible!',
  "Guns & Safety":
    'Data was researched using the term "Guns & Safety" which has been renamed to "Firearms & Second Amendment" in an effort to reduce bias. We are working to update all of our data as quickly as possible!',
  "Social Justice":
    'Data was researched using the term "Social Justice" which has been renamed to "Civil Rights & Equality" in an effort to reduce bias. We are working to update all of our data as quickly as possible!',
  "Election Reform":
    'Data was researched using the term "Election Reform" which has been renamed to "Election Policy" in an effort to reduce bias. We are working to update all of our data as quickly as possible!',
};

/** Returns the current neutral display name for an issue (resolves legacy names). */
export function getIssueDisplayName(issue: string): string {
  return (LEGACY_ISSUE_NAMES[issue] as string) ?? issue;
}

export interface CandidateSummary {
  name: string;
  party?: string;
  incumbent: boolean;
  image_url?: string;
}

export interface RaceSummary {
  id: string;
  title?: string;
  office?: string;
  jurisdiction?: string;
  state?: string;
  election_date: string;
  updated_utc: string;
  candidates: CandidateSummary[];
  agent_metrics?: {
    estimated_usd?: number;
    model?: string;
    total_tokens?: number;
  } | null;
  forecast?: RaceForecast | null;
}

// Pipeline run types
export type RunStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "continued"
  | "skipped";

// Canonical pipeline step identifiers
export type PipelineStepId =
  | "discovery"
  | "images"
  | "issues"
  | "finance"
  | "refinement"
  | "polling"
  | "forecast"
  | "voter_resources"
  | "review"
  | "iteration";

export const PIPELINE_STEPS: {
  id: PipelineStepId;
  label: string;
  weight: number;
}[] = [
  { id: "discovery", label: "Discovery", weight: 12 },
  { id: "images", label: "Image Resolution", weight: 4 },
  { id: "issues", label: "Issue Research", weight: 28 },
  { id: "finance", label: "Finance & Voting", weight: 9 },
  { id: "refinement", label: "Refinement", weight: 11 },
  { id: "polling", label: "Polling", weight: 7 },
  { id: "forecast", label: "Forecast", weight: 4 },
  { id: "voter_resources", label: "Voter Resources", weight: 5 },
  { id: "review", label: "AI Review", weight: 12 },
  { id: "iteration", label: "Review Iteration", weight: 8 },
];

export interface RunOptions {
  save_artifact?: boolean;
  note?: string;
  goal?: string;
  cheap_mode?: boolean;
  model_profile?: "economy" | "balanced" | "quality" | "custom";
  model_overrides?: {
    primary?: string;
    small?: string;
    review_claude?: string;
    review_gemini?: string;
    review_grok?: string;
  };
  force_fresh?: boolean;
  research_model?: string;
  claude_model?: string;
  gemini_model?: string;
  grok_model?: string;
  review_providers?: ("claude" | "gemini" | "grok")[];
  enabled_steps?: string[];
  max_candidates?: number;
  target_no_info?: boolean;
  candidate_names?: string[];
}

export interface RunStep {
  name: string;
  label?: string;
  status: RunStatus;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  progress_pct?: number;
  weight?: number;
  artifact_id?: string;
  error?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  estimated_usd?: number;
}

export interface RunInfo {
  run_id: string;
  race_id?: string;
  status: RunStatus;
  progress?: number;
  progress_message?: string;
  current_step?: PipelineStepId | string | null;
  current_step_progress?: number;
  remaining_steps?: string[];
  payload?: Record<string, unknown>;
  options: RunOptions;
  started_at: string;
  completed_at?: string;
  duration_ms?: number;
  artifact_id?: string;
  error?: string;
  steps?: RunStep[];
  logs?: LogEntry[];
  serper_calls?: number;
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

export interface TrafficDimension {
  name: string;
  pageviews: number;
  visits: number;
}

export interface TrafficTimeseriesBucket {
  time: string;
  pageviews: number;
  visits: number;
}

export interface TrafficAnalytics {
  configured: boolean;
  provider: "cloudflare";
  hours: number;
  pageviews: number;
  visits: number;
  pages_per_visit: number;
  timeseries: TrafficTimeseriesBucket[];
  top_pages: TrafficDimension[];
  top_referrers: TrafficDimension[];
  countries: TrafficDimension[];
  devices: TrafficDimension[];
  fetched_at: string | null;
  error: string | null;
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
  cost_usd?: number | null;
  cost_source?: "provider" | "estimated";
  serper_calls?: number;
  model_breakdown: Record<
    string,
    { prompt_tokens: number; completion_tokens: number }
  >;
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
  cost_usd?: number | null;
  cost_source?: "provider" | "estimated";
  serper_calls?: number;
  model_breakdown: Record<
    string,
    { prompt_tokens: number; completion_tokens: number }
  >;
  duration_s: number;
  candidate_count: number;
  cheap_mode: boolean;
}

export interface PipelineMetricsSummary {
  total_runs: number;
  total_usd: number;
  avg_usd: number;
  recent_30d_usd: number;
  success_rate: number;
  cheap_runs: number;
  avg_cheap_usd: number;
  full_runs: number;
  avg_full_usd: number;
  avg_usd_per_candidate: number;
}

// ---------------------------------------------------------------------------
// Unified Race Record (mirrors Python RaceRecord)
// ---------------------------------------------------------------------------

export type RaceStatusType =
  | "empty"
  | "queued"
  | "running"
  | "draft"
  | "published"
  | "failed";

export interface RaceRecord {
  race_id: string;
  title?: string;
  office?: string;
  jurisdiction?: string;
  election_date?: string;

  status: RaceStatusType;
  published_at?: string;
  draft_updated_at?: string;
  draft_exists?: boolean;
  published_exists?: boolean;
  draft_quality_grade?: "A" | "B" | "C" | "D" | "F";
  published_quality_grade?: "A" | "B" | "C" | "D" | "F";
  draft_candidate_count?: number;
  published_candidate_count?: number;
  draft_updated_utc?: string;
  published_updated_utc?: string;
  public_updated_utc?: string;
  has_unpublished_changes?: boolean;

  candidate_count: number;
  quality_grade?: "A" | "B" | "C" | "D" | "F";
  freshness?: string;

  queue_position?: number;
  queue_options?: Record<string, unknown>;
  last_run_options?: Record<string, unknown>;
  current_run_id?: string;
  last_run_id?: string;
  last_run_at?: string;
  last_run_status?: string;
  total_runs: number;

  requests_24h: number;
  last_accessed?: string;

  created_at: string;
  updated_at: string;
}
