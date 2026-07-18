<script lang="ts">
  import { browser } from "$app/environment";
  import { onDestroy, onMount } from "svelte";
  import AdminTabs from "$lib/components/admin/AdminTabs.svelte";
  import DashboardTab from "$lib/components/admin/DashboardTab.svelte";
  import RacesTab from "$lib/components/admin/RacesTab.svelte";
  import RunsTab from "$lib/components/admin/RunsTab.svelte";
  import type { RunHistoryItem } from "$lib/types";
  import { initializeAuth } from "$lib/stores/apiStore";
  import {
    PipelineApiService,
    type QueueItem,
  } from "$lib/services/pipelineApiService";
  import { racesApiBase } from "$lib/config/api";

  const API_BASE = racesApiBase();

  let apiService: PipelineApiService;
  let activeTab:
    | "dashboard"
    | "races"
    | "runs"
    | "forecasts"
    | "costs"
    | "agent" = "dashboard";
  let queueItems: QueueItem[] = [];
  let runs: RunHistoryItem[] = [];
  let isRefreshingRuns = false;
  let isPruningRuns = false;
  let connected = false;
  let queueTimer: ReturnType<typeof setInterval> | null = null;
  let cancellingItemId: string | null = null;
  let racesTab: RacesTab | null = null;
  let authError = "";
  let ForecastsTabComponent:
    | typeof import("$lib/components/admin/ForecastsTab.svelte").default
    | null = null;
  let CostsTabComponent:
    | typeof import("$lib/components/admin/CostsTab.svelte").default
    | null = null;
  let AgentTabComponent:
    | typeof import("$lib/components/admin/DurableAdminAgentTab.svelte").default
    | null = null;

  $: if (activeTab === "forecasts" && !ForecastsTabComponent) {
    void import("$lib/components/admin/ForecastsTab.svelte").then(
      (module) => (ForecastsTabComponent = module.default),
    );
  }
  $: if (activeTab === "costs" && !CostsTabComponent) {
    void import("$lib/components/admin/CostsTab.svelte").then(
      (module) => (CostsTabComponent = module.default),
    );
  }
  $: if (activeTab === "agent" && !AgentTabComponent) {
    void import("$lib/components/admin/DurableAdminAgentTab.svelte").then(
      (module) => (AgentTabComponent = module.default),
    );
  }

  $: if (activeTab === "runs" && apiService) {
    void refreshRuns();
  }

  $: activeQueueItems = queueItems.filter(
    (item) => item.status === "running" || item.status === "pending",
  );
  $: runningItems = activeQueueItems.filter(
    (item) => item.status === "running",
  );
  $: pendingItems = activeQueueItems.filter(
    (item) => item.status === "pending",
  );
  $: oldestPendingMs = Math.max(
    0,
    ...pendingItems.map((item) => {
      const created = item.created_at ? Date.parse(item.created_at) : NaN;
      return Number.isFinite(created) ? Date.now() - created : 0;
    }),
  );
  $: queueLikelyStalled =
    pendingItems.length > 0 &&
    runningItems.length === 0 &&
    oldestPendingMs >= 180000;

  let pollingIntervalMs = 0;

  function startOrUpdatePolling(activeItemsCount: number, currentTab: string) {
    let newIntervalMs = 0;
    if (activeItemsCount > 0) {
      newIntervalMs = 12000;
    } else if (
      currentTab === "dashboard" ||
      currentTab === "races" ||
      currentTab === "runs"
    ) {
      newIntervalMs = 30000;
    } else {
      newIntervalMs = 0;
    }

    if (newIntervalMs === pollingIntervalMs) {
      return;
    }

    pollingIntervalMs = newIntervalMs;
    if (queueTimer) {
      clearInterval(queueTimer);
      queueTimer = null;
    }

    if (pollingIntervalMs > 0) {
      queueTimer = setInterval(() => {
        if (!document.hidden) void refreshOperationalState();
      }, pollingIntervalMs);
    }
  }

  $: if (browser && apiService) {
    startOrUpdatePolling(activeQueueItems.length, activeTab);
  }

  onMount(async () => {
    if (!browser) return;
    try {
      await initializeAuth();
      apiService = new PipelineApiService(API_BASE);
    } catch (err) {
      authError =
        err instanceof Error
          ? err.message
          : "Unable to initialize admin authentication.";
      return;
    }

    const params = new URLSearchParams(window.location.search);
    const tabParam = params.get("tab");
    if (
      tabParam === "agent" ||
      tabParam === "races" ||
      tabParam === "runs" ||
      tabParam === "forecasts" ||
      tabParam === "costs"
    ) {
      activeTab = tabParam;
    } else {
      activeTab = "dashboard";
    }

    await refreshQueue();
    await refreshRuns();
  });

  onDestroy(() => {
    if (queueTimer) clearInterval(queueTimer);
  });

  async function refreshQueue() {
    if (!apiService) return;
    try {
      const result = await apiService.loadQueue();
      queueItems = result.items;
      connected = true;
    } catch {
      connected = false;
    }
  }

  async function refreshOperationalState() {
    const refreshes: Promise<void>[] = [refreshQueue()];
    if (activeTab === "runs") {
      refreshes.push(refreshRuns());
    } else if (activeTab === "races" && racesTab) {
      refreshes.push(racesTab.refresh(false));
    }
    await Promise.allSettled(refreshes);
  }

  async function refreshAllAdminState() {
    await Promise.allSettled([
      refreshQueue(),
      refreshRuns(),
      racesTab?.refresh(false) ?? Promise.resolve(),
    ]);
  }

  async function cancelQueueItem(item: QueueItem) {
    if (!confirm(`Cancel ${item.race_id || item.run_id || "this queue item"}?`))
      return;
    cancellingItemId = item.id;
    try {
      await apiService.removeQueueItem(item.id);
    } catch {
      await apiService.removeQueueItem(item.id, true);
    } finally {
      cancellingItemId = null;
      await refreshQueue();
    }
  }

  async function refreshRuns() {
    if (!apiService || isRefreshingRuns) return;
    isRefreshingRuns = true;
    try {
      runs = await apiService.loadRunHistory();
    } catch (err) {
      console.error("Failed to load runs history:", err);
    } finally {
      isRefreshingRuns = false;
    }
  }

  async function pruneCompletedRuns() {
    if (!apiService) return;
    isPruningRuns = true;
    try {
      await apiService.pruneRuns();
      await refreshRuns();
    } catch (err) {
      alert("Failed to prune runs: " + err);
    } finally {
      isPruningRuns = false;
    }
  }

  async function handleClearQueue() {
    try {
      await apiService.clearPendingQueue();
      await refreshQueue();
    } catch (err) {
      alert("Failed to clear queue: " + err);
    }
  }
</script>

<svelte:head>
  <title>Admin Console - SmarterVote</title>
  <meta name="robots" content="noindex,nofollow" />
</svelte:head>

{#if authError}
  <div class="mx-auto mt-16 max-w-xl px-4">
    <div
      class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800"
      role="alert"
    >
      <p class="font-semibold">Admin authentication failed</p>
      <p class="mt-1">{authError}</p>
    </div>
  </div>
{:else}
  <div class="w-full max-w-[1600px] mx-auto px-4 py-6">
    <div class="mt-2 mb-6 card p-4">
      <div class="flex items-center justify-between gap-4">
        <div>
          <h1 class="text-xl font-bold text-content">Admin Console</h1>
          <p class="text-sm text-content-subtle">
            Operations dashboard and deployed agent
          </p>
        </div>
        <div class="flex items-center gap-3 text-sm text-content-muted">
          <button
            type="button"
            class="rounded border border-stroke px-3 py-1.5 text-xs font-medium text-content hover:bg-surface-alt disabled:opacity-50"
            disabled={!apiService}
            on:click={refreshAllAdminState}
          >
            Refresh all
          </button>
          <div class="flex items-center gap-2">
            <span
              class="w-2.5 h-2.5 rounded-full {connected
                ? 'bg-green-500'
                : 'bg-red-500'}"
            ></span>
            {connected ? "Connected" : "Disconnected"}
          </div>
        </div>
      </div>
    </div>

    <AdminTabs bind:activeTab />

    {#if activeQueueItems.length > 0}
      <div
        class="mb-4 card border-blue-200 bg-blue-50 dark:bg-blue-900/20 overflow-hidden"
      >
        <div
          class="px-4 py-3 border-b border-blue-200 dark:border-blue-800 flex items-center justify-between"
        >
          <p class="text-sm font-semibold text-blue-900 dark:text-blue-100">
            {runningItems.length} running, {pendingItems.length} queued
          </p>
          <button
            type="button"
            class="text-xs text-blue-700 hover:underline"
            on:click={refreshQueue}>Refresh</button
          >
        </div>
        <div class="divide-y divide-blue-100 dark:divide-blue-900/40">
          {#each activeQueueItems as item (item.id)}
            <div class="px-4 py-2.5 flex items-center gap-3">
              <div class="flex-1 min-w-0">
                <span
                  class="block font-mono text-sm text-blue-900 dark:text-blue-100 truncate"
                  >{item.race_id || item.run_id}</span
                >
                <span
                  class="block text-xs text-blue-700 dark:text-blue-300 capitalize"
                  >{item.status}</span
                >
              </div>
              <button
                type="button"
                class="text-xs text-red-600 hover:underline disabled:opacity-50"
                disabled={cancellingItemId === item.id}
                on:click={() => cancelQueueItem(item)}>Cancel</button
              >
            </div>
          {/each}
        </div>
      </div>
    {/if}

    {#if queueLikelyStalled}
      <div
        class="mb-4 card p-3 border-amber-300 bg-amber-50 dark:bg-amber-900/20"
      >
        <p class="text-sm font-medium text-amber-800 dark:text-amber-200">
          Queue appears stalled
        </p>
        <p class="text-xs text-amber-700 dark:text-amber-300 mt-1">
          {pendingItems.length} item{pendingItems.length === 1 ? "" : "s"} pending
          with no active runner for over three minutes.
        </p>
      </div>
    {/if}

    {#if activeTab === "dashboard"}
      <DashboardTab
        {apiService}
        on:view-runs={() => (activeTab = "runs")}
      />
    {:else if activeTab === "races" && apiService}
      <div class="card p-6">
        <RacesTab bind:this={racesTab} />
      </div>
    {:else if activeTab === "runs" && apiService}
      <RunsTab
        {apiService}
        {runs}
        {queueItems}
        isRefreshing={isRefreshingRuns}
        isPruning={isPruningRuns}
        on:refresh={refreshRuns}
        on:clear-queue={handleClearQueue}
        on:prune-runs={pruneCompletedRuns}
      />
    {:else if activeTab === "forecasts" && apiService}
      <div class="card p-6">
        {#if ForecastsTabComponent}
          <svelte:component this={ForecastsTabComponent} {apiService} />
        {/if}
      </div>
    {:else if activeTab === "costs"}
      {#if CostsTabComponent}
        <svelte:component this={CostsTabComponent} />
      {/if}
    {:else if activeTab === "agent" && apiService}
      {#if AgentTabComponent}
        <svelte:component this={AgentTabComponent} {apiService} />
      {/if}
    {/if}
  </div>
{/if}
