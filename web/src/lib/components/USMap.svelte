<script lang="ts">
  import { onMount, createEventDispatcher } from "svelte";
  import { geoAlbersUsa, geoPath } from "d3-geo";
  import { feature } from "topojson-client";
  import type { Topology } from "topojson-specification";

  export let activeStates: Set<string> = new Set();
  export let selectedState: string | null = null;
  export let raceCounts: Record<string, number> = {};
  export let matchingCandidatesByState: Record<string, string[]> = {};
  export let stateColors: Record<string, string> = {};
  export let stateTooltips: Record<string, {
    title: string;
    subtitle?: string;
    badge?: string;
    badgeClass?: string;
    details?: string[];
  }> = {};

  const dispatch = createEventDispatcher<{ stateClick: string }>();

  const FIPS_TO_STATE: Record<string, string> = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona", "05": "Arkansas",
    "06": "California", "08": "Colorado", "09": "Connecticut", "10": "Delaware",
    "11": "District of Columbia", "12": "Florida", "13": "Georgia",
    "15": "Hawaii", "16": "Idaho", "17": "Illinois", "18": "Indiana",
    "19": "Iowa", "20": "Kansas", "21": "Kentucky", "22": "Louisiana",
    "23": "Maine", "24": "Maryland", "25": "Massachusetts", "26": "Michigan",
    "27": "Minnesota", "28": "Mississippi", "29": "Missouri", "30": "Montana",
    "31": "Nebraska", "32": "Nevada", "33": "New Hampshire", "34": "New Jersey",
    "35": "New Mexico", "36": "New York", "37": "North Carolina", "38": "North Dakota",
    "39": "Ohio", "40": "Oklahoma", "41": "Oregon", "42": "Pennsylvania",
    "44": "Rhode Island", "45": "South Carolina", "46": "South Dakota",
    "47": "Tennessee", "48": "Texas", "49": "Utah", "50": "Vermont",
    "51": "Virginia", "53": "Washington", "54": "West Virginia",
    "55": "Wisconsin", "56": "Wyoming",
  };

  interface StateFeature {
    id: string;
    name: string;
    pathData: string;
  }

  let stateFeatures: StateFeature[] = [];
  let hoveredStateName: string | null = null;
  let hoveredStateCount = 0;
  let tooltipX = 0;
  let tooltipY = 0;
  let loaded = false;
  let svgEl: SVGSVGElement;

  const projection = geoAlbersUsa().scale(1300).translate([487.5, 305]);
  const pathFn = geoPath(projection);

  onMount(async () => {
    const res = await fetch("/states-10m.json");
    const topology = await res.json() as Topology;
    // @ts-ignore
    const geojson = feature(topology, topology.objects.states);
    // @ts-ignore
    stateFeatures = geojson.features
      .map((f: any) => {
        const fips = String(f.id).padStart(2, "0");
        const name = FIPS_TO_STATE[fips] ?? fips;
        return { id: fips, name, pathData: pathFn(f) ?? "" };
      })
      .filter((f: StateFeature) => f.pathData);
    loaded = true;
  });

  function handleClick(name: string) {
    dispatch("stateClick", name);
  }

  function handleKeydown(e: KeyboardEvent, name: string) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      dispatch("stateClick", name);
    }
  }

  function handleMouseEnter(e: MouseEvent, name: string, count: number) {
    hoveredStateName = name;
    hoveredStateCount = count;
    if (svgEl) {
      const rect = svgEl.getBoundingClientRect();
      tooltipX = ((e.clientX - rect.left) / rect.width) * 100;
      tooltipY = ((e.clientY - rect.top) / rect.height) * 100;
    }
  }

  function handleMouseLeave() {
    hoveredStateName = null;
    hoveredStateCount = 0;
  }

  function getFill(name: string): string {
    if (stateColors[name]) return stateColors[name];
    if (name === selectedState) return "var(--map-selected)";
    if (activeStates.has(name)) return "var(--map-active)";
    return "var(--map-inactive)";
  }

  // Split into two render passes so the selected state always paints on top
  $: baseFeatures = stateFeatures.filter((s) => s.name !== selectedState);
  $: selectedFeature = stateFeatures.find((s) => s.name === selectedState) ?? null;
</script>

<style>
  :root {
    --map-active: #3b82f6;
    --map-selected: #1d4ed8;
    --map-selected-stroke: #ffffff;
    --map-inactive: #e5e7eb;
    --map-stroke: #d1d5db;

    --color-safe-d: #1d4ed8;
    --color-likely-d: #3b82f6;
    --color-lean-d: #60a5fa;
    --color-tilt-d: #93c5fd;
    --color-tossup: #cbd5e1;
    --color-tilt-r: #fca5a5;
    --color-lean-r: #f87171;
    --color-likely-r: #ef4444;
    --color-safe-r: #b91c1c;
    --color-other: #94a3b8;
    --color-holdover-d: rgba(59, 130, 246, 0.18);
    --color-holdover-r: rgba(239, 68, 68, 0.18);
  }

  :global(.dark) {
    --map-active: #3b82f6;
    --map-selected: #60a5fa;
    --map-selected-stroke: #0f172a;
    --map-inactive: #1f2937;
    --map-stroke: #374151;

    --color-safe-d: #1e3a8a;
    --color-likely-d: #1d4ed8;
    --color-lean-d: #2563eb;
    --color-tilt-d: #3b82f6;
    --color-tossup: #334155;
    --color-tilt-r: #ef4444;
    --color-lean-r: #dc2626;
    --color-likely-r: #b91c1c;
    --color-safe-r: #7f1d1d;
    --color-other: #475569;
    --color-holdover-d: rgba(59, 130, 246, 0.28);
    --color-holdover-r: rgba(239, 68, 68, 0.28);
  }

  .state-path {
    transition: fill 0.2s cubic-bezier(0.4, 0, 0.2, 1), filter 0.2s ease, stroke-width 0.2s ease;
    cursor: default;
  }

  .state-path.clickable {
    cursor: pointer;
  }

  .state-path.clickable:hover {
    filter: brightness(1.1) drop-shadow(0 4px 12px rgba(59, 130, 246, 0.2));
  }

  .state-path:focus {
    outline: none;
  }

  .map-container {
    position: relative;
    width: 100%;
    max-width: 720px;
    margin: 0 auto;
  }

  svg {
    display: block;
    width: 100%;
    height: auto;
  }

  .tooltip {
    position: absolute;
    pointer-events: none;
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #f8fafc;
    padding: 8px 12px;
    border-radius: 8px;
    transform: translate(-50%, calc(-100% - 10px));
    z-index: 20;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3), 0 4px 6px -4px rgba(0, 0, 0, 0.3);
    display: flex;
    flex-direction: column;
    gap: 4px;
    align-items: center;
  }

  :global(.dark) .tooltip {
    background: rgba(15, 23, 42, 0.85);
    border-color: rgba(255, 255, 255, 0.08);
  }

  .tooltip-state {
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.025em;
  }

  .tooltip-badge {
    font-size: 0.7rem;
    background: #3b82f6;
    color: white;
    padding: 2px 8px;
    border-radius: 9999px;
    font-weight: 600;
  }

  .tooltip-no-races {
    font-size: 0.7rem;
    color: #94a3b8;
    font-weight: 500;
  }

  .skeleton {
    width: 100%;
    height: 280px;
    border-radius: 8px;
    background: linear-gradient(90deg, #e5e7eb 25%, #f3f4f6 50%, #e5e7eb 75%);
    background-size: 200% 100%;
    animation: shimmer 1.4s infinite;
  }

  :global(.dark) .skeleton {
    background: linear-gradient(90deg, #1f2937 25%, #374151 50%, #1f2937 75%);
    background-size: 200% 100%;
  }

  @keyframes shimmer {
    0%   { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
</style>

<div class="map-container">
  {#if !loaded}
    <div class="skeleton" />
  {:else}
    <svg bind:this={svgEl} viewBox="0 0 975 610" aria-label="US States map">
      <!-- Base pass: all states except selected -->
      {#each baseFeatures as state (state.id)}
        {@const canHover = activeStates.has(state.name) || !!stateTooltips[state.name]}
        {@const canClick = activeStates.has(state.name)}
        {@const count = raceCounts[state.name] ?? 0}
        <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
        <path
          d={state.pathData}
          fill={getFill(state.name)}
          stroke="var(--map-stroke)"
          stroke-width="0.6"
          class="state-path {canHover ? 'clickable' : ''}"
          role={canClick ? "button" : (canHover ? "img" : "presentation")}
          tabindex={canClick ? 0 : -1}
          aria-label={canClick ? `${state.name}, ${count} race${count !== 1 ? 's' : ''}` : state.name}
          on:click={() => canClick && handleClick(state.name)}
          on:keydown={(e) => handleKeydown(e, state.name)}
          on:mouseenter={(e) => canHover && handleMouseEnter(e, state.name, count)}
          on:mouseleave={handleMouseLeave}
        />
      {/each}

      <!-- Selected state rendered last so its stroke is never clipped by neighbors -->
      {#if selectedFeature}
        {@const canHover = activeStates.has(selectedFeature.name) || !!stateTooltips[selectedFeature.name]}
        {@const canClick = activeStates.has(selectedFeature.name)}
        {@const count = raceCounts[selectedFeature.name] ?? 0}
        <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
        <path
          d={selectedFeature.pathData}
          fill={getFill(selectedFeature.name)}
          stroke="var(--map-selected-stroke)"
          stroke-width="2.5"
          stroke-linejoin="round"
          class="state-path {canHover ? 'clickable' : ''}"
          role={canClick ? "button" : (canHover ? "img" : "presentation")}
          tabindex={canClick ? 0 : -1}
          aria-label="{selectedFeature.name}, {count} race{count !== 1 ? 's' : ''}, selected"
          on:click={() => canClick && handleClick(selectedFeature.name)}
          on:keydown={(e) => handleKeydown(e, selectedFeature.name)}
          on:mouseenter={(e) => canHover && handleMouseEnter(e, selectedFeature.name, count)}
          on:mouseleave={handleMouseLeave}
        />
      {/if}
    </svg>

    {#if hoveredStateName && stateTooltips[hoveredStateName]}
      {@const tip = stateTooltips[hoveredStateName]}
      <div
        class="tooltip"
        style="left: {tooltipX}%; top: {tooltipY}%;"
      >
        <span class="tooltip-state">{tip.title}</span>
        {#if tip.subtitle}
          <span class="text-[11px] text-gray-400 font-medium">{tip.subtitle}</span>
        {/if}
        {#if tip.badge}
          <span class="tooltip-badge {tip.badgeClass ?? ''}">{tip.badge}</span>
        {/if}
        {#if tip.details && tip.details.length > 0}
          <div class="mt-1.5 pt-1.5 border-t border-white/10 w-full text-center flex flex-col gap-0.5 animate-fade-in">
            {#each tip.details as detail}
              <span class="text-[11px] text-white/90 font-medium">{detail}</span>
            {/each}
          </div>
        {/if}
      </div>
    {:else if hoveredStateName}
      <div
        class="tooltip"
        style="left: {tooltipX}%; top: {tooltipY}%;"
      >
        <span class="tooltip-state">{hoveredStateName}</span>
        {#if hoveredStateCount > 0}
          <span class="tooltip-badge">{hoveredStateCount} {hoveredStateCount === 1 ? 'Race' : 'Races'}</span>
          {#if matchingCandidatesByState[hoveredStateName] && matchingCandidatesByState[hoveredStateName].length > 0}
            <div class="mt-1.5 pt-1.5 border-t border-white/10 w-full text-center">
              <span class="text-[9px] text-gray-400 font-semibold block mb-0.5 tracking-wide uppercase">Matches</span>
              <div class="text-[11px] text-white/90 font-medium leading-tight max-w-[160px] mx-auto">
                {matchingCandidatesByState[hoveredStateName].join(", ")}
              </div>
            </div>
          {/if}
        {:else}
          <span class="tooltip-no-races">No active races</span>
        {/if}
      </div>
    {/if}
  {/if}
</div>
