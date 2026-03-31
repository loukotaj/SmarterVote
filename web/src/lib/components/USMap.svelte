<script lang="ts">
  import { onMount, createEventDispatcher } from "svelte";
  import { geoAlbersUsa, geoPath } from "d3-geo";
  import { feature } from "topojson-client";
  import type { Topology } from "topojson-specification";

  export let activeStates: Set<string> = new Set();
  export let selectedState: string | null = null;
  /** Map of jurisdiction name → count of races */
  export let raceCounts: Record<string, number> = {};

  const dispatch = createEventDispatcher<{ stateClick: string }>();

  // FIPS numeric ID → state name (Census Bureau standard)
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
  let hoveredState: string | null = null;
  let tooltipX = 0;
  let tooltipY = 0;
  let loaded = false;

  const projection = geoAlbersUsa().scale(1300).translate([487.5, 305]);
  const pathFn = geoPath(projection);

  onMount(async () => {
    const res = await fetch("/states-10m.json");
    const topology: Topology = await res.json();
    // @ts-ignore — topojson types are slightly loose here
    const geojson = feature(topology, topology.objects.states);
    // @ts-ignore
    stateFeatures = geojson.features.map((f: any) => {
      const fips = String(f.id).padStart(2, "0");
      const name = FIPS_TO_STATE[fips] ?? fips;
      return {
        id: fips,
        name,
        pathData: pathFn(f) ?? "",
      };
    }).filter((f: StateFeature) => f.pathData);
    loaded = true;
  });

  function handleClick(name: string) {
    dispatch("stateClick", name);
  }

  function getFill(name: string): string {
    if (name === selectedState) return "var(--map-selected)";
    if (activeStates.has(name)) return "var(--map-active)";
    return "var(--map-inactive)";
  }

  function getStroke(name: string): string {
    if (name === selectedState) return "var(--map-selected-stroke)";
    return "var(--map-stroke)";
  }
</script>

<style>
  :root {
    --map-active: #3b82f6;
    --map-selected: #1d4ed8;
    --map-selected-stroke: #1e3a8a;
    --map-inactive: #e5e7eb;
    --map-stroke: #d1d5db;
    --map-stroke-width: 0.5;
  }

  :global(.dark) {
    --map-active: #3b82f6;
    --map-selected: #1d4ed8;
    --map-selected-stroke: #93c5fd;
    --map-inactive: #1f2937;
    --map-stroke: #374151;
  }

  .state-path {
    cursor: default;
    transition: fill 0.15s ease;
  }

  .state-path.clickable {
    cursor: pointer;
  }

  .state-path.clickable:hover {
    filter: brightness(1.15);
  }

  .map-container {
    position: relative;
    width: 100%;
  }

  svg {
    display: block;
    width: 100%;
    height: auto;
  }

  .tooltip {
    position: absolute;
    pointer-events: none;
    background: rgba(17, 24, 39, 0.92);
    color: #f9fafb;
    font-size: 0.78rem;
    font-weight: 500;
    padding: 4px 10px;
    border-radius: 6px;
    white-space: nowrap;
    transform: translate(-50%, -110%);
    z-index: 10;
  }

  .skeleton {
    width: 100%;
    height: 300px;
    border-radius: 8px;
    background: repeating-linear-gradient(
      90deg,
      var(--map-inactive) 0%,
      color-mix(in srgb, var(--map-inactive) 70%, transparent) 50%,
      var(--map-inactive) 100%
    );
    background-size: 200% 100%;
    animation: shimmer 1.4s infinite;
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
    <svg viewBox="0 0 975 610" aria-label="US States map">
      {#each stateFeatures as state (state.id)}
        {@const isActive = activeStates.has(state.name)}
        {@const count = raceCounts[state.name] ?? 0}
        <path
          d={state.pathData}
          fill={getFill(state.name)}
          stroke={getStroke(state.name)}
          stroke-width="0.6"
          class="state-path {isActive ? 'clickable' : ''}"
          role={isActive ? "button" : undefined}
          tabindex={isActive ? 0 : undefined}
          aria-label={isActive ? `${state.name}, ${count} race${count !== 1 ? 's' : ''}` : state.name}
          on:click={() => isActive && handleClick(state.name)}
          on:keydown={(e) => { if (isActive && (e.key === 'Enter' || e.key === ' ')) handleClick(state.name); }}
          on:mouseenter={(e) => {
            if (isActive) {
              hoveredState = `${state.name}${count > 0 ? ` · ${count} race${count !== 1 ? 's' : ''}` : ''}`;
              const rect = (e.currentTarget as SVGPathElement).closest('.map-container')?.getBoundingClientRect();
              const svgEl = (e.currentTarget as SVGPathElement).ownerSVGElement!;
              const pt = svgEl.createSVGPoint();
              pt.x = e.clientX; pt.y = e.clientY;
              const svgRect = svgEl.getBoundingClientRect();
              tooltipX = ((e.clientX - svgRect.left) / svgRect.width) * 100;
              tooltipY = ((e.clientY - svgRect.top) / svgRect.height) * 100;
            }
          }}
          on:mouseleave={() => { hoveredState = null; }}
        />
      {/each}
    </svg>

    {#if hoveredState}
      <div
        class="tooltip"
        style="left: {tooltipX}%; top: {tooltipY}%;"
      >
        {hoveredState}
      </div>
    {/if}
  {/if}
</div>
