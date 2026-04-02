<script lang="ts">
  import { onMount, createEventDispatcher } from "svelte";
  import { geoAlbersUsa, geoPath } from "d3-geo";
  import { feature } from "topojson-client";
  import type { Topology } from "topojson-specification";

  export let activeStates: Set<string> = new Set();
  export let selectedState: string | null = null;
  export let raceCounts: Record<string, number> = {};

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
  let hoveredState: string | null = null;
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
    hoveredState = count > 0
      ? `${name} \u00b7 ${count} race${count !== 1 ? "s" : ""}`
      : name;
    if (svgEl) {
      const rect = svgEl.getBoundingClientRect();
      tooltipX = ((e.clientX - rect.left) / rect.width) * 100;
      tooltipY = ((e.clientY - rect.top) / rect.height) * 100;
    }
  }

  function handleMouseLeave() {
    hoveredState = null;
  }

  function getFill(name: string): string {
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
  }

  :global(.dark) {
    --map-active: #3b82f6;
    --map-selected: #60a5fa;
    --map-selected-stroke: #0f172a;
    --map-inactive: #1f2937;
    --map-stroke: #374151;
  }

  .state-path {
    transition: fill 0.12s ease;
    cursor: default;
  }

  .state-path.clickable {
    cursor: pointer;
  }

  .state-path.clickable:hover {
    filter: brightness(1.18);
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
    background: rgba(17, 24, 39, 0.9);
    color: #f9fafb;
    font-size: 0.75rem;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 6px;
    white-space: nowrap;
    transform: translate(-50%, calc(-100% - 6px));
    z-index: 20;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
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
        {@const isActive = activeStates.has(state.name)}
        {@const count = raceCounts[state.name] ?? 0}
        <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
        <path
          d={state.pathData}
          fill={getFill(state.name)}
          stroke="var(--map-stroke)"
          stroke-width="0.6"
          class="state-path {isActive ? 'clickable' : ''}"
          role={isActive ? "button" : "img"}
          tabindex={isActive ? 0 : -1}
          aria-label={isActive ? `${state.name}, ${count} race${count !== 1 ? 's' : ''}` : state.name}
          on:click={() => isActive && handleClick(state.name)}
          on:keydown={(e) => handleKeydown(e, state.name)}
          on:mouseenter={(e) => isActive && handleMouseEnter(e, state.name, count)}
          on:mouseleave={handleMouseLeave}
        />
      {/each}

      <!-- Selected state rendered last so its stroke is never clipped by neighbors -->
      {#if selectedFeature}
        {@const count = raceCounts[selectedFeature.name] ?? 0}
        <path
          d={selectedFeature.pathData}
          fill="var(--map-selected)"
          stroke="var(--map-selected-stroke)"
          stroke-width="2.5"
          stroke-linejoin="round"
          class="state-path clickable"
          role="button"
          tabindex={0}
          aria-label="{selectedFeature.name}, {count} race{count !== 1 ? 's' : ''}, selected"
          on:click={() => handleClick(selectedFeature.name)}
          on:keydown={(e) => handleKeydown(e, selectedFeature.name)}
          on:mouseenter={(e) => handleMouseEnter(e, selectedFeature.name, count)}
          on:mouseleave={handleMouseLeave}
        />
      {/if}
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
