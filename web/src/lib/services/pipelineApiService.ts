/**
 * Pipeline API service for handling server communication
 */
import { fetchWithAuth } from "$lib/stores/apiStore";
import type { RunInfo, Artifact, RunOptions, RunHistoryItem, RaceRecord } from "$lib/types";

interface RunsResponse {
  runs: RunInfo[];
}

interface ArtifactsResponse {
  items: Artifact[];
}

export interface PublishedRaceSummary {
  id: string;
  title?: string;
  office?: string;
  jurisdiction?: string;
  election_date: string;
  updated_utc: string;
  candidates: { name: string; party?: string }[];
  agent_metrics?: { estimated_usd?: number; model?: string; total_tokens?: number } | null;
}

interface PublishedRacesResponse {
  races: PublishedRaceSummary[];
}

export interface QueueItem {
  id: string;
  race_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  options: Record<string, unknown>;
  run_id?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
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

export class PipelineApiService {
  constructor(private apiBase: string) {}

  /**
   * Load artifacts
   */
  async loadArtifacts(): Promise<Artifact[]> {
    const res = await fetchWithAuth(`${this.apiBase}/artifacts`, {}, 15000);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const data: ArtifactsResponse = await res.json();
    return data.items || [];
  }

  /**
   * Load run history
   */
  async loadRunHistory(): Promise<RunHistoryItem[]> {
    const res = await fetchWithAuth(`${this.apiBase}/runs`, {}, 10000);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const data: RunsResponse = await res.json();
    const runs = data.runs || [];

    return runs.map((r: RunInfo, idx: number) => {
      // Find the currently running step, or the last completed step
      const runningStep = r.steps?.find((s) => s.status === "running");
      const completedSteps = r.steps?.filter((s) => s.status === "completed") ?? [];
      const lastStep = runningStep?.name ?? completedSteps.at(-1)?.name ?? (r as any).step;
      return {
        ...(r as any),
        run_id: (r as any).run_id || (r as any).id || (r as any)._id,
        display_id: runs.length - idx,
        updated_at: (r as any).completed_at || (r as any).started_at,
        last_step: lastStep,
      } as RunHistoryItem;
    });
  }

  /**
   * Delete a run from history (or cancel if still active)
   */
  async deleteRun(runId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/runs/${encodeURIComponent(runId)}`,
      { method: "DELETE" },
      10000
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
    const res = await fetchWithAuth(`${this.apiBase}/run/${runId}`, {}, 15000);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Get artifact data
   */
  async getArtifact(artifactId: string): Promise<any> {
    const res = await fetchWithAuth(
      `${this.apiBase}/artifact/${artifactId}`,
      {},
      20000
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Load published race summaries
   */
  async loadPublishedRaces(): Promise<PublishedRaceSummary[]> {
    const res = await fetchWithAuth(`${this.apiBase}/races`, {}, 10000);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const data: PublishedRacesResponse = await res.json();
    return data.races || [];
  }

  /**
   * Run the agent pipeline for a race
   */
  async runAgent(
    raceId: string,
    options: RunOptions = {}
  ): Promise<{ run_id: string; status: string; step: string }> {
    const res = await fetchWithAuth(`${this.apiBase}/api/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ race_id: raceId, options }),
    });

    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }

    return await res.json();
  }

  /**
   * Get full published race data (for export/download)
   */
  async getPublishedRace(raceId: string): Promise<Record<string, unknown>> {
    const res = await fetchWithAuth(
      `${this.apiBase}/races/${encodeURIComponent(raceId)}`,
      {},
      15000
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Delete a published race
   */
  async deletePublishedRace(raceId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/races/${encodeURIComponent(raceId)}`,
      { method: "DELETE" },
      15000
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
    const res = await fetchWithAuth(`${this.apiBase}/drafts`, {}, 10000);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const data: PublishedRacesResponse = await res.json();
    return data.races || [];
  }

  /**
   * Get full draft race data (for preview)
   */
  async getDraftRace(raceId: string): Promise<Record<string, unknown>> {
    const res = await fetchWithAuth(
      `${this.apiBase}/drafts/${encodeURIComponent(raceId)}`,
      {},
      15000
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Publish a draft race (copy from drafts/ to races/)
   */
  async publishDraft(raceId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/drafts/${encodeURIComponent(raceId)}/publish`,
      { method: "POST" },
      15000
    );
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
  }

  /**
   * Unpublish a race (remove from published, keep draft)
   */
  async unpublishRace(raceId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/races/${encodeURIComponent(raceId)}/unpublish`,
      { method: "POST" },
      15000
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
      `${this.apiBase}/drafts/${encodeURIComponent(raceId)}`,
      { method: "DELETE" },
      15000
    );
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
  }

  // -- Queue API ----------------------------------------------------------

  /**
   * Get current queue state
   */
  async loadQueue(): Promise<QueueResponse> {
    const res = await fetchWithAuth(`${this.apiBase}/queue`, {}, 10000);
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
    const res = await fetchWithAuth(`${this.apiBase}/queue`, {
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
   * Remove or cancel a queue item
   */
  async removeQueueItem(itemId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/queue/${encodeURIComponent(itemId)}`,
      { method: "DELETE" },
      10000
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }

  /**
   * Clear completed/failed items from queue
   */
  async clearFinishedQueue(): Promise<{ removed: number }> {
    const res = await fetchWithAuth(`${this.apiBase}/queue/finished`, {
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
    const res = await fetchWithAuth(`${this.apiBase}/api/races`, {}, 15000);
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
      10000
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
      15000
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
      10000
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
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
      15000
    );
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${res.status}: ${res.statusText}. ${errorText}`);
    }
  }

  /**
   * Unpublish a race
   */
  async unpublishRaceRecord(raceId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/unpublish`,
      { method: "POST" },
      15000
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
      10000
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const data: RaceRunsResponse = await res.json();
    return data.runs || [];
  }

  /**
   * Get run details for a specific race
   */
  async getRaceRun(raceId: string, runId: string): Promise<RunInfo> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/runs/${encodeURIComponent(runId)}`,
      {},
      15000
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

  /**
   * Delete or cancel a run for a specific race
   */
  async deleteRaceRun(raceId: string, runId: string): Promise<void> {
    const res = await fetchWithAuth(
      `${this.apiBase}/api/races/${encodeURIComponent(raceId)}/runs/${encodeURIComponent(runId)}`,
      { method: "DELETE" },
      10000
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
      15000
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  }

}
