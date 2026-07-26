<script lang="ts">
  import type { ForecastRating } from "$lib/types";
  import { formatRating } from "$lib/utils/forecast";
  import { ratingClass } from "$lib/utils/forecastPresentation";

  export let ratingOrder: ForecastRating[];
  export let ratingCounts: Partial<Record<ForecastRating, number>>;
</script>

<!-- Ratings Counts Grid Card -->
<section
  class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md"
>
  <p
    class="text-xs font-bold uppercase text-content-subtle tracking-wider mb-4"
  >
    Forecast Ratings Breakdown
  </p>
  <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-9 gap-2">
    {#each ratingOrder as rating}
      <div
        class={`border rounded-xl px-2 py-1.5 text-center transition-all ${ratingClass(
          rating,
        )}`}
      >
        <div class="text-[10px] font-bold leading-tight truncate">
          {formatRating(rating)}
        </div>
        <div class="text-lg font-black mt-1 tabular-nums">
          {ratingCounts[rating] ?? 0}
        </div>
      </div>
    {/each}
  </div>
</section>
