<section class="bg-surface-alt py-14 sm:py-20" aria-labelledby="trust-heading">
  <div class="mx-auto max-w-6xl px-4">
    <h2 id="trust-heading" class="text-3xl font-bold text-content">
      Research you can inspect
    </h2>
    <p class="mt-3 max-w-3xl leading-7 text-content-muted">
      Smarter.Vote is nonpartisan. We do not endorse candidates. We do not claim
      perfect neutrality or infallibility.
    </p>
    <div class="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {#each [["Sourced", "Important claims link to supporting material."], ["Transparent about limits", "Uncertainty, sparse evidence, and update dates stay visible."], ["Consistent standards", "The same research and review rules apply regardless of party."], ["Independent", "Supporters cannot influence conclusions or coverage treatment."], ["Correctable", "Readers can report errors and material updates are documented."]] as principle}
        <article class="rounded-xl border border-stroke bg-surface p-5">
          <h3 class="font-semibold text-content">{principle[0]}</h3>
          <p class="mt-2 text-sm leading-6 text-content-muted">
            {principle[1]}
          </p>
        </article>
      {/each}
    </div>
    <div
      class="mt-7 flex flex-wrap gap-5 text-sm font-semibold text-blue-600 dark:text-blue-400"
    >
      <a href="/methodology/" class="hover:underline">Read our methodology</a>
      <a href="/corrections/" class="hover:underline">Request a correction</a>
      <a href="/funding-and-editorial-independence/" class="hover:underline"
        >Funding and independence</a
      >
    </div>
  </div>
</section>
