/**
 * Pipeline API service for handling server communication
 */
import { fetchWithAuth } from "$lib/stores/apiStore";
import type { RunInfo, Artifact, RunOptions, RunHistoryItem } from "$lib/types";

interface RunsResponse {
  runs: RunInfo[];
}

interface ArtifactsResponse {
  items: Artifact[];
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
      const lastStep = r.steps?.at(-1)?.name || (r as any).step;
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
}
