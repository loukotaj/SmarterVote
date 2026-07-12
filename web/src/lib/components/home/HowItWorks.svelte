<section class="bg-surface-alt py-20 sm:py-28" aria-labelledby="how-it-works">
  <div class="mx-auto max-w-6xl px-4 sm:px-6">
    <div class="grid gap-12 lg:grid-cols-[.65fr_1.35fr]">
      <div>
        <p
          class="text-xs font-bold uppercase tracking-[0.24em] text-blue-600 dark:text-blue-400"
        >
          From address to evidence
        </p>
        <h2
          id="how-it-works"
          class="mt-4 text-4xl font-bold tracking-tight text-content sm:text-5xl"
        >
          Three steps. Your conclusions.
        </h2>
      </div>
      <ol class="grid gap-8 sm:grid-cols-3">
        {#each [["Find", "See the elections that apply to your address."], ["Compare", "Explore structured positions, experience, and donors."], ["Inspect", "Open the original sources and verify each claim."]] as step, index}
          <li class="relative border-t-2 border-blue-600 pt-5">
            <span
              class="font-mono text-xs font-bold text-blue-600 dark:text-blue-400"
              >0{index + 1}</span
            >
            <h3 class="mt-6 text-2xl font-bold text-content">{step[0]}</h3>
            <p class="mt-3 leading-7 text-content-muted">{step[1]}</p>
          </li>
        {/each}
      </ol>
    </div>
  </div>
</section>
