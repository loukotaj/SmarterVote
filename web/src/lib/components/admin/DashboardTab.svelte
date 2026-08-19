<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import {
    ArcElement,
    CategoryScale,
    Chart as ChartJS,
    Filler,
    Legend,
    LinearScale,
    LineElement,
    PointElement,
    Title,
    Tooltip,
  } from "chart.js";
  import { Doughnut, Line } from "svelte-chartjs";
  import { analyticsService } from "$lib/services/analyticsService";
  import { PipelineApiService } from "$lib/services/pipelineApiService";
  import type { AnalyticsOverview, TrafficAnalytics } from "$lib/types";
  import type { RaceRecord } from "$lib/types";

  // Register Chart.js components once
  ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    ArcElement,
    Filler,
  );

  export let apiService: PipelineApiService | undefined = undefined;

  const GCP_PROJECT = import.meta.env.VITE_GCP_PROJECT || "";

  let overview: AnalyticsOverview | null = null;
  let traffic: TrafficAnalytics | null = null;
  let loading = true;
  let error = "";
  let refreshTimer: ReturnType<typeof setInterval> | null = null;
  let refreshInFlight: Promise<void> | null = null;

  const TIME_RANGES = [
    { label: "1h", value: 1 },
    { label: "6h", value: 6 },
    { label: "24h", value: 24 },
    { label: "7d", value: 168 },
    { label: "30d", value: 720 },
  ];
  let selectedHours = 24;
  $: rangeLabel =
    TIME_RANGES.find((r) => r.value === selectedHours)?.label ??
    `${selectedHours}h`;

  // Derived chart data
  $: lineData = traffic
    ? {
        labels: traffic.timeseries.map((b) => formatTrafficTime(b.time)),
        datasets: [
          {
            label: "Page views",
            data: traffic.timeseries.map((b) => b.pageviews),
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
      x: {
        grid: { display: false },
        ticks: { maxTicksLimit: 8, font: { size: 11 } },
      },
      y: { beginAtZero: true, ticks: { precision: 0, font: { size: 11 } } },
    },
  };

  // Traffic grouped by race path.
  $: raceRequests = aggregateRaceTraffic(traffic?.top_pages ?? []);

  // Discovery-only races
  let allRaces: RaceRecord[] = [];
  $: discoveryOnlyRaces = allRaces.filter((r) => {
    const opts = (r.last_run_options ?? r.queue_options) as
      | { enabled_steps?: string[] }
      | undefined;
    if (!opts) return false;
    const steps = opts.enabled_steps;
    return (
      Array.isArray(steps) && steps.length === 1 && steps[0] === "discovery"
    );
  });

  $: donutData = raceRequests.length
    ? (() => {
        const top6 = raceRequests.slice(0, 6);
        const otherCount = raceRequests
          .slice(6)
          .reduce((s, r) => s + r.requests_24h, 0);
        const labels = [
          ...top6.map((r) => r.race_id),
          ...(otherCount > 0 ? ["Other"] : []),
        ];
        const data = [
          ...top6.map((r) => r.requests_24h),
          ...(otherCount > 0 ? [otherCount] : []),
        ];
        const colors = [
          "#3B82F6",
          "#10B981",
          "#F59E0B",
          "#EF4444",
          "#8B5CF6",
          "#EC4899",
          "#6B7280",
        ];
        return {
          labels,
          datasets: [
            {
              data,
              backgroundColor: colors.slice(0, data.length),
              borderWidth: 2,
            },
          ],
        };
      })()
    : { labels: [], datasets: [] };

  $: donutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "bottom" as const,
        labels: { font: { size: 11 }, boxWidth: 12 },
      },
    },
  };

  async function loadData(hours = selectedHours) {
    if (refreshInFlight) return refreshInFlight;
    refreshInFlight = (async () => {
      try {
        const [overviewRes, trafficRes] = await Promise.allSettled([
          analyticsService.getOverview(hours),
          analyticsService.getTraffic(hours),
        ]);

        if (overviewRes.status === "fulfilled") overview = overviewRes.value;
        if (trafficRes.status === "fulfilled") {
          traffic = trafficRes.value;
        } else {
          traffic = {
            configured: false,
            provider: "cloudflare",
            hours,
            pageviews: 0,
            visits: 0,
            pages_per_visit: 0,
            timeseries: [],
            top_pages: [],
            top_referrers: [],
            countries: [],
            devices: [],
            fetched_at: null,
            error: String(trafficRes.reason),
          };
        }

        const failed = [overviewRes].filter(
          (result) => result.status === "rejected",
        ).length;
        if (failed > 0)
          error = `${failed} dashboard request${
            failed === 1 ? "" : "s"
          } failed`;

        if (apiService) {
          try {
            allRaces = await apiService.listRaces();
          } catch {
            /* non-critical */
          }
        }
      } catch (e) {
        error = String(e);
      } finally {
        refreshInFlight = null;
        loading = false;
      }
    })();
    return refreshInFlight;
  }

  async function handleRangeChange(hours: number) {
    selectedHours = hours;
    loading = true;
    await loadData(hours);
  }

  export async function refresh() {
    loading = true;
    await loadData(selectedHours);
  }

  const gcpLogsUrl = GCP_PROJECT
    ? `https://console.cloud.google.com/logs/query;query=resource.type%3D%22cloud_run_revision%22?project=${GCP_PROJECT}`
    : null;

  function refreshWhenVisible() {
    if (typeof document !== "undefined" && document.hidden) return;
    void loadData(selectedHours);
  }

  function handleVisibilityChange() {
    if (!document.hidden) refreshWhenVisible();
  }

  onMount(() => {
    refreshWhenVisible();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    refreshTimer = setInterval(refreshWhenVisible, 5 * 60_000);
  });

  onDestroy(() => {
    if (refreshTimer) clearInterval(refreshTimer);
    document.removeEventListener("visibilitychange", handleVisibilityChange);
  });

  function formatTrafficTime(value: string) {
    if (!value) return "";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return selectedHours > 14 * 24
      ? parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" })
      : parsed.toLocaleString(undefined, {
          month: "short",
          day: "numeric",
          hour: "numeric",
        });
  }

  function aggregateRaceTraffic(pages: { name: string; pageviews: number }[]) {
    const totals = new Map<string, number>();
    for (const page of pages) {
      const match = page.name.match(/^\/races\/([^/?#]+)/);
      if (!match) continue;
      const raceId = decodeURIComponent(match[1]);
      totals.set(raceId, (totals.get(raceId) ?? 0) + page.pageviews);
    }
    return [...totals.entries()]
      .map(([race_id, requests_24h]) => ({ race_id, requests_24h }))
      .sort((a, b) => b.requests_24h - a.requests_24h);
  }
</script>

<!-- Time range selector -->
<div class="flex items-center justify-between mb-4">
  <div class="flex items-center gap-1 bg-surface-alt rounded-lg p-1">
    {#each TIME_RANGES as range}
      <button
        type="button"
        class="px-3 py-1 rounded-md text-sm font-medium transition-colors
          {selectedHours === range.value
          ? 'bg-surface text-content shadow-sm'
          : 'text-content-subtle hover:text-content-muted'}"
        on:click={() => handleRangeChange(range.value)}
      >
        {range.label}
      </button>
    {/each}
  </div>
  <button
    type="button"
    class="text-xs text-blue-600 hover:underline"
    on:click={() => loadData(selectedHours)}>Refresh</button
  >
</div>

{#if loading}
  <div class="flex items-center justify-center py-16">
    <div class="flex items-center space-x-3 text-content-subtle">
      <svg
        class="animate-spin h-5 w-5"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle
          class="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          stroke-width="4"
        />
        <path
          class="opacity-75"
          fill="currentColor"
          d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
      <span>Loading dashboard...</span>
    </div>
  </div>
{:else}
  {#if traffic && !traffic.configured}
    <div
      class="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-200"
    >
      Traffic analytics unavailable: {traffic.error}
    </div>
  {/if}

  <!-- Traffic stat cards -->
  <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
    <div class="card p-4">
      <p
        class="text-xs font-medium text-content-subtle uppercase tracking-wide"
      >
        Page Views ({rangeLabel})
      </p>
      <p class="mt-1 text-2xl font-bold text-content">
        {(traffic?.pageviews ?? 0).toLocaleString()}
      </p>
    </div>
    <div class="card p-4">
      <p
        class="text-xs font-medium text-content-subtle uppercase tracking-wide"
      >
        Visits
      </p>
      <p class="mt-1 text-2xl font-bold text-content">
        {(traffic?.visits ?? 0).toLocaleString()}
      </p>
    </div>
    <div class="card p-4">
      <p
        class="text-xs font-medium text-content-subtle uppercase tracking-wide"
      >
        Pages / Visit
      </p>
      <p class="mt-1 text-2xl font-bold text-content">
        {traffic?.pages_per_visit ?? 0}
      </p>
    </div>
    <div class="card p-4">
      <p
        class="text-xs font-medium text-content-subtle uppercase tracking-wide"
      >
        API Health
      </p>
      <p
        class="mt-1 text-xl font-bold {(overview?.error_rate ?? 0) > 5
          ? 'text-red-600'
          : 'text-content'}"
      >
        {overview?.error_rate ?? 0}% errors
      </p>
      <p class="mt-1 text-xs text-content-faint">
        {overview?.avg_latency_ms ?? 0} ms average latency
      </p>
    </div>
  </div>

  <!-- Discovery-only callout -->
  {#if discoveryOnlyRaces.length > 0}
    <div
      class="mb-4 rounded-lg border border-violet-300 dark:border-violet-700 bg-violet-50 dark:bg-violet-950/30 px-4 py-3 flex items-center justify-between gap-3"
    >
      <div class="flex items-center gap-2 min-w-0">
        <svg
          class="w-4 h-4 text-violet-600 dark:text-violet-400 shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          stroke-width="2"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
        <span class="text-sm font-medium text-violet-900 dark:text-violet-100">
          {discoveryOnlyRaces.length} race{discoveryOnlyRaces.length !== 1
            ? "s"
            : ""} in discovery-only state
        </span>
        <span
          class="text-xs text-violet-700 dark:text-violet-300 truncate hidden sm:block"
        >
          - candidates found but issues, research &amp; finance not yet
          populated
        </span>
      </div>
      <div class="flex items-center gap-1.5 shrink-0 flex-wrap">
        {#each discoveryOnlyRaces.slice(0, 4) as r}
          <span
            class="text-xs font-mono bg-violet-100 dark:bg-violet-900/40 text-violet-800 dark:text-violet-200 rounded px-1.5 py-0.5 border border-violet-200 dark:border-violet-800"
          >
            {r.race_id}
          </span>
        {/each}
        {#if discoveryOnlyRaces.length > 4}
          <span class="text-xs text-violet-600 dark:text-violet-400"
            >+{discoveryOnlyRaces.length - 4} more</span
          >
        {/if}
      </div>
    </div>
  {/if}

  <!-- Charts row -->
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
    <!-- Requests over time -->
    <div class="card p-4 lg:col-span-2">
      <h3 class="text-sm font-semibold text-content-muted mb-3">
        Page Views over Time ({rangeLabel})
      </h3>
      {#if (traffic?.timeseries?.length ?? 0) > 0}
        <div class="h-40">
          <Line data={lineData} options={lineOptions} />
        </div>
      {:else}
        <div
          class="h-40 flex items-center justify-center text-content-faint text-sm"
        >
          No data yet
        </div>
      {/if}
    </div>
    <!-- By race -->
    <div class="card p-4">
      <h3 class="text-sm font-semibold text-content-muted mb-3">
        Page Views by Race ({rangeLabel})
      </h3>
      {#if raceRequests.length > 0}
        <div class="h-40">
          <Doughnut data={donutData} options={donutOptions} />
        </div>
      {:else}
        <div
          class="h-40 flex items-center justify-center text-content-faint text-sm"
        >
          No data yet
        </div>
      {/if}
    </div>
  </div>

  {#if error}
    <div
      class="mb-4 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-700 dark:bg-red-950/30 dark:text-red-200"
    >
      {error}
    </div>
  {/if}

  {#if gcpLogsUrl}
    <div class="card p-4 mb-6">
      <a
        href={gcpLogsUrl}
        target="_blank"
        rel="noopener noreferrer"
        class="inline-flex items-center text-xs text-blue-600 hover:underline"
      >
        View logs in GCP Console ->
      </a>
    </div>
  {/if}

  {#if traffic?.configured}
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
      <div class="card p-4">
        <h3 class="text-sm font-semibold text-content-muted mb-3">Top Pages</h3>
        <div class="space-y-2">
          {#each traffic.top_pages.slice(0, 8) as item}
            <div class="flex items-center justify-between gap-3 text-xs">
              <span
                class="font-mono text-content-muted truncate"
                title={item.name}>{item.name}</span
              >
              <span class="font-semibold text-content shrink-0"
                >{item.pageviews.toLocaleString()}</span
              >
            </div>
          {/each}
        </div>
      </div>
      <div class="card p-4">
        <h3 class="text-sm font-semibold text-content-muted mb-3">
          Top Referrers
        </h3>
        <div class="space-y-2">
          {#each traffic.top_referrers.slice(0, 8) as item}
            <div class="flex items-center justify-between gap-3 text-xs">
              <span class="text-content-muted truncate" title={item.name}
                >{item.name}</span
              >
              <span class="font-semibold text-content shrink-0"
                >{item.visits.toLocaleString()}</span
              >
            </div>
          {/each}
        </div>
      </div>
      <div class="card p-4">
        <h3 class="text-sm font-semibold text-content-muted mb-3">Audience</h3>
        <div class="space-y-3">
          <div>
            <p class="text-xs text-content-faint mb-1.5">Countries</p>
            <div class="flex flex-wrap gap-1.5">
              {#each traffic.countries.slice(0, 6) as item}
                <span
                  class="rounded bg-surface-alt px-2 py-1 text-xs text-content-muted"
                  >{item.name} {item.visits}</span
                >
              {/each}
            </div>
          </div>
          <div>
            <p class="text-xs text-content-faint mb-1.5">Devices</p>
            <div class="flex flex-wrap gap-1.5">
              {#each traffic.devices.slice(0, 6) as item}
                <span
                  class="rounded bg-surface-alt px-2 py-1 text-xs text-content-muted"
                  >{item.name} {item.visits}</span
                >
              {/each}
            </div>
          </div>
        </div>
      </div>
    </div>
  {/if}
{/if}
