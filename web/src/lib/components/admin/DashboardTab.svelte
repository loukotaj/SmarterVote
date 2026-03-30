<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import {
    ArcElement,
    CategoryScale,
    Chart as ChartJS,
    Legend,
    LinearScale,
    LineElement,
    PointElement,
    Title,
    Tooltip,
  } from "chart.js";
  import { Doughnut, Line } from "svelte-chartjs";
  import { analyticsService } from "$lib/services/analyticsService";
  import type { Alert, AnalyticsOverview } from "$lib/types";

  // Register Chart.js components once
  ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, ArcElement);

  export let onAlertCountChange: (n: number) => void = () => {};
  export let recentRuns: { run_id: string; status: string; payload?: Record<string, unknown>; started_at?: string }[] = [];

  const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";
  const GCP_PROJECT = import.meta.env.VITE_GCP_PROJECT || "";

  let overview: AnalyticsOverview | null = null;
  let alerts: Alert[] = [];
  let loading = true;
  let error = "";
  let refreshTimer: ReturnType<typeof setInterval> | null = null;

  // Derived chart data
  $: lineData = overview
    ? {
        labels: overview.timeseries.map((b) => b.time),
        datasets: [
          {
            label: "Requests",
            data: overview.timeseries.map((b) => b.requests),
            borderColor: "rgb(59, 130, 246)",
            backgroundColor: "rgba(59, 130, 246, 0.1)",
            tension: 0.3,
            fill: true,
            pointRadius: 2,
          },
        ],
      }
    : { labels: [], datasets: [] };

  $: lineOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { display: false }, ticks: { maxTicksLimit: 8, font: { size: 11 } } },
      y: { beginAtZero: true, ticks: { stepSize: 1, font: { size: 11 } } },
    },
  };

  // Separate race request tracking per race
  let raceRequests: { race_id: string; requests_24h: number }[] = [];

  $: donutData = raceRequests.length
    ? (() => {
        const top6 = raceRequests.slice(0, 6);
        const otherCount = raceRequests.slice(6).reduce((s, r) => s + r.requests_24h, 0);
        const labels = [...top6.map((r) => r.race_id), ...(otherCount > 0 ? ["Other"] : [])];
        const data = [...top6.map((r) => r.requests_24h), ...(otherCount > 0 ? [otherCount] : [])];
        const colors = ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#6B7280"];
        return {
          labels,
          datasets: [{ data, backgroundColor: colors.slice(0, data.length), borderWidth: 2 }],
        };
      })()
    : { labels: [], datasets: [] };

  $: donutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: "bottom" as const, labels: { font: { size: 11 }, boxWidth: 12 } } },
  };

  $: unacknowledgedAlerts = alerts.filter((a) => !a.acknowledged);
  $: {
    onAlertCountChange(unacknowledgedAlerts.length);
  }

  async function loadData() {
    try {
      error = "";
      const [overviewRes, alertsRes, racesRes] = await Promise.allSettled([
        analyticsService.getOverview(24),
        analyticsService.getAlerts(),
        analyticsService.getRaces(24),
      ]);

      if (overviewRes.status === "fulfilled") overview = overviewRes.value;
      if (alertsRes.status === "fulfilled") alerts = alertsRes.value.alerts;
      if (racesRes.status === "fulfilled") raceRequests = racesRes.value.races;
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  async function handleAcknowledge(alertId: string) {
    await analyticsService.acknowledgeAlert(alertId);
    alerts = alerts.map((a) => (a.id === alertId ? { ...a, acknowledged: true } : a));
  }

  const gcpLogsUrl = GCP_PROJECT
    ? `https://console.cloud.google.com/logs/query;query=resource.type%3D%22cloud_run_revision%22?project=${GCP_PROJECT}`
    : null;

  onMount(() => {
    loadData();
    refreshTimer = setInterval(loadData, 60_000);
  });

  onDestroy(() => {
    if (refreshTimer) clearInterval(refreshTimer);
  });

  function severityClass(s: string) {
    return s === "critical"
      ? "bg-red-50 border-red-200 text-red-800"
      : s === "warning"
        ? "bg-yellow-50 border-yellow-200 text-yellow-800"
        : "bg-blue-50 border-blue-200 text-blue-800";
  }

  function severityBadge(s: string) {
    return s === "critical"
      ? "bg-red-500 text-white"
      : s === "warning"
        ? "bg-yellow-500 text-white"
        : "bg-blue-500 text-white";
  }

  function formatDate(s?: string) {
    if (!s) return "—";
    return new Date(s).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  }
</script>

{#if loading}
  <div class="flex items-center justify-center py-16">
    <div class="flex items-center space-x-3 text-gray-500">
      <svg class="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path
          class="opacity-75"
          fill="currentColor"
          d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
      <span>Loading dashboard…</span>
    </div>
  </div>
{:else}
  <!-- Stat cards -->
  <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
    <div class="card p-4">
      <p class="text-xs font-medium text-gray-500 uppercase tracking-wide">Requests (24h)</p>
      <p class="mt-1 text-2xl font-bold text-gray-900">{(overview?.total_requests ?? 0).toLocaleString()}</p>
    </div>
    <div class="card p-4">
      <p class="text-xs font-medium text-gray-500 uppercase tracking-wide">Unique Visitors</p>
      <p class="mt-1 text-2xl font-bold text-gray-900">{(overview?.unique_visitors ?? 0).toLocaleString()}</p>
    </div>
    <div class="card p-4">
      <p class="text-xs font-medium text-gray-500 uppercase tracking-wide">Avg Latency</p>
      <p class="mt-1 text-2xl font-bold text-gray-900">{overview?.avg_latency_ms ?? 0}<span class="text-sm font-normal text-gray-500 ml-1">ms</span></p>
    </div>
    <div class="card p-4">
      <p class="text-xs font-medium text-gray-500 uppercase tracking-wide">Error Rate</p>
      <p class="mt-1 text-2xl font-bold {(overview?.error_rate ?? 0) > 5 ? 'text-red-600' : 'text-gray-900'}">
        {overview?.error_rate ?? 0}%
      </p>
    </div>
  </div>

  <!-- Charts row -->
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
    <!-- Requests over time -->
    <div class="card p-4 lg:col-span-2">
      <h3 class="text-sm font-semibold text-gray-700 mb-3">Requests per Hour (24h)</h3>
      {#if (overview?.timeseries?.length ?? 0) > 0}
        <div class="h-40">
          <Line data={lineData} options={lineOptions} />
        </div>
      {:else}
        <div class="h-40 flex items-center justify-center text-gray-400 text-sm">No data yet</div>
      {/if}
    </div>
    <!-- By race -->
    <div class="card p-4">
      <h3 class="text-sm font-semibold text-gray-700 mb-3">Requests by Race (24h)</h3>
      {#if raceRequests.length > 0}
        <div class="h-40">
          <Doughnut data={donutData} options={donutOptions} />
        </div>
      {:else}
        <div class="h-40 flex items-center justify-center text-gray-400 text-sm">No data yet</div>
      {/if}
    </div>
  </div>

  <!-- Alerts + Recent Runs row -->
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
    <!-- Alerts panel -->
    <div class="card p-4">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-semibold text-gray-700">Alerts</h3>
        <div class="flex items-center space-x-2">
          {#if unacknowledgedAlerts.length > 0}
            <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold bg-red-500 text-white">
              {unacknowledgedAlerts.length} active
            </span>
          {/if}
          <button
            type="button"
            class="text-xs text-blue-600 hover:underline"
            on:click={loadData}
          >Refresh</button>
        </div>
      </div>

      {#if error}
        <p class="text-xs text-red-500">{error}</p>
      {:else if alerts.filter((a) => !a.acknowledged).length === 0}
        <p class="text-sm text-gray-400 py-4 text-center">No active alerts ✓</p>
      {:else}
        <div class="space-y-2 max-h-64 overflow-y-auto pr-1">
          {#each alerts.filter((a) => !a.acknowledged) as alert (alert.id)}
            <div class="rounded-lg border px-3 py-2 {severityClass(alert.severity)}">
              <div class="flex items-start justify-between gap-2">
                <div class="flex-1 min-w-0">
                  <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-bold mr-1.5 {severityBadge(alert.severity)}">
                    {alert.severity}
                  </span>
                  <span class="text-xs">{alert.message}</span>
                </div>
                <button
                  type="button"
                  class="shrink-0 text-xs underline opacity-70 hover:opacity-100"
                  on:click={() => handleAcknowledge(alert.id)}
                >Ack</button>
              </div>
            </div>
          {/each}
        </div>
      {/if}

      {#if gcpLogsUrl}
        <a href={gcpLogsUrl} target="_blank" rel="noopener noreferrer" class="mt-3 inline-flex items-center text-xs text-blue-600 hover:underline">
          View logs in GCP Console →
        </a>
      {/if}
    </div>

    <!-- Recent pipeline runs -->
    <div class="card p-4">
      <h3 class="text-sm font-semibold text-gray-700 mb-3">Recent Pipeline Runs</h3>
      {#if recentRuns.length === 0}
        <p class="text-sm text-gray-400 py-4 text-center">No recent runs</p>
      {:else}
        <div class="space-y-1 max-h-64 overflow-y-auto">
          {#each recentRuns.slice(0, 10) as run (run.run_id)}
            {@const race_id = run.payload?.race_id ?? "—"}
            <div class="flex items-center justify-between text-xs py-1 border-b border-gray-100 last:border-0">
              <span class="font-mono text-gray-700 truncate max-w-40">{race_id}</span>
              <div class="flex items-center space-x-2 shrink-0">
                <span
                  class="px-1.5 py-0.5 rounded text-xs font-medium
                    {run.status === 'completed' ? 'bg-green-100 text-green-700' : run.status === 'failed' ? 'bg-red-100 text-red-700' : run.status === 'running' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600'}"
                >
                  {run.status}
                </span>
                <span class="text-gray-400">{formatDate(run.started_at)}</span>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </div>
{/if}
