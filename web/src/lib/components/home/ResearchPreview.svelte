<script lang="ts">
  import type { IssueStance, Race } from "$lib/types";
  import { getIssueDisplayName } from "$lib/types";
  export let race: Race;
  const candidates = race.candidates
    .filter((candidate) => !candidate.withdrawn)
    .slice(0, 2);
  const issueNames = Object.keys(candidates[0]?.issues ?? {})
    .filter(
      (issue) =>
        candidates[1]?.issues[issue as keyof (typeof candidates)[1]["issues"]]
    )
    .slice(0, 3);
  const position = (candidateIndex: number, issue: string) =>
    candidates[candidateIndex].issues[
      issue as keyof (typeof candidates)[number]["issues"]
    ] as IssueStance | undefined;
</script>

<section class="py-14 sm:py-20" aria-labelledby="preview-heading">
  <div class="mx-auto max-w-6xl px-4">
    <p
      class="text-sm font-semibold uppercase tracking-widest text-blue-600 dark:text-blue-400"
    >
      Inside a guide
    </p>
    <div class="mt-2 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 id="preview-heading" class="text-3xl font-bold text-content">
          {race.title ?? race.office}
        </h2>
        <p class="mt-2 text-sm text-content-muted">
          Updated {new Date(race.updated_utc).toLocaleDateString("en-US", {
            month: "long",
            day: "numeric",
            year: "numeric",
          })}
        </p>
      </div>
      <a
        href="/races/{race.id}/compare/"
        class="font-semibold text-blue-600 hover:underline dark:text-blue-400"
        >See the full comparison</a
      >
    </div>
    <div
      class="mt-7 overflow-x-auto rounded-2xl border border-stroke bg-surface"
    >
      <table class="w-full min-w-[680px] text-left text-sm">
        <thead
          ><tr class="border-b border-stroke"
            ><th class="p-4 text-content-muted">Issue</th
            >{#each candidates as candidate}<th class="p-4 text-content"
                >{candidate.name}<span
                  class="block text-xs font-normal text-content-subtle"
                  >{candidate.party ?? "Party not listed"}</span
                ></th
              >{/each}</tr
          ></thead
        >
        <tbody
          >{#each issueNames as issue}<tr
              class="border-b border-stroke last:border-0"
              ><th class="p-4 align-top font-semibold text-content"
                >{getIssueDisplayName(issue)}</th
              >{#each candidates as _, candidateIndex}{#if position(candidateIndex, issue)}<td
                    class="p-4 align-top text-content-muted"
                    ><p class="line-clamp-3">
                      {position(candidateIndex, issue)?.stance}
                    </p>
                    <div class="mt-2 flex gap-3 text-xs">
                      <span class="capitalize text-content-subtle"
                        >{position(candidateIndex, issue)?.confidence} confidence</span
                      >{#if position(candidateIndex, issue)?.sources[0]}<a
                          class="text-blue-600 hover:underline dark:text-blue-400"
                          href={position(candidateIndex, issue)?.sources[0].url}
                          target="_blank"
                          rel="noopener noreferrer">Source</a
                        >{/if}
                    </div></td
                  >{/if}{/each}</tr
            >{/each}</tbody
        >
      </table>
    </div>
  </div>
</section>
