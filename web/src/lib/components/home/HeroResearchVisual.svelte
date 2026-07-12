<div
  class="relative mx-auto w-full max-w-xl"
  aria-label="Preview of sourced candidate research"
>
  <div
    class="absolute -left-4 top-16 hidden h-48 w-36 -rotate-6 rounded-xl border border-blue-200 bg-white p-4 shadow-xl sm:block dark:border-blue-900 dark:bg-slate-900"
    aria-hidden="true"
  >
    <div class="h-2 w-16 rounded bg-blue-100 dark:bg-blue-900" />
    <div class="mt-4 h-20 rounded bg-slate-100 dark:bg-slate-800" />
    <div class="mt-4 space-y-2">
      <div class="h-2 rounded bg-slate-200 dark:bg-slate-700" />
      <div class="h-2 w-4/5 rounded bg-slate-200 dark:bg-slate-700" />
    </div>
  </div>
  <div
    class="relative overflow-hidden rounded-2xl border border-blue-200/80 bg-white shadow-2xl shadow-blue-950/15 dark:border-blue-800 dark:bg-slate-950"
  >
    <div
      class="flex items-center justify-between border-b border-stroke px-5 py-4"
    >
      <div>
        <p
          class="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-600 dark:text-blue-400"
        >
          Election guide
        </p>
        <p class="mt-1 text-sm font-bold text-content">
          U.S. Senate · General election
        </p>
      </div>
      <span
        class="rounded-full bg-emerald-50 px-3 py-1 text-[10px] font-bold text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
        >Research updated</span
      >
    </div>
    <div class="grid grid-cols-[5.5rem_1fr_1fr] text-xs">
      <div
        class="border-b border-r border-stroke p-3 font-semibold text-content-subtle"
      >
        Issue
      </div>
      <div class="border-b border-r border-stroke p-3 font-bold text-content">
        Candidate A
      </div>
      <div class="border-b border-stroke p-3 font-bold text-content">
        Candidate B
      </div>
      {#each [["Economy", "Supports targeted tax credits and expanded manufacturing incentives.", "Favors broad tax reductions and regulatory reform."], ["Healthcare", "Would expand premium assistance under current law.", "Proposes market-based plans and state flexibility."], ["Energy", "Backs clean-energy investment with domestic production.", "Prioritizes domestic oil, gas, and nuclear production."]] as row, i}
        <div class="border-r border-stroke p-3 font-bold text-content">
          {row[0]}
        </div>
        <div class="border-r border-stroke p-3 leading-5 text-content-muted">
          {row[1]}<span
            class="mt-2 block font-semibold text-blue-600 dark:text-blue-400"
            >↗ {i + 2} sources</span
          >
        </div>
        <div class="p-3 leading-5 text-content-muted">
          {row[2]}<span
            class="mt-2 block font-semibold text-blue-600 dark:text-blue-400"
            >↗ {i + 1} sources</span
          >
        </div>
      {/each}
    </div>
    <div
      class="flex items-center gap-3 border-t border-stroke bg-blue-50/60 px-5 py-3 text-xs text-blue-900 dark:bg-blue-950/50 dark:text-blue-100"
    >
      <span class="h-2 w-2 rounded-full bg-amber-500" /><strong
        >Uncertainty noted:</strong
      > proposals differ in level of detail.
    </div>
  </div>
  <div
    class="absolute -bottom-7 -right-3 w-52 rotate-3 rounded-xl border border-blue-200 bg-white p-4 shadow-xl sm:-right-8 dark:border-blue-900 dark:bg-slate-900"
    aria-hidden="true"
  >
    <p
      class="text-[10px] font-bold uppercase tracking-widest text-content-subtle"
    >
      Source trail
    </p>
    <p class="mt-2 text-xs font-semibold text-content">
      Official policy platform
    </p>
    <p class="mt-1 truncate text-[10px] text-blue-600 dark:text-blue-400">
      candidate.example/issues
    </p>
  </div>
</div>
