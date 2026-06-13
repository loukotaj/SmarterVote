/**
 * Pipeline API service for handling server communication
 */
import { fetchWithAuth } from "$lib/stores/apiStore";
import {
  API_TIMEOUT_SHORT,
  API_TIMEOUT_DEFAULT,
  API_TIMEOUT_ARTIFACT,
} from "$lib/config/constants";
import { PIPELINE_STEPS } from "$lib/types";
import type { RunInfo, RunOptions, RunHistoryItem, RaceRecord, RunStep } from "$lib/types";

export interface AdminChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AdminChatAction {
  type: string; // "queue_run"
  race_ids?: string[];
  options?: Record<string, unknown>;
  description?: string;
}

/** Lightweight race metadata returned alongside a chat action */
export interface AdminChatRaceRecord {
  race_id: string;
  title?: string;
  status: string;
  quality_grade?: string;
  freshness?: string;
  candidate_count: number;
  last_run_at?: string;
  last_run_status?: string;
  requests_24h: number;
  published_at?: string;
  draft_updated_at?: string;
  discovery_only?: boolean;
}

export interface AdminChatResponse {
  reply: string;
  action: AdminChatAction | null;
  race_records?: AdminChatRaceRecord[];
  question?: string | null;
  thinking_steps?: string[];
}

export interface AdminAgentMessage {
  message_id: string;
  conversation_id: string;
  task_id?: string | null;
  role: "user" | "assistant" | "tool";
  content: string;
  tool_call_id?: string | null;
  tool_name?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface AdminAgentTask {
  task_id: string;
  conversation_id: string;
  status: "queued" | "running" | "waiting_approval" | "completed" | "failed" | "cancelled" | "continued";
  iteration?: number;
  continuation_count?: number;
  approval_summary?: string | null;
  pending_tool_call?: { id: string; name: string; arguments: Record<string, unknown> } | null;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminAgentConversation {
  conversation: {
    conversation_id: string;
    title: string;
    status: string;
    created_at: string;
    updated_at: string;
  };
  messages: AdminAgentMessage[];
  tasks: AdminAgentTask[];
}

interface RunsResponse {
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
  candidates: { name: string; party?: string; incumbent?: boolean; image_url?: string }[];
  agent_metrics?: { estimated_usd?: number; model?: string; total_tokens?: number } | null;
}

interface PublishedRacesResponse {
  races: PublishedRaceSummary[];
}

export interface QueueItem {
  id: string;
  race_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled" | "continued";
  options: Record<string, unknown>;
  run_id?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
  parent_run_id?: string;
  is_continuation?: boolean;
}

interface QueueResponse {
  items: QueueItem[];
  running: boolean;
  pending: number;
}

interface QueueAddResponse {
  added: QueueItem[];
  errors: Array<{ race_id: string; error: string }>;
}

interface RaceListResponse {
  races: RaceRecord[];
}

interface RaceQueueResponse {
  added: RaceRecord[];
  errors: Array<{ race_id: string; error: string }>;
}

interface RaceRunsResponse {
  runs: RunInfo[];
  count: number;
}

export interface RaceVersion {
  filename: string;
  source: "draft" | "published" | string;
  archived_at: string | null;
  size_bytes: number;
}

export class PipelineApiService {
  constructor(private apiBase: string) {}

  private normalizeRun(raw: RunInfo | Record<string, unknown>): RunInfo {
    const r = raw as RunInfo & Record<string, unknown>;
    const runId = String(r.run_id || r.id || "");
    const payloadRaceId = (r.payload as Record<string, unknown> | undefined)?.race_id;
    const raceId = typeof r.race_id === "string"
      ? r.race_id
      : typeof payloadRaceId === "string"
        ? payloadRaceId
        : undefined;
    const options = r.options ?? {};
    const existingSteps = Array.isArray(r.steps) ? (r.steps as RunStep[]) : [];
    const enabledSteps = Array.isArray(options.enabled_steps) && options.enabled_steps.length
      ? options.enabled_steps
      : PIPELINE_STEPS.map((s) => s.id);
    const remainingSteps = Array.isArray(r.remaining_steps) ? r.remaining_steps.map(String) : undefined;
    const currentStep = typeof r.current_step === "string" ? r.current_step : undefined;
    const currentStepProgress = typeof r.current_step_progress === "number" ? r.current_step_progress : undefined;
    const status = (r.status || "pending") as RunInfo["status"];
    const steps = existingSteps.length
      ? existingSteps
      : PIPELINE_STEPS.map((step) => {
          const enabled = enabledSteps.includes(step.id);
          let stepStatus: RunStep["status"] = enabled ? "pending" : "skipped";
          if (enabled && remainingSteps && !remainingSteps.includes(step.id) && step.id !== currentStep) {
            stepStatus = "completed";
          }
          if (enabled && step.id === currentStep && (status === "running" || status === "pending")) {
            stepStatus = "running";
          }
          if (status === "completed" && enabled) {
            stepStatus = "completed";
          }
          return {
            name: step.id,
            label: step.label,
            weight: step.weight,
            status: stepStatus,
            progress_pct: enabled && step.id === currentStep ? currentStepProgress : undefined,
          };
        });

    return {
      ...(r as RunInfo),
      run_id: runId,
      race_id: raceId,
      status,
      payload: r.payload ?? (raceId ? { race_id: raceId } : {}),
      options,
      progress: typeof r.progress === "number" ? r.progress : undefined,
      progress_message: typeof r.progress_message === "string" ? r.progress_message : undefined,
      current_step: currentStep ?? null,
      current_step_progress: currentStepProgress,
      remaining_steps: remainingSteps,
      steps,
    };
  }

  /**
   * Load run history from Firestore (via /runs endpoint).
   * Firestore run docs have: run_id, race_id, status, progress, current_step,
   * started_at, completed_at, duration_ms, error, options — but NOT steps[] or logs[].
   */
  async loadRunHistory(): Promise<RunHistoryItem[]> {
    const res = await fetchWithAuth(`${this.apiBase}/runs`, {}, API_TIMEOUT_SHORT);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const data: RunsResponse = await res.json();
    const runs = data.runs || [];

    return runs.map((r: RunInfo, idx: number) => {
      const normalized = this.normalizeRun(r);
      return ({
        ...normalized,
        run_id: normalized.run_id,
        display_id: runs.length - idx,
        updated_at: normalized.completed_at || normalized.started_at,
      // Firestore runs expose current_step instead of a steps array.
        last_step: normalized.current_step ?? undefined,
      // Fields not present in Firestore run docs — supply safe defaults.
        steps: normalized.steps,
        payload: normalized.payload,
        progress: normalized.progress,
        progress_message: normalized.progress_message,
        current_step: normalized.current_step,
        current_step_progress: normalized.current_step_progress,
      } as RunHistoryItem);
    });
  }

  /**
   * Delete a run from history (or cancel if still active)
   */
  async deleteRun(runId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/runs/${encodeURIComponent(runId)}`,
      { method: "DELETE" },
      API_TIMEOUT_SHORT
    );
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
  }

  /**
   * Prune all finished runs from Firestore history.
   */
  async pruneRuns(): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/runs`,
      { method: "DELETE" },
      API_TIMEOUT_SHORT
    );
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
  }

  /**
   * Get run details
   */
  async getRunDetails(runId: string): Promise<RunInfo> {
    const res = await fetchWithAuth(`${this.apiBase}/runs/${encodeURIComponent(runId)}`, {}, API_TIMEOUT_DEFAULT);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return this.normalizeRun(await res.json());
  }

  /**
   * Load run logs from Firestore subcollection via /runs/{runId}/logs.
   * Pass `since` to only fetch entries after that index (incremental polling).
   */
  async getRunLogs(
    runId: string,
    since = 0
  ): Promise<{ logs: import("$lib/types").LogEntry[]; total: number }> {
    const res = await fetchWithAuth(
      `${this.apiBase}/runs/${encodeURIComponent(runId)}/logs?since=${since}`,
      {},
      API_TIMEOUT_SHORT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Load published race summaries
   */
  async loadPublishedRaces(): Promise<PublishedRaceSummary[]> {
    const res = await fetchWithAuth(`${this.apiBase}/races/summaries`, {}, API_TIMEOUT_SHORT);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Get full published race data (for export/download)
   */
  async getPublishedRace(raceId: string): Promise<Record<string, unknown>> {
    const res = await fetchWithAuth(
      `${this.apiBase}/races/${encodeURIComponent(raceId)}`,
      {},
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Delete a published race
   */
  async deletePublishedRace(raceId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/unpublish`,
      { method: "POST" },
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
  }

  // -- Drafts API ---------------------------------------------------------

  /**
   * Load draft race summaries
   */
  async loadDraftRaces(): Promise<PublishedRaceSummary[]> {
    const res = await fetchWithAuth(`${this.apiBase}/api/races/drafts`, {}, API_TIMEOUT_SHORT);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const data: PublishedRacesResponse = await res.json();
    return data.races || [];
  }

  /**
   * Get full draft race data (for preview)
   */
  async getDraftRace(raceId: string): Promise<Record<string, unknown>> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/data?draft=true`,
      {},
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Publish a draft race (copy from drafts/ to races/)
   */
  async publishDraft(raceId: string): Promise<void> {
    return this.publishRace(raceId);
  }

  /**
   * Unpublish a race (remove from published, keep draft)
   */
  async unpublishRace(raceId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/unpublish`,
      { method: "POST" },
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
  }

  /**
   * Delete a draft race
   */
  async deleteDraftRace(raceId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/draft`,
      { method: "DELETE" },
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      // Idempotent behavior: treat missing draft as already deleted.
      if (res.status === 404 && errorText.toLowerCase().includes("draft not found")) {
        return;
      }
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
  }

  // -- Queue API ----------------------------------------------------------

  /**
   * Get current queue state
   */
  async loadQueue(): Promise<QueueResponse> {
    const res = await fetchWithAuth(`${this.apiBase}/api/queue`, {}, API_TIMEOUT_SHORT);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Add races to the processing queue
   */
  async addToQueue(
    raceIds: string[],
    options: RunOptions = {}
  ): Promise<QueueAddResponse> {
    const res = await fetchWithAuth(`${this.apiBase}/api/races/queue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ race_ids: raceIds, options }),
    });
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
    return await res.json();
  }

  /**
   * Remove or cancel a queue item. If force=true, skip graceful cancel and force-remove.
   */
  async removeQueueItem(itemId: string, force = false): Promise<void> {
    const url = `${this.apiBase}/api/queue/${encodeURIComponent(itemId)}${force ? "?force=true" : ""}`;
    const res = await fetchWithAuth(url, { method: "DELETE" }, API_TIMEOUT_SHORT);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }

  /**
   * Clear completed/failed items from queue
   */
  async clearFinishedQueue(): Promise<{ removed: number }> {
    const res = await fetchWithAuth(`${this.apiBase}/api/queue/finished`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Clear all pending (not yet started) items from queue
   */
  async clearPendingQueue(): Promise<{ removed: number }> {
    const res = await fetchWithAuth(`${this.apiBase}/api/queue/pending`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  // -- Unified Race API (Phase 3) -----------------------------------------

  /**
   * List all race records (unified view)
   */
  async listRaces(): Promise<RaceRecord[]> {
    const res = await fetchWithAuth(`${this.apiBase}/api/races`, {}, API_TIMEOUT_DEFAULT);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const data: RaceListResponse = await res.json();
    return data.races || [];
  }

  /**
   * Get a single race record
   */
  async getRaceRecord(raceId: string): Promise<RaceRecord> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}`,
      {},
      API_TIMEOUT_SHORT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Delete a race record and all associated data
   */
  async deleteRaceRecord(raceId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}`,
      { method: "DELETE" },
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }

  /**
   * Queue races for pipeline processing (unified)
   */
  async queueRaces(
    raceIds: string[],
    options: RunOptions = {}
  ): Promise<RaceQueueResponse> {
    const res = await fetchWithAuth(`${this.apiBase}/api/races/queue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ race_ids: raceIds, options }),
    });
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
    return await res.json();
  }

  /**
   * Cancel a queued or running race
   */
  async cancelRace(raceId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/cancel`,
      { method: "POST" },
      API_TIMEOUT_SHORT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }

  /**
   * Recheck race status from storage (recover stuck 'running' races)
   */
  async recheckRace(raceId: string): Promise<{ race: import("$lib/types").RaceRecord }> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/recheck`,
      { method: "POST" },
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Recheck all race statuses from storage and clear stale active runs
   */
  async recheckAllRaces(): Promise<{ checked: number; updated: number; races: import("$lib/types").RaceRecord[] }> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/recheck`,
      { method: "POST" },
      API_TIMEOUT_ARTIFACT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Run pipeline for a single race (direct, not queued)
   */
  async runRace(
    raceId: string,
    options: RunOptions = {}
  ): Promise<{ run_id: string; status: string; race_id: string }> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/run`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(options),
      }
    );
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
    return await res.json();
  }

  /**
   * Publish a race (draft -> published)
   */
  async publishRace(raceId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/publish`,
      { method: "POST" },
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
  }

  /**
   * Batch publish multiple races at once
   */
  async batchPublishRaces(raceIds: string[]): Promise<{ published: string[]; errors: Array<{ race_id: string; error: string }> }> {
    const res = await fetchWithAuth(`${this.apiBase}/api/races/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ race_ids: raceIds }),
    }, API_TIMEOUT_ARTIFACT);
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
    return await res.json();
  }

  /**
   * Unpublish a race
   */
  async unpublishRaceRecord(raceId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/unpublish`,
      { method: "POST" },
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
  }

  /**
   * List runs for a specific race
   */
  async listRaceRuns(raceId: string, limit: number = 20): Promise<RunInfo[]> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/runs?limit=${limit}`,
      {},
      API_TIMEOUT_SHORT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const data: RaceRunsResponse = await res.json();
    return (data.runs || []).map((run) => this.normalizeRun(run));
  }

  /**
   * Get run details for a specific race
   */
  async getRaceRun(raceId: string, runId: string): Promise<RunInfo> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/runs/${encodeURIComponent(runId)}`,
      {},
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return this.normalizeRun(await res.json());
  }

  /**
   * Delete or cancel a run for a specific race
   */
  async deleteRaceRun(raceId: string, runId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/runs/${encodeURIComponent(runId)}`,
      { method: "DELETE" },
      API_TIMEOUT_SHORT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }

  /**
   * Get full race JSON data (published or draft)
   */
  async getRaceData(raceId: string, draft: boolean = false): Promise<Record<string, unknown>> {
    const params = draft ? "?draft=true" : "";
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/data${params}`,
      {},
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * List retired (archived) versions for a race
   */
  async listRaceVersions(raceId: string): Promise<RaceVersion[]> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/versions`,
      {},
      API_TIMEOUT_SHORT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const data: { versions: RaceVersion[]; count: number } = await res.json();
    return data.versions || [];
  }

  /**
   * Get JSON content of a specific retired version
   */
  async getRaceVersionData(raceId: string, filename: string): Promise<Record<string, unknown>> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/versions/${encodeURIComponent(filename)}`,
      {},
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Restore a retired version as the active draft
   */
  async restoreVersionAsDraft(raceId: string, filename: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/versions/${encodeURIComponent(filename)}/restore`,
      { method: "POST" },
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }

  // -- Admin chat ---------------------------------------------------------

  /**
   * Send a chat message to the admin AI assistant.
   * Returns the assistant reply and an optional action to confirm.
   */
  async adminChat(
    messages: AdminChatMessage[]
  ): Promise<AdminChatResponse> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/admin-chat`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages }),
      },
      60_000 // allow up to 60 s for LLM response
    );
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
    return await res.json();
  }

  async createAdminAgentConversation(): Promise<AdminAgentConversation["conversation"]> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/admin-agent/conversations`,
      { method: "POST", headers: { "Content-Type": "application/json" } },
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    return await res.json();
  }

  async getAdminAgentConversation(conversationId: string): Promise<AdminAgentConversation> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/admin-agent/conversations/${encodeURIComponent(conversationId)}`,
      {},
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    return await res.json();
  }

  async submitAdminAgentMessage(conversationId: string, content: string): Promise<AdminAgentTask> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/admin-agent/conversations/${encodeURIComponent(conversationId)}/messages`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      },
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    return await res.json();
  }

  async approveAdminAgentTask(taskId: string): Promise<AdminAgentTask> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/admin-agent/tasks/${encodeURIComponent(taskId)}/approve`,
      { method: "POST", headers: { "Content-Type": "application/json" } },
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    return await res.json();
  }

  async cancelAdminAgentTask(taskId: string): Promise<AdminAgentTask> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/admin-agent/tasks/${encodeURIComponent(taskId)}/cancel`,
      { method: "POST", headers: { "Content-Type": "application/json" } },
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    return await res.json();
  }

  async listAdminAgentConversations(): Promise<AdminAgentConversation["conversation"][]> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/admin-agent/conversations`,
      {},
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    const data = await res.json();
    return data.conversations || [];
  }

  async deleteAdminAgentConversation(conversationId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/admin-agent/conversations/${encodeURIComponent(conversationId)}`,
      { method: "DELETE" },
      API_TIMEOUT_DEFAULT
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }

}
