<section class="py-14 sm:py-20" aria-labelledby="how-it-works">
  <div class="mx-auto max-w-6xl px-4">
    <h2 id="how-it-works" class="text-3xl font-bold text-content">
      How it works
    </h2>
    <div class="mt-8 grid gap-5 md:grid-cols-3">
      {#each [["Research", "Gather candidate statements, official records, reputable reporting, and other public sources."], ["Review", "Compare evidence, flag conflicts, and run consistency and quality checks before publication."], ["Verify", "Link claims to sources, show uncertainty and update dates, and accept corrections."]] as step, index}
        <article class="rounded-2xl border border-stroke bg-surface p-6">
          <p class="text-sm font-semibold text-blue-600 dark:text-blue-400">
            0{index + 1}
          </p>
          <h3 class="mt-2 text-xl font-semibold text-content">{step[0]}</h3>
          <p class="mt-2 text-sm leading-6 text-content-muted">{step[1]}</p>
        </article>
      {/each}
    </div>
  </div>
</section>
