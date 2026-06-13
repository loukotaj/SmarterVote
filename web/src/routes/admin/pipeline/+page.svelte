<script lang="ts">
  import { browser } from "$app/environment";
  import { onDestroy, onMount } from "svelte";
  import AdminTabs from "$lib/components/admin/AdminTabs.svelte";
  import DashboardTab from "$lib/components/admin/DashboardTab.svelte";
  import DurableAdminAgentTab from "$lib/components/admin/DurableAdminAgentTab.svelte";
  import RacesTab from "$lib/components/admin/RacesTab.svelte";
  import RunsTab from "$lib/components/admin/RunsTab.svelte";
  import type { RunHistoryItem } from "$lib/types";
  import { initializeAuth } from "$lib/stores/apiStore";
  import { PipelineApiService, type QueueItem } from "$lib/services/pipelineApiService";

  const API_BASE = import.meta.env.VITE_RACES_API_URL || "http://127.0.0.1:8080";

  let apiService: PipelineApiService;
  let activeTab: "dashboard" | "races" | "runs" | "agent" = "dashboard";
  let alertBadgeCount = 0;
  let queueItems: QueueItem[] = [];
  let runs: RunHistoryItem[] = [];
  let isRefreshingRuns = false;
  let isPruningRuns = false;
  let connected = false;
  let queueTimer: ReturnType<typeof setInterval> | null = null;
  let cancellingItemId: string | null = null;

  $: if (activeTab === "runs" && apiService) {
    void refreshRuns();
  }

  $: activeQueueItems = queueItems.filter((item) => item.status === "running" || item.status === "pending");
  $: runningItems = activeQueueItems.filter((item) => item.status === "running");
  $: pendingItems = activeQueueItems.filter((item) => item.status === "pending");
  $: oldestPendingMs = Math.max(
    0,
    ...pendingItems.map((item) => {
      const created = item.created_at ? Date.parse(item.created_at) : NaN;
      return Number.isFinite(created) ? Date.now() - created : 0;
    })
  );
  $: queueLikelyStalled = pendingItems.length > 0 && runningItems.length === 0 && oldestPendingMs >= 180000;

  let pollingIntervalMs = 0;

  function startOrUpdatePolling(activeItemsCount: number, currentTab: string) {
    let newIntervalMs = 0;
    if (activeItemsCount > 0) {
      newIntervalMs = 12000;
    } else if (currentTab === "dashboard" || currentTab === "runs") {
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
        if (!document.hidden) void refreshQueue();
      }, pollingIntervalMs);
    }
  }

  $: if (browser && apiService) {
    startOrUpdatePolling(activeQueueItems.length, activeTab);
  }

  onMount(async () => {
    if (!browser) return;
    await initializeAuth();
    apiService = new PipelineApiService(API_BASE);

    const params = new URLSearchParams(window.location.search);
    const tabParam = params.get("tab");
    if (tabParam === "agent" || tabParam === "races" || tabParam === "runs") {
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

  async function cancelQueueItem(item: QueueItem) {
    if (!confirm(`Cancel ${item.race_id || item.run_id || "this queue item"}?`)) return;
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
    if (!apiService) return;
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
</svelte:head>

<div class="w-full max-w-[1600px] mx-auto px-4 py-6">
  <div class="mt-2 mb-6 card p-4">
    <div class="flex items-center justify-between gap-4">
      <div>
        <h1 class="text-xl font-bold text-content">Admin Console</h1>
        <p class="text-sm text-content-subtle">Operations dashboard and deployed agent</p>
      </div>
      <div class="flex items-center gap-2 text-sm text-content-muted">
        <span class="w-2.5 h-2.5 rounded-full {connected ? 'bg-green-500' : 'bg-red-500'}"></span>
        {connected ? "Connected" : "Disconnected"}
      </div>
    </div>
  </div>

  <AdminTabs bind:activeTab alertCount={alertBadgeCount} />

  {#if activeQueueItems.length > 0}
    <div class="mb-4 card border-blue-200 bg-blue-50 dark:bg-blue-900/20 overflow-hidden">
      <div class="px-4 py-3 border-b border-blue-200 dark:border-blue-800 flex items-center justify-between">
        <p class="text-sm font-semibold text-blue-900 dark:text-blue-100">
          {runningItems.length} running, {pendingItems.length} queued
        </p>
        <button type="button" class="text-xs text-blue-700 hover:underline" on:click={refreshQueue}>Refresh</button>
      </div>
      <div class="divide-y divide-blue-100 dark:divide-blue-900/40">
        {#each activeQueueItems as item (item.id)}
          <div class="px-4 py-2.5 flex items-center gap-3">
            <div class="flex-1 min-w-0">
              <span class="block font-mono text-sm text-blue-900 dark:text-blue-100 truncate">{item.race_id || item.run_id}</span>
              <span class="block text-xs text-blue-700 dark:text-blue-300 capitalize">{item.status}</span>
            </div>
            <button
              type="button"
              class="text-xs text-red-600 hover:underline disabled:opacity-50"
              disabled={cancellingItemId === item.id}
              on:click={() => cancelQueueItem(item)}
            >Cancel</button>
          </div>
        {/each}
      </div>
    </div>
  {/if}

  {#if queueLikelyStalled}
    <div class="mb-4 card p-3 border-amber-300 bg-amber-50 dark:bg-amber-900/20">
      <p class="text-sm font-medium text-amber-800 dark:text-amber-200">Queue appears stalled</p>
      <p class="text-xs text-amber-700 dark:text-amber-300 mt-1">
        {pendingItems.length} item{pendingItems.length === 1 ? "" : "s"} pending with no active runner for over three minutes.
      </p>
    </div>
  {/if}

  {#if activeTab === "dashboard"}
    <DashboardTab
      onAlertCountChange={(count) => (alertBadgeCount = count)}
      {apiService}
      on:view-runs={() => (activeTab = "runs")}
    />
  {:else if activeTab === "races" && apiService}
    <div class="card p-6">
      <RacesTab />
    </div>
  {:else if activeTab === "runs" && apiService}
    <RunsTab
      runs={runs}
      queueItems={queueItems}
      isRefreshing={isRefreshingRuns}
      isPruning={isPruningRuns}
      on:refresh={refreshRuns}
      on:clear-queue={handleClearQueue}
      on:prune-runs={pruneCompletedRuns}
    />
  {:else if activeTab === "agent" && apiService}
    <DurableAdminAgentTab {apiService} />
  {/if}
</div>
