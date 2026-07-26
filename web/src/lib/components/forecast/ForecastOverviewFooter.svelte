<script lang="ts">
  export let narrative: string;
  export let updatedAt: string | undefined;
</script>

<div class="lg:col-span-12 space-y-4 pt-2">
  <div
    class="bg-surface-alt/10 border border-stroke/40 rounded-2xl p-5 relative overflow-hidden"
  >
    <div
      class="flex items-center gap-1.5 text-[10px] font-black uppercase text-blue-600 dark:text-blue-400 tracking-wider mb-2.5"
    >
      <svg
        class="w-3.5 h-3.5"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
        />
      </svg>
      Forecast Overview
    </div>
    <p class="text-sm font-semibold text-content leading-relaxed">
      {narrative ||
        "Projections indicate a highly competitive cycle for this chamber."}
    </p>
  </div>

  <!-- Clean Updated Footer -->
  <div
    class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-content-subtle font-semibold px-1"
  >
    <span>AI-generated model projection</span>
    {#if updatedAt}
      <span class="w-1 h-1 rounded-full bg-stroke/60"></span>
      <span
        >Last updated <span class="font-bold text-content"
          >{new Date(updatedAt).toLocaleDateString()}</span
        ></span
      >
    {/if}
  </div>
</div>
