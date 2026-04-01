<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher } from "svelte";
  import { PipelineApiService } from "$lib/services/pipelineApiService";
  import { formatDuration, getStatusClass, safeJsonStringify, downloadAsJson } from "$lib/utils/pipelineUtils";
  import type { RunInfo, RunStep, LogEntry } from "$lib/types";

  export let runId: string;
  export let isLive = false;
  export let liveLogs: LogEntry[] = [];
  export let liveProgress = 0;
  export let liveProgressMessage = "";
  export let liveElapsed = 0;

  const dispatch = createEventDispatcher<{ back: void }>();
  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";
  const apiService = new PipelineApiService(API_BASE);

  let run: RunInfo | null = null;
  let loading = true;
  let error = "";
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let showRawJson = false;
  type SectionId = "steps" | "logs" | "output";
  let activeSection: SectionId = "steps";
  let artifactData: any = null;
  let artifactLoading = false;
  type LogLevel = "all" | "info" | "warning" | "error";
  const LOG_LEVELS: LogLevel[] = ["all", "info", "warning", "error"];
  let logFilter: LogLevel = "all";

  $: raceId = (run?.payload?.race_id as string) ?? runId;
  // A run is only "live" if the backend actually reports it as running/pending.
  // Never show the live spinner for a run the server has already completed.
  $: isRunning = run?.status === "running" || run?.status === "pending";
  $: isLiveAndRunning = isLive && isRunning;
  // Use live logs while the run is active; once done fall back to stored logs
  // then to agent_logs embedded in the artifact (GCS blobs strip logs).
  $: artifactAgentLogs = (() => {
    const logs = artifactData?.output?.agent_logs;
    if (!Array.isArray(logs)) return [];
    return logs.map((l: any) => ({
      level: (l.level ?? "info").toLowerCase(),
      message: l.message ?? String(l),
      timestamp: l.timestamp ?? "",
    })) as LogEntry[];
  })();
  $: runLogs = isLiveAndRunning ? liveLogs : ((run?.logs ?? []).length > 0 ? (run?.logs ?? []) : artifactAgentLogs);
  $: filteredLogs = logFilter === "all" ? runLogs : runLogs.filter((l) => l.level === logFilter);
  $: steps = run?.steps ?? [];
  // Filter to only pipeline sub-steps (exclude the top-level "agent" step)
  $: pipelineSteps = steps.filter((s) => s.name !== "agent");
  $: hasPipelineSteps = pipelineSteps.length > 0;
  $: sections = [
    { id: "steps" as SectionId, label: `Steps (${pipelineSteps.length})` },
    { id: "logs" as SectionId, label: `Logs (${runLogs.length})` },
    { id: "output" as SectionId, label: "Output" },
  ];
  $: progress = isLiveAndRunning ? liveProgress : computeProgress(pipelineSteps);
  $: progressMsg = isLiveAndRunning ? liveProgressMessage : lastStepMessage(pipelineSteps);
  $: elapsed = isLiveAndRunning ? liveElapsed : (run?.duration_ms ? Math.floor(run.duration_ms / 1000) : 0);

  function computeProgress(steps: RunStep[]): number {
    if (!steps.length) return 0;
    // Weight-based progress: sum weights of completed steps / total enabled weight
    const enabled = steps.filter((s) => s.status !== "skipped");
    if (!enabled.length) return 100;
    const totalWeight = enabled.reduce((sum, s) => sum + (s.weight || 1), 0);
    let doneWeight = 0;
    let partialWeight = 0;
    for (const s of enabled) {
      const w = s.weight || 1;
      if (s.status === "completed") doneWeight += w;
      else if (s.status === "running") partialWeight += w * ((s.progress_pct || 0) / 100);
    }
    return Math.min(98, Math.round(((doneWeight + partialWeight) / totalWeight) * 100));
  }

  function lastStepMessage(steps: RunStep[]): string {
    const running = steps.find((s) => s.status === "running");
    if (running) return `Running: ${running.name}`;
    const last = [...steps].reverse().find((s) => s.status === "completed");
    if (last) return `Completed: ${last.name}`;
    return "";
  }

  function stepIcon(status: string): string {
    switch (status) {
      case "completed": return "✓";
      case "running": return "●";
      case "failed": return "✗";
      case "skipped": return "⊘";
      default: return "○";
    }
  }

  function stepColor(status: string): string {
    switch (status) {
      case "completed": return "text-green-600";
      case "running": return "text-blue-600";
      case "failed": return "text-red-600";
      case "skipped": return "text-content-faint opacity-50";
      default: return "text-content-faint";
    }
  }

  function statusBadge(status: string): string {
    switch (status) {
      case "completed": return "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300";
      case "running": return "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300";
      case "failed": return "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300";
      case "cancelled": return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300";
      case "skipped": return "bg-gray-100 text-gray-500 dark:bg-gray-800/30 dark:text-gray-500";
      case "pending": return "bg-surface-alt text-content-subtle";
      default: return "bg-surface-alt text-content-subtle";
    }
  }

  function formatTimestamp(iso?: string): string {
    if (!iso) return "—";
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  }

  function logLevelClass(level: string): string {
    switch (level) {
      case "error": return "text-red-600 dark:text-red-400";
      case "warning": return "text-yellow-600 dark:text-yellow-400";
      case "debug": return "text-content-faint";
      default: return "text-content-muted";
    }
  }

  function breakdownTokens(counts: unknown): number {
    const c = counts as { prompt_tokens?: number; completion_tokens?: number };
    return (c?.prompt_tokens ?? 0) + (c?.completion_tokens ?? 0);
  }

  async function loadRun() {
    try {
      error = "";
      run = await apiService.getRunDetails(runId);
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  async function loadArtifact() {
    if (!run?.artifact_id) return;
    artifactLoading = true;
    try {
      artifactData = await apiService.getArtifact(run.artifact_id);
    } catch (e) {
      artifactData = { error: String(e) };
    } finally {
      artifactLoading = false;
    }
  }

  onMount(async () => {
    await loadRun();
    if (isRunning) {
      pollTimer = setInterval(loadRun, 3000);
    } else if (run?.artifact_id) {
      // Auto-load artifact for completed runs so logs are available immediately
      loadArtifact();
    }
  });

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  // If the run finishes, stop polling and load artifact
  $: if (run && !isRunning && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
    if (run.artifact_id && !artifactData) loadArtifact();
  }
</script>

<div class="space-y-4">
  <!-- Back button + header -->
  <div class="flex items-center gap-3">
    <button
      type="button"
      class="p-1.5 rounded-lg hover:bg-surface-alt text-content-subtle hover:text-content-muted"
      on:click={() => dispatch("back")}
      title="Back to runs"
    >
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
      </svg>
    </button>
    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-3">
        <h2 class="text-lg font-bold text-content truncate">{raceId}</h2>
        {#if run}
          <span class="px-2.5 py-0.5 rounded-full text-xs font-semibold {statusBadge(run.status)}">
            {run.status}
          </span>
        {/if}
        {#if isLiveAndRunning}
          <span class="flex items-center gap-1 text-xs text-blue-600">
            <svg class="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            Live
          </span>
        {/if}
      </div>
      <div class="flex items-center gap-4 mt-0.5 text-xs text-content-subtle">
        <span>Run {runId.substring(0, 8)}</span>
        {#if run}
          <span>Started {formatTimestamp(run.started_at)}</span>
          {#if run.completed_at}
            <span>Finished {formatTimestamp(run.completed_at)}</span>
          {/if}
          {#if run.options?.research_model}
            <span class="font-mono">{run.options.research_model}</span>
          {/if}          {#if run.options?.note}
            <span class="italic text-content-faint">"{run.options.note}"</span>
          {/if}        {/if}
      </div>
    </div>
  </div>

  {#if loading}
    <div class="card p-8 text-center">
      <svg class="animate-spin h-6 w-6 mx-auto text-blue-500 mb-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
      </svg>
      <span class="text-sm text-content-subtle">Loading run details…</span>
    </div>
  {:else if error}
    <div class="card p-4 text-sm text-red-600">{error}</div>
  {:else if run}
    <!-- Progress bar -->
    <div class="card p-4">
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm text-content-muted font-medium">{progressMsg || "Waiting…"}</span>
        <div class="flex items-center gap-3 text-sm text-content-subtle">
          <span>{formatDuration(elapsed)}</span>
          <span class="font-semibold">{progress}%</span>
        </div>
      </div>
      <div class="w-full bg-stroke rounded-full h-2.5">
        <div
          class="h-2.5 rounded-full transition-all duration-700 ease-out {run.status === 'failed' ? 'bg-red-500' : run.status === 'completed' ? 'bg-green-500' : 'bg-blue-600'}"
          style="width: {progress}%"
        />
      </div>
      {#if run.error}
        <p class="mt-2 text-sm text-red-600">{run.error}</p>
      {/if}
    </div>

    <!-- Section tabs -->
    <div class="flex gap-1 border-b border-stroke">
      {#each sections as sec}
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium transition-colors {activeSection === sec.id ? 'border-b-2 border-blue-600 text-blue-700 dark:text-blue-400' : 'text-content-subtle hover:text-content-muted'}"
          on:click={() => (activeSection = sec.id)}
        >
          {sec.label}
        </button>
      {/each}
    </div>

    <!-- Steps section -->
    {#if activeSection === "steps"}
      <div class="card p-0">
        {#if pipelineSteps.length > 0}
          <div class="divide-y divide-stroke">
            {#each pipelineSteps as step, i}
              {@const isSkipped = step.status === "skipped"}
              <div class="flex items-center gap-3 px-4 py-3 {isSkipped ? 'opacity-50' : ''}">
                <!-- Step number + icon -->
                <div class="flex items-center gap-2 shrink-0 w-8">
                  <span class="text-lg {stepColor(step.status)}">{stepIcon(step.status)}</span>
                </div>

                <!-- Step info -->
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium text-content {isSkipped ? 'line-through' : ''}">{step.label || step.name}</span>
                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase {statusBadge(step.status)}">{step.status}</span>
                  </div>
                  {#if step.status === "running" && step.progress_pct}
                    <div class="mt-1.5 flex items-center gap-2">
                      <div class="flex-1 h-1.5 bg-surface-alt rounded-full overflow-hidden">
                        <div class="h-full bg-blue-500 rounded-full transition-all duration-300" style="width: {step.progress_pct}%"></div>
                      </div>
                      <span class="text-[10px] text-content-subtle shrink-0">{step.progress_pct}%</span>
                    </div>
                  {/if}
                </div>

                <!-- Duration -->
                <div class="shrink-0 text-right">
                  {#if step.duration_ms}
                    <span class="text-xs text-content-subtle">{formatDuration(step.duration_ms)}</span>
                  {:else if step.status === "running"}
                    <span class="text-xs text-blue-500 animate-pulse">running…</span>
                  {:else if isSkipped}
                    <span class="text-xs text-content-faint">skipped</span>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {:else}
          <div class="text-center text-content-faint py-8 text-sm">
            {#if isRunning}
              Waiting for step data…
            {:else}
              No step data available for this run
            {/if}
          </div>
        {/if}
      </div>
    {/if}

    <!-- Logs section -->
    {#if activeSection === "logs"}
      <div class="card p-0">
        <div class="px-4 py-2 border-b border-stroke flex items-center gap-2">
          <span class="text-xs font-medium text-content-subtle">Filter:</span>
          {#each LOG_LEVELS as level}
            <button
              type="button"
              class="px-2 py-0.5 rounded text-xs font-medium transition-colors {logFilter === level ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' : 'text-content-subtle hover:bg-surface-alt'}"
              on:click={() => (logFilter = level)}
            >{level}</button>
          {/each}
          <span class="ml-auto text-xs text-content-faint">{filteredLogs.length} entries</span>
        </div>
        <div class="max-h-96 overflow-y-auto font-mono text-xs p-3 space-y-0.5 bg-surface-alt">
          {#each filteredLogs as log}
            <div class="flex gap-2 leading-5">
              <span class="text-content-faint shrink-0 select-none">{log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : ""}</span>
              <span class="shrink-0 w-14 text-right font-semibold uppercase {logLevelClass(log.level)}">{log.level}</span>
              <span class="{logLevelClass(log.level)} break-all">{log.message}</span>
            </div>
          {:else}
            <div class="text-center text-content-faint py-6">No logs available</div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Output section -->
    {#if activeSection === "output"}
      <div class="card p-4">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold text-content-muted">
            {#if run.artifact_id}
              Artifact: <span class="font-mono text-content-subtle">{run.artifact_id}</span>
            {:else}
              Run Output
            {/if}
          </h3>
          <div class="flex items-center gap-2">
            {#if run.artifact_id && !artifactData}
              <button
                type="button"
                class="px-3 py-1 text-xs border border-stroke rounded-lg hover:bg-surface-alt disabled:opacity-40"
                disabled={artifactLoading}
                on:click={loadArtifact}
              >
                {artifactLoading ? "Loading…" : "Load Artifact"}
              </button>
            {/if}
            {#if artifactData}
              <button
                type="button"
                class="px-3 py-1 text-xs border border-stroke rounded-lg hover:bg-surface-alt"
                on:click={() => downloadAsJson(artifactData, `${raceId}-${runId.substring(0, 8)}.json`)}
              >
                Download JSON
              </button>
            {/if}
            <button
              type="button"
              class="px-3 py-1 text-xs border border-stroke rounded-lg hover:bg-surface-alt"
              on:click={() => (showRawJson = !showRawJson)}
            >
              {showRawJson ? "Parsed View" : "Raw JSON"}
            </button>
          </div>
        </div>

        {#if artifactData}
          {#if showRawJson}
            <pre class="bg-surface-alt rounded-lg p-3 text-xs font-mono overflow-auto max-h-[600px] whitespace-pre-wrap break-words text-content">{safeJsonStringify(artifactData).content}</pre>
          {:else}
            {@const d = artifactData}
            {#if typeof d === "object" && d !== null}
              <div class="space-y-4">
                <!-- Quick summary if it looks like RaceJSON -->
                {#if Array.isArray(d.candidates)}
                  {@const metrics = d.agent_metrics ?? d.output?.race_json?.agent_metrics ?? d.output?.agent_metrics ?? null}
                  <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <div class="bg-surface-alt rounded-lg p-3">
                      <p class="text-xs text-content-subtle">Race</p>
                      <p class="text-sm font-semibold text-content">{d.id ?? d.race_id ?? "—"}</p>
                    </div>
                    <div class="bg-surface-alt rounded-lg p-3">
                      <p class="text-xs text-content-subtle">Candidates</p>
                      <p class="text-sm font-semibold text-content">{d.candidates.length}</p>
                    </div>
                    <div class="bg-surface-alt rounded-lg p-3">
                      <p class="text-xs text-content-subtle">Office</p>
                      <p class="text-sm font-semibold text-content">{d.office ?? "—"}</p>
                    </div>
                    <div class="bg-surface-alt rounded-lg p-3">
                      <p class="text-xs text-content-subtle">Updated</p>
                      <p class="text-sm font-semibold text-content">{d.updated_utc ? new Date(d.updated_utc).toLocaleDateString() : "—"}</p>
                    </div>
                  </div>
                  {#if metrics}
                    <!-- Agent metrics card -->
                    <div class="border border-stroke rounded-lg p-4 bg-surface-alt">
                      <h4 class="text-xs font-semibold text-content-subtle uppercase tracking-wide mb-3">Agent Metrics</h4>
                      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                        <div>
                          <p class="text-xs text-content-faint">Total Tokens</p>
                          <p class="text-sm font-semibold text-content">{(metrics.total_tokens ?? 0).toLocaleString()}</p>
                        </div>
                        <div>
                          <p class="text-xs text-content-faint">Est. Cost</p>
                          <p class="text-sm font-semibold text-content">{metrics.estimated_usd != null ? (metrics.estimated_usd < 0.001 ? '<$0.001' : `$${metrics.estimated_usd.toFixed(4)}`) : '—'}</p>
                        </div>
                        <div>
                          <p class="text-xs text-content-faint">Duration</p>
                          <p class="text-sm font-semibold text-content">{metrics.duration_s != null ? `${Math.round(metrics.duration_s)}s` : '—'}</p>
                        </div>
                        <div>
                          <p class="text-xs text-content-faint">Primary Model</p>
                          <p class="text-sm font-semibold text-content truncate">{metrics.model ?? '—'}</p>
                        </div>
                      </div>
                      {#if metrics.model_breakdown && Object.keys(metrics.model_breakdown).length > 1}
                        <div class="border-t border-stroke pt-2">
                          <p class="text-xs text-content-faint mb-1.5">Model Breakdown</p>
                          <div class="space-y-1">
                            {#each Object.entries(metrics.model_breakdown) as [model, counts]}
                              <div class="flex items-center justify-between text-xs">
                                <span class="font-mono text-content-muted truncate max-w-48">{model}</span>
                                <span class="text-content-subtle shrink-0 ml-2">{breakdownTokens(counts).toLocaleString()} tok</span>
                              </div>
                            {/each}
                          </div>
                        </div>
                      {/if}
                    </div>
                  {/if}
                  <!-- Candidate cards -->
                  {#each d.candidates as candidate}
                    <div class="border border-stroke rounded-lg p-4">
                      <div class="flex items-center gap-3 mb-2">
                        <h4 class="text-sm font-bold text-content">{candidate.name}</h4>
                        {#if candidate.party}
                          <span class="text-xs px-2 py-0.5 rounded-full {candidate.party === 'Democratic' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' : candidate.party === 'Republican' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' : 'bg-surface-alt text-content-muted'}">{candidate.party}</span>
                        {/if}
                        {#if candidate.incumbent}
                          <span class="text-xs text-content-subtle">Incumbent</span>
                        {/if}
                      </div>
                      {#if candidate.summary}
                        <p class="text-xs text-content-muted mb-2 line-clamp-2">{candidate.summary}</p>
                      {/if}
                      {#if candidate.issues && typeof candidate.issues === "object"}
                        <div class="flex flex-wrap gap-1">
                          {#each Object.keys(candidate.issues) as issue}
                            <span class="text-xs px-2 py-0.5 rounded bg-surface-alt text-content-muted">{issue}</span>
                          {/each}
                        </div>
                      {/if}
                    </div>
                  {/each}
                {:else}
                  <!-- Generic object display -->
                  <pre class="bg-surface-alt rounded-lg p-3 text-xs font-mono overflow-auto max-h-[600px] whitespace-pre-wrap break-words text-content">{safeJsonStringify(d).content}</pre>
                {/if}
              </div>
            {:else}
              <p class="text-sm text-content-subtle">No structured output available</p>
            {/if}
          {/if}
        {:else if isLiveAndRunning}
          <div class="flex items-center gap-2 p-6 text-content-faint justify-center">
            <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <span class="text-sm">Output available when run completes…</span>
          </div>
        {:else}
          <p class="text-sm text-content-faint py-4 text-center">
            {run.artifact_id ? "Click \"Load Artifact\" to view output" : "No output recorded for this run"}
          </p>
        {/if}
      </div>
    {/if}
  {/if}
</div>
