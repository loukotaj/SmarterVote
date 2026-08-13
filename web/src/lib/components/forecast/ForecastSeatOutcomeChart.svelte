<script lang="ts">
  import type { GroupedSeatBucket } from "$lib/utils/forecast";
  import type { SeatOutcomeChart } from "$lib/utils/forecastPresentation";

  export let seatBuckets: GroupedSeatBucket[];
  export let sortedOutcomes: SeatOutcomeChart["outcomes"];
  export let maxProbability: number;
  export let svgData: SeatOutcomeChart["svgData"];

  let activeChartType: "buckets" | "histogram" | "curve" = "buckets";
</script>

<!-- Seat Outcome Distribution Card -->
<div
  class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md flex-1"
>
  <div
    class="flex items-center justify-between mb-4 border-b border-stroke/40 pb-3"
  >
    <div>
      <h3
        class="text-sm font-black uppercase text-content-subtle tracking-wider"
      >
        Seat Outcome Distribution
      </h3>
      <p class="text-[10px] text-content-subtle font-medium mt-0.5">
        Probability of final Republican/Democratic seat splits
      </p>
    </div>
  </div>

  <!-- Chart Tab Toggle -->
  <div
    class="flex gap-1 bg-surface-alt/60 p-1 rounded-lg border border-stroke/45 mb-4"
  >
    <button
      on:click={() => (activeChartType = "buckets")}
      class={`flex-1 text-center py-1 text-[11px] font-bold rounded-md transition-all ${
        activeChartType === "buckets"
          ? "bg-surface text-content shadow-sm border border-stroke/20"
          : "text-content-subtle hover:text-content"
      }`}
    >
      Groups
    </button>
    <button
      on:click={() => (activeChartType = "histogram")}
      class={`flex-1 text-center py-1 text-[11px] font-bold rounded-md transition-all ${
        activeChartType === "histogram"
          ? "bg-surface text-content shadow-sm border border-stroke/20"
          : "text-content-subtle hover:text-content"
      }`}
    >
      Histogram
    </button>
    <button
      on:click={() => (activeChartType = "curve")}
      class={`flex-1 text-center py-1 text-[11px] font-bold rounded-md transition-all ${
        activeChartType === "curve"
          ? "bg-surface text-content shadow-sm border border-stroke/20"
          : "text-content-subtle hover:text-content"
      }`}
    >
      Curve
    </button>
  </div>

  <!-- Chart Content Area -->
  <div class="min-h-[160px] flex flex-col justify-center">
    {#if activeChartType === "buckets"}
      <div class="space-y-4">
        <!-- Visual Stacked Bar -->
        <div
          class="h-8 rounded-lg overflow-hidden flex border border-stroke/60"
        >
          {#each seatBuckets as bucket}
            {#if bucket.probability > 0}
              <div
                class={`${bucket.colorClass} transition-all duration-500 flex items-center justify-center text-[10px] font-bold text-white shadow-inner relative group cursor-pointer`}
                style={`width: ${bucket.probability * 100}%`}
              >
                <!-- Tooltip -->
                <div
                  class="absolute bottom-full mb-2 hidden group-hover:block z-50 bg-surface border border-stroke p-2 rounded-lg shadow-md text-xs font-semibold text-content w-40 text-center pointer-events-none"
                >
                  <div class="font-bold">{bucket.label}</div>
                  <div class="text-blue-600 dark:text-blue-400 mt-1">
                    {(bucket.probability * 100).toFixed(1)}% probability
                  </div>
                </div>

                {#if bucket.probability > 0.08}
                  {Math.round(bucket.probability * 100)}%
                {/if}
              </div>
            {/if}
          {/each}
        </div>

        <!-- Legend & Details -->
        <div class="grid grid-cols-1 gap-2.5">
          {#each seatBuckets as bucket}
            {#if bucket.probability > 0}
              <div class="flex items-center justify-between text-xs">
                <div class="flex items-center gap-2">
                  <span
                    class={`w-3.5 h-3.5 rounded ${bucket.colorClass} border border-stroke/20`}
                  ></span>
                  <span class="font-bold text-content">{bucket.label}</span>
                </div>
                <span class="font-black text-content-muted"
                  >{(bucket.probability * 100).toFixed(1)}%</span
                >
              </div>
            {/if}
          {/each}
        </div>
      </div>
    {:else if activeChartType === "histogram"}
      <div class="space-y-2 max-h-[280px] overflow-y-auto pr-1 select-none">
        {#each sortedOutcomes as outcome}
          {@const isTie = outcome.dSeats === 50}
          {@const isDem = outcome.dSeats >= 51}
          <div class="flex items-center gap-3 text-xs">
            <!-- Label e.g. "52D - 48R" -->
            <span
              class="w-20 font-mono font-bold text-[10px] text-content-subtle shrink-0"
            >
              {outcome.dSeats}D - {outcome.rSeats}R
            </span>
            <!-- Bar track -->
            <div
              class="flex-1 bg-surface-alt rounded-full h-3 overflow-hidden border border-stroke/40 relative"
            >
              <div
                class={`h-full rounded-full transition-all duration-300 ${
                  isTie
                    ? "bg-slate-400 dark:bg-slate-500"
                    : isDem
                      ? "bg-blue-500 dark:bg-blue-600"
                      : "bg-red-500 dark:bg-red-600"
                }`}
                style={`width: ${(outcome.probability / maxProbability) * 100}%`}
              ></div>
            </div>
            <!-- Value -->
            <span
              class="w-10 text-right font-black font-mono text-[10px] text-content-muted shrink-0"
            >
              {(outcome.probability * 100).toFixed(1)}%
            </span>
          </div>
        {/each}
      </div>
    {:else if activeChartType === "curve"}
      <div
        class="relative w-full h-[180px] select-none flex flex-col justify-between"
      >
        <!-- SVG Area Chart -->
        <svg viewBox="0 0 300 100" class="w-full h-[140px] overflow-visible">
          <defs>
            <linearGradient id="curveGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="rgba(59, 130, 246, 0.4)" />
              <stop offset="100%" stop-color="rgba(239, 68, 68, 0.4)" />
            </linearGradient>
            <linearGradient id="lineGradient" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stop-color="#3b82f6" />
              <stop offset="100%" stop-color="#ef4444" />
            </linearGradient>
          </defs>

          <!-- Grid lines -->
          <line
            x1="15"
            y1="85"
            x2="285"
            y2="85"
            stroke="currentColor"
            class="text-stroke/60"
            stroke-width="0.75"
          />
          <line
            x1="15"
            y1="10"
            x2="285"
            y2="10"
            stroke="currentColor"
            class="text-stroke/20"
            stroke-dasharray="2 2"
            stroke-width="0.5"
          />

          <!-- Area Path -->
          {#if svgData.fillPath}
            <path d={svgData.fillPath} fill="url(#curveGradient)" />
            <path
              d={svgData.strokePath}
              stroke="url(#lineGradient)"
              stroke-width="1.5"
              fill="none"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          {/if}

          <!-- Tie break line -->
          <line
            x1={svgData.tieX}
            y1="10"
            x2={svgData.tieX}
            y2="85"
            stroke="currentColor"
            class="text-slate-400 dark:text-slate-500"
            stroke-width="1"
            stroke-dasharray="3 3"
          />

          <!-- Hoverable Points -->
          {#each svgData.points as pt}
            <g class="group/point cursor-pointer">
              <circle
                cx={pt.x}
                cy={pt.y}
                r="3.5"
                fill="currentColor"
                class="text-blue-600 dark:text-blue-400 scale-0 group-hover/point:scale-120 transition-transform origin-center"
                stroke="currentColor"
                stroke-width="1.5"
              />
              <circle cx={pt.x} cy={pt.y} r="7" fill="transparent" />
              <foreignObject
                x={Math.max(10, pt.x - 55)}
                y={Math.max(0, pt.y - 38)}
                width="110"
                height="35"
                class="pointer-events-none hidden group-hover/point:block overflow-visible z-50"
              >
                <div
                  class="bg-surface border border-stroke p-1 rounded shadow-md text-[8px] font-black text-center leading-tight"
                >
                  <div>{pt.dSeats}D - {pt.rSeats}R</div>
                  <div class="text-blue-500 mt-0.5">
                    {(pt.prob * 100).toFixed(1)}% prob
                  </div>
                </div>
              </foreignObject>
            </g>
          {/each}
        </svg>

        <!-- X-axis Labels -->
        <div
          class="flex justify-between text-[9px] font-bold text-content-subtle px-2 border-t border-stroke/20 pt-1.5 mt-1"
        >
          <span>{svgData.minD}D (Min)</span>
          <span class="text-slate-400 dark:text-slate-500"
            >50-50 Tie Threshold</span
          >
          <span>{svgData.maxD}D (Max)</span>
        </div>
      </div>
    {/if}
  </div>
</div>
