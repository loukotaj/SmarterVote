<script lang="ts">
  import type { IssueStance, Race } from "$lib/types";
  import { getIssueDisplayName } from "$lib/types";
  import { homepageResearchPreview } from "$lib/homepagePreview";

  export let race: Race | null = null;

  $: candidates = race
    ? race.candidates.filter((candidate) => !candidate.withdrawn).slice(0, 2)
    : [];
  $: commonIssues = race
    ? Object.keys(race.candidates[0]?.issues ?? {})
        .filter((issue) =>
          Boolean(
            race?.candidates[1]?.issues[
              issue as keyof (typeof race.candidates)[number]["issues"]
            ]
          )
        )
        .slice(0, 3)
    : [];
  $: displayTitle = race?.title ?? homepageResearchPreview.title;
  $: displayCandidates = commonIssues.length
    ? candidates
    : homepageResearchPreview.candidates;
  $: displayIssues = commonIssues.length
    ? commonIssues
    : Object.keys(homepageResearchPreview.candidates[0].issues);
  const stance = (candidateIndex: number, issue: string) =>
    race?.candidates[candidateIndex]?.issues[
      issue as keyof (typeof race.candidates)[number]["issues"]
    ] as IssueStance | undefined;
  const previewIssue = (
    candidate: (typeof homepageResearchPreview.candidates)[number],
    issue: string
  ) =>
    candidate.issues[issue as keyof typeof candidate.issues] as {
      stance: string;
      sources: number;
    };
</script>

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
          {displayTitle}
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
        <span class="block"
          >{displayCandidates[0]?.name ?? "Candidate profile"}</span
        >
        <span class="mt-1 block text-[10px] font-normal text-content-subtle"
          >{displayCandidates[0]?.party}</span
        >
      </div>
      <div class="border-b border-stroke p-3 font-bold text-content">
        <span class="block"
          >{displayCandidates[1]?.name ?? "Candidate profile"}</span
        >
        <span class="mt-1 block text-[10px] font-normal text-content-subtle"
          >{displayCandidates[1]?.party}</span
        >
      </div>
      {#if commonIssues.length}
        {#each commonIssues as issue}
          <div class="border-r border-stroke p-3 font-bold text-content">
            {getIssueDisplayName(issue)}
          </div>
          {#each candidates as _, candidateIndex}
            <div
              class:border-r={candidateIndex === 0}
              class="border-stroke p-3 leading-5 text-content-muted"
            >
              <span class="line-clamp-3"
                >{stance(candidateIndex, issue)?.stance}</span
              ><span
                class="mt-2 block font-semibold text-blue-600 dark:text-blue-400"
                >↗ {stance(candidateIndex, issue)?.sources.length ?? 0} source{(stance(
                  candidateIndex,
                  issue
                )?.sources.length ?? 0) === 1
                  ? ""
                  : "s"}</span
              >
            </div>
          {/each}
        {/each}
      {:else}
        {#each displayIssues as issue}
          <div class="border-r border-stroke p-3 font-bold text-content">
            {getIssueDisplayName(issue)}
          </div>
          {#each homepageResearchPreview.candidates as candidate, candidateIndex}
            <div
              class:border-r={candidateIndex === 0}
              class="border-stroke p-3 leading-5 text-content-muted"
            >
              <span class="line-clamp-3"
                >{previewIssue(candidate, issue).stance}</span
              ><span
                class="mt-2 block font-semibold text-blue-600 dark:text-blue-400"
                >↗ {previewIssue(candidate, issue).sources} source{previewIssue(
                  candidate,
                  issue
                ).sources === 1
                  ? ""
                  : "s"}</span
              >
            </div>
          {/each}
        {/each}
      {/if}
    </div>
    <div
      class="flex items-center gap-3 border-t border-stroke bg-blue-50/60 px-5 py-3 text-xs text-blue-900 dark:bg-blue-950/50 dark:text-blue-100"
    >
      <span class="h-2 w-2 rounded-full bg-amber-500" /><strong
        >Uncertainty noted:</strong
      >
      Grade {race?.validation_grade?.grade ?? homepageResearchPreview.grade} ·
      {race?.validation_grade?.score ?? homepageResearchPreview.score}/100
      review score.
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
    <p class="mt-2 text-xs font-semibold text-content">Published research</p>
    <p class="mt-1 truncate text-[10px] text-blue-600 dark:text-blue-400">
      {race?.updated_utc
        ? new Date(race.updated_utc).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
          })
        : new Date(homepageResearchPreview.updatedUtc).toLocaleDateString(
            "en-US",
            { month: "short", day: "numeric", year: "numeric" }
          )}
    </p>
  </div>
</div>
