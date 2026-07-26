<script lang="ts">
  export let filterRating: string;
  export let filterParty: string;
  export let sortBy: string;
  export let selectedState: string | null;
  export let resultCount: number;
  export let onFilterRatingChange: (rating: string) => void;
  export let onFilterPartyChange: (party: string) => void;
  export let onSortByChange: (sortBy: string) => void;
  export let onClearState: () => void;

  const ratingPills = [
    { id: "all", label: "All Ratings" },
    { id: "tossup", label: "Toss-ups" },
    { id: "tilt", label: "Tilt" },
    { id: "lean", label: "Lean" },
    { id: "likely_safe", label: "Likely/Safe" },
  ];

  const partyPills = [
    { id: "all", label: "All Parties" },
    { id: "Democratic", label: "Democratic" },
    { id: "Republican", label: "Republican" },
  ];

  function handleSortChange(event: Event) {
    onSortByChange((event.target as HTMLSelectElement).value);
  }
</script>

<!-- Filter and Sort Header bar -->
<div class="px-5 py-5 border-b border-stroke/40 bg-surface-alt/10 space-y-4">
  <div class="flex flex-col md:flex-row justify-between gap-4">
    <!-- Pills Filter block -->
    <div class="space-y-2.5">
      <div class="flex flex-wrap items-center gap-2">
        <span
          class="text-xs font-bold text-content-subtle uppercase tracking-wider w-16"
          >Rating:</span
        >
        {#each ratingPills as pill}
          <button
            type="button"
            on:click={() => onFilterRatingChange(pill.id)}
            class="text-xs px-3 py-1.5 rounded-full font-bold transition-all border
            {filterRating === pill.id
              ? 'bg-blue-600 text-white border-blue-600 dark:bg-blue-500 dark:border-blue-500'
              : 'bg-surface border-stroke hover:bg-surface-alt/50 text-content-muted'}"
          >
            {pill.label}
          </button>
        {/each}
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <span
          class="text-xs font-bold text-content-subtle uppercase tracking-wider w-16"
          >Favored:</span
        >
        {#each partyPills as pill}
          <button
            type="button"
            on:click={() => onFilterPartyChange(pill.id)}
            class="text-xs px-3 py-1.5 rounded-full font-bold transition-all border
            {filterParty === pill.id
              ? pill.id === 'Democratic'
                ? 'bg-blue-600 text-white border-blue-600 dark:bg-blue-500 dark:border-blue-500'
                : 'bg-red-600 text-white border-red-600 dark:bg-red-500 dark:border-red-500'
              : 'bg-surface border-stroke hover:bg-surface-alt/50 text-content-muted'}"
          >
            {pill.label}
          </button>
        {/each}
      </div>
    </div>

    <!-- Sort block -->
    <div
      class="flex flex-row md:flex-col md:items-end justify-between md:justify-start gap-4"
    >
      <div class="flex items-center gap-2.5">
        <label
          for="sort-by"
          class="text-xs font-bold text-content-subtle uppercase tracking-wider"
          >Sort by:</label
        >
        <select
          id="sort-by"
          value={sortBy}
          on:change={handleSortChange}
          class="text-xs bg-surface border border-stroke/60 rounded-xl px-3 py-1.5 text-content font-bold focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option value="control_relevance"
            >Most likely to decide control</option
          >
          <option value="competitiveness">Most competitive</option>
          <option value="dem_pickup">Highest Democratic pickup chance</option>
          <option value="gop_pickup"
            >Highest Republican hold/pickup chance</option
          >
          <option value="probability">Win Probability</option>
          <option value="margin">Margin Estimate</option>
          <option value="state">State</option>
          <option value="rating">Rating</option>
        </select>
      </div>

      <div class="flex items-center gap-2.5 text-xs">
        {#if selectedState}
          <button
            type="button"
            on:click={onClearState}
            class="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-bold bg-blue-50 dark:bg-blue-950/40 px-2.5 py-1 rounded-xl border border-blue-200/50"
          >
            State: {selectedState} x
          </button>
        {/if}

        <span
          class="text-xs text-content-subtle font-extrabold bg-surface-alt px-2.5 py-1 rounded-xl border border-stroke/60"
        >
          {resultCount} races
        </span>
      </div>
    </div>
  </div>
</div>
