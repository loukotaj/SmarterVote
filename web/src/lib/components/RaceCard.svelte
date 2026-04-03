<script lang="ts">
  import type { RaceSummary } from "$lib/types";
  import { partyAbbr, partyRing, partyInitialBg } from "$lib/utils/party";

  export let race: RaceSummary;

  function formatDate(dateString: string): string {
    const d = new Date(dateString);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }

  function getOfficeBadge(office: string | undefined): { label: string; cls: string } {
    if (!office) return { label: "Race", cls: "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200" };
    const o = office.toLowerCase();
    if (o.includes("senate")) return { label: "Senate", cls: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200" };
    if (o.includes("governor") || o.includes("gubernatorial")) return { label: "Governor", cls: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200" };
    if (o.includes("house") || o.includes("representative")) return { label: "House", cls: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200" };
    if (o.includes("secretary")) return { label: "Sec. of State", cls: "bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200" };
    if (o.includes("attorney")) return { label: "Atty. General", cls: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200" };
    // Truncate long office names
    return { label: office.length > 22 ? office.slice(0, 22) + "…" : office, cls: "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200" };
  }

  $: badge = getOfficeBadge(race.office);

  let imageErrors: Set<string> = new Set();
  function handleImageError(name: string) {
    imageErrors = new Set([...imageErrors, name]);
  }
</script>

<a
  href="/races/{race.id}"
  class="group block bg-surface rounded-xl border border-stroke hover:border-blue-400 hover:shadow-md transition-all duration-200 overflow-hidden"
>
  <!-- Card header: badges + date -->
  <div class="px-4 pt-4 pb-3 flex flex-wrap items-center gap-2">
    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold {badge.cls}">
      {badge.label}
    </span>
    {#if race.jurisdiction}
      <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
        {race.jurisdiction}
      </span>
    {/if}
    <span class="ml-auto text-xs text-content-subtle whitespace-nowrap">
      {formatDate(race.election_date)}
    </span>
  </div>

  <!-- Race title -->
  <div class="px-4 pb-3">
    <h3 class="text-sm font-semibold text-content group-hover:text-blue-600 transition-colors leading-snug line-clamp-2 capitalize">
      {race.title ?? `${race.office ?? "Race"} — ${race.jurisdiction ?? ""}`}
    </h3>
  </div>

  <!-- Candidate avatars + names -->
  <div class="px-4 pb-4">
    <div class="flex flex-wrap gap-3">
      {#each race.candidates as candidate}
        <div class="flex items-center gap-2 min-w-0">
          <!-- Avatar -->
          <div class="relative flex-shrink-0">
            {#if candidate.image_url && !imageErrors.has(candidate.name)}
              <img
                src={candidate.image_url}
                alt={candidate.name}
                class="w-9 h-9 rounded-full object-cover ring-2 {partyRing(candidate.party)}"
                loading="lazy"
                on:error={() => handleImageError(candidate.name)}
              />
            {:else}
              <div
                class="w-9 h-9 rounded-full ring-2 {partyRing(candidate.party)} {partyInitialBg(candidate.party)} flex items-center justify-center text-white text-sm font-bold"
                aria-hidden="true"
              >
                {candidate.name ? candidate.name[0].toUpperCase() : "?"}
              </div>
            {/if}
          </div>
          <!-- Name + party -->
          <div class="min-w-0">
            <p class="text-xs font-medium text-content truncate max-w-[110px]">{candidate.name}</p>
            {#if candidate.party}
              <p class="text-xs text-content-subtle">{partyAbbr(candidate.party)}</p>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  </div>
</a>
