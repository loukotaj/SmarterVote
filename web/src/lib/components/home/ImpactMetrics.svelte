<script lang="ts">
  import type { HomepageMetrics } from "$lib/utils/homepage";
  export let metrics: HomepageMetrics;
  const date = (value: string) =>
    new Date(value).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
</script>

<section
  class="border-y border-stroke bg-surface-alt py-12"
  aria-labelledby="coverage-metrics"
>
  <div class="mx-auto max-w-6xl px-4">
    <h2 id="coverage-metrics" class="sr-only">Current published coverage</h2>
    <dl class="grid gap-7 text-center sm:grid-cols-2 lg:grid-cols-4">
      <div>
        <dt class="text-sm text-content-muted">Published election guides</dt>
        <dd class="mt-1 text-3xl font-bold text-content">
          {metrics.guides.toLocaleString()}
        </dd>
      </div>
      <div>
        <dt class="text-sm text-content-muted">Candidate profiles</dt>
        <dd class="mt-1 text-3xl font-bold text-content">
          {metrics.candidateProfiles.toLocaleString()}
        </dd>
      </div>
      <div>
        <dt class="text-sm text-content-muted">States represented</dt>
        <dd class="mt-1 text-3xl font-bold text-content">
          {metrics.statesRepresented}
        </dd>
      </div>
      <div>
        <dt class="text-sm text-content-muted">Research last updated</dt>
        <dd class="mt-1 text-xl font-bold text-content">
          {date(metrics.lastUpdated)}
        </dd>
      </div>
    </dl>
    <p class="mt-7 text-center text-xs text-content-subtle">
      Published-data snapshot: {date(metrics.snapshotDate)}. Counts describe
      Smarter.Vote coverage, not every contest on a ballot.
    </p>
  </div>
</section>
