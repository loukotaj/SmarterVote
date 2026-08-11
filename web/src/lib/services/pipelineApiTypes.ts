import type { ChamberForecasts, RaceRecord, RunInfo } from "$lib/types";

export interface RunsResponse {
  runs: RunInfo[];
}

export interface PublishedRaceSummary {
  id: string;
  title?: string;
  office?: string;
  jurisdiction?: string;
  state?: string;
  election_date: string;
  updated_utc: string;
  candidates: {
    name: string;
    party?: string;
    incumbent?: boolean;
    image_url?: string;
  }[];
  agent_metrics?: {
    estimated_usd?: number;
    model?: string;
    total_tokens?: number;
  } | null;
}

export interface PublishedRacesResponse {
  races: PublishedRaceSummary[];
}

export interface QueueItem {
  id: string;
  race_id: string;
  status:
    | "pending"
    | "running"
    | "completed"
    | "failed"
    | "cancelled"
    | "continued";
  options: Record<string, unknown>;
  run_id?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
  parent_run_id?: string;
  parent_queue_item_id?: string;
  is_continuation?: boolean;
}

export interface QueueResponse {
  items: QueueItem[];
  running: boolean;
  pending: number;
}

export interface QueueAddResponse {
  added: QueueItem[];
  errors: Array<{ race_id: string; error: string }>;
}

export interface RaceListResponse {
  races: RaceRecord[];
}

export interface RaceQueueResponse {
  added: RaceRecord[];
  errors: Array<{ race_id: string; error: string }>;
}

export interface RaceRunsResponse {
  runs: RunInfo[];
  count: number;
}

export interface RaceVersion {
  filename: string;
  source: "draft" | "published" | string;
  archived_at: string | null;
  size_bytes: number;
}

export interface ChamberForecastGenerateResponse {
  message: string;
  updated_at: string;
  model?: string;
  forecast: ChamberForecasts;
}
