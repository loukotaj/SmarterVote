<script lang="ts">
  import "../app.css";
  import { page, navigating } from "$app/stores";
  import { onMount } from "svelte";
  import { writable } from "svelte/store";
  import { getRaceSummaries } from "$lib/api";
  import type { RaceSummary } from "$lib/types";
  import { goto } from "$app/navigation";
  import { candidateSlug } from "$lib/utils/format";

  const darkMode = writable(false);
  let isAuthenticated = false;

  // Global search autocomplete state
  let races: RaceSummary[] = [];
  let headerQuery = "";
  let showSuggestions = false;
  let matchingCandidates: { name: string; party?: string; raceId: string; raceTitle: string }[] = [];
  let matchingRaces: { id: string; title: string; office?: string; state?: string }[] = [];
  let activeIndex = -1;
  let searchContainer: HTMLElement;

  onMount(async () => {
    const saved = localStorage.getItem("darkMode");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const enabled = saved !== null ? saved === "true" : prefersDark;
    darkMode.set(enabled);
    document.documentElement.classList.toggle("dark", enabled);

    // Check auth state silently — don't prompt login, just detect if already authenticated
    try {
      const { getAuth0Client, isAuthSkipped } = await import("$lib/auth");
      if (isAuthSkipped()) {
        isAuthenticated = true;
      } else {
        const auth0 = await getAuth0Client();
        isAuthenticated = await auth0.isAuthenticated();
      }
    } catch {
      isAuthenticated = false;
    }

    // Load race summaries for autocomplete suggestions
    try {
      races = await getRaceSummaries();
    } catch (e) {
      console.error("Failed to load race summaries for navbar search autocomplete:", e);
    }
  });

  function toggleDark() {
    darkMode.update(d => {
      const next = !d;
      document.documentElement.classList.toggle("dark", next);
      localStorage.setItem("darkMode", String(next));
      return next;
    });
  }

  // Sync search input with URL search parameter on the landing page
  let lastHeaderQ = "";
  $: {
    if ($page.url.pathname === "/") {
      const q = $page.url.searchParams.get("q") || "";
      if (q !== lastHeaderQ) {
        lastHeaderQ = q;
        headerQuery = q;
      }
    } else {
      lastHeaderQ = "";
    }
  }

  function handleSearchInput() {
    updateSuggestions();

    // If on homepage, sync input to URL query param in real time
    if ($page.url.pathname === "/") {
      const q = headerQuery.trim();
      lastHeaderQ = q;
      const params = new URLSearchParams($page.url.searchParams);
      if (q) {
        params.set("q", q);
      } else {
        params.delete("q");
      }
      goto(`/?${params.toString()}`, { replaceState: true, keepFocus: true, noScroll: true });
    }
  }

  function updateSuggestions() {
    activeIndex = -1;
    const q = headerQuery.trim().toLowerCase();
    if (!q) {
      matchingCandidates = [];
      matchingRaces = [];
      return;
    }

    const matchedRacesList: typeof matchingRaces = [];
    const matchedCandsList: typeof matchingCandidates = [];

    races.forEach((race) => {
      const titleMatch = race.title?.toLowerCase().includes(q);
      const officeMatch = race.office?.toLowerCase().includes(q);
      const stateMatch = race.state?.toLowerCase().includes(q);
      const jurMatch = race.jurisdiction?.toLowerCase().includes(q);

      if (titleMatch || officeMatch || stateMatch || jurMatch) {
        matchedRacesList.push({
          id: race.id,
          title: race.title || race.id,
          office: race.office,
          state: race.state
        });
      }

      race.candidates.forEach((cand) => {
        if (cand.name.toLowerCase().includes(q) || cand.party?.toLowerCase().includes(q)) {
          matchedCandsList.push({
            name: cand.name,
            party: cand.party,
            raceId: race.id,
            raceTitle: race.title || race.id
          });
        }
      });
    });

    // Limit to top 5 results for clean display
    matchingRaces = matchedRacesList.slice(0, 5);
    matchingCandidates = matchedCandsList.slice(0, 5);
    showSuggestions = true;
  }

  function selectRace(raceId: string) {
    showSuggestions = false;
    headerQuery = "";
    goto(`/races/${raceId}`);
  }

  function selectCandidate(raceId: string, candidateName: string) {
    showSuggestions = false;
    headerQuery = "";
    goto(`/races/${raceId}/${candidateSlug(candidateName)}`);
  }

  function clearSearch() {
    headerQuery = "";
    lastHeaderQ = "";
    matchingCandidates = [];
    matchingRaces = [];
    showSuggestions = false;

    if ($page.url.pathname === "/") {
      const params = new URLSearchParams($page.url.searchParams);
      params.delete("q");
      goto(`/?${params.toString()}`, { replaceState: true, keepFocus: true, noScroll: true });
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    const total = matchingRaces.length + matchingCandidates.length;

    if (e.key === "Enter") {
      e.preventDefault();
      if (activeIndex >= 0 && activeIndex < total) {
        if (activeIndex < matchingRaces.length) {
          selectRace(matchingRaces[activeIndex].id);
        } else {
          const candIndex = activeIndex - matchingRaces.length;
          const candidate = matchingCandidates[candIndex];
          selectCandidate(candidate.raceId, candidate.name);
        }
      } else if (headerQuery.trim()) {
        showSuggestions = false;
        const q = headerQuery.trim();
        goto(`/?q=${encodeURIComponent(q)}`);
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (total > 0) {
        activeIndex = (activeIndex + 1) % total;
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (total > 0) {
        activeIndex = (activeIndex - 1 + total) % total;
      }
    } else if (e.key === "Escape") {
      showSuggestions = false;
    }
  }

  function handleWindowClick(e: MouseEvent) {
    if (searchContainer && !searchContainer.contains(e.target as Node)) {
      showSuggestions = false;
    }
  }
</script>

<svelte:window on:click={handleWindowClick} />

<div class="min-h-screen bg-page overflow-x-hidden">
  <!-- Navigation loading bar -->
  {#if $navigating}
    <div class="fixed top-0 left-0 right-0 z-50 h-0.5 overflow-hidden">
      <div class="h-full bg-blue-600 animate-[navprogress_1.2s_ease-in-out_infinite]"></div>
    </div>
  {/if}

  <!-- Navigation -->
  <nav class="bg-surface shadow-sm border-b border-stroke">
    <div class="container mx-auto px-4 py-3 max-w-7xl">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <!-- Top Row (Logo & Navigation/Toggle on mobile) -->
        <div class="flex items-center justify-between w-full md:w-auto">
          <a href="/" class="text-xl sm:text-2xl font-bold text-blue-600 hover:text-blue-700 whitespace-nowrap">
            Smarter.vote
          </a>
          <!-- Navigation links on mobile (hidden on desktop) -->
          <div class="flex items-center gap-3 text-sm md:hidden">
            <a href="/" class="text-content-muted hover:text-content {$page.url.pathname === '/' ? 'font-semibold text-content' : ''}">
              Home
            </a>
            <a href="/about" class="text-content-muted hover:text-content {$page.url.pathname === '/about' ? 'font-semibold text-content' : ''}">
              About
            </a>
            {#if isAuthenticated}
              <a href="/admin" class="text-content-muted hover:text-content {$page.url.pathname.startsWith('/admin') ? 'font-semibold text-content' : ''}">
                Admin
              </a>
            {/if}
            <button
              on:click={toggleDark}
              class="p-1.5 rounded-lg text-content-subtle hover:text-content hover:bg-surface-alt transition-colors"
              aria-label="Toggle dark mode"
              title={$darkMode ? "Switch to light mode" : "Switch to dark mode"}
            >
              {#if $darkMode}
                <svg class="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707M17.657 17.657l-.707-.707M6.343 6.343l-.707-.707M12 8a4 4 0 100 8 4 4 0 000-8z" />
                </svg>
              {:else}
                <svg class="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
              {/if}
            </button>
          </div>
        </div>

        <!-- Global Search Bar in Header -->
        <div class="relative w-full md:max-w-xs lg:max-w-md" bind:this={searchContainer}>
          <div class="relative shadow-sm hover:shadow-md transition-shadow duration-300 rounded-full">
            <div class="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
              <svg class="h-4 w-4 text-content-subtle" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <input
              type="text"
              bind:value={headerQuery}
              on:input={handleSearchInput}
              on:focus={() => showSuggestions = true}
              on:keydown={handleKeydown}
              placeholder="Search candidates, races, states..."
              class="block w-full pl-9 pr-8 py-1.5 border border-stroke rounded-full text-xs sm:text-sm bg-surface-alt placeholder-content-subtle focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-content transition-all duration-300"
            />
            {#if headerQuery.trim()}
              <button
                on:click={clearSearch}
                class="absolute inset-y-0 right-0 pr-2.5 flex items-center text-content-subtle hover:text-content transition-colors"
                aria-label="Clear search query"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            {/if}
          </div>

          <!-- Suggestions Dropdown -->
          {#if showSuggestions && (matchingRaces.length > 0 || matchingCandidates.length > 0)}
            <div class="absolute top-full left-0 right-0 mt-2 bg-surface border border-stroke rounded-xl shadow-lg z-50 max-h-96 overflow-y-auto py-2 divide-y divide-stroke backdrop-blur-md bg-surface/95">
              {#if matchingRaces.length > 0}
                <div class="p-1.5">
                  <div class="text-[10px] font-semibold text-content-subtle px-2.5 py-1 uppercase tracking-wider">Races</div>
                  {#each matchingRaces as race, i}
                    <button
                      on:click={() => selectRace(race.id)}
                      class="w-full text-left px-2.5 py-1.5 rounded-lg text-xs transition-colors flex flex-col gap-0.5
                        {i === activeIndex ? 'bg-surface-alt text-primary font-medium' : 'text-content hover:bg-surface-alt/60'}"
                    >
                      <span class="truncate">{race.title}</span>
                      <span class="text-[10px] text-content-subtle truncate">{race.office || ''} {race.state ? `· ${race.state}` : ''}</span>
                    </button>
                  {/each}
                </div>
              {/if}

              {#if matchingCandidates.length > 0}
                <div class="p-1.5">
                  <div class="text-[10px] font-semibold text-content-subtle px-2.5 py-1 uppercase tracking-wider">Candidates</div>
                  {#each matchingCandidates as cand, i}
                    {@const itemIndex = matchingRaces.length + i}
                    <button
                      on:click={() => selectCandidate(cand.raceId, cand.name)}
                      class="w-full text-left px-2.5 py-1.5 rounded-lg text-xs transition-colors flex flex-col gap-0.5
                        {itemIndex === activeIndex ? 'bg-surface-alt text-primary font-medium' : 'text-content hover:bg-surface-alt/60'}"
                    >
                      <span class="truncate">{cand.name}</span>
                      <span class="text-[10px] text-content-subtle truncate">{cand.party || ''} · {cand.raceTitle}</span>
                    </button>
                  {/each}
                </div>
              {/if}
            </div>
          {/if}
        </div>

        <!-- Navigation Links (desktop) -->
        <div class="hidden md:flex items-center gap-4 sm:gap-6 text-sm">
          <a href="/" class="text-content-muted hover:text-content {$page.url.pathname === '/' ? 'font-semibold text-content' : ''}">
            Home
          </a>
          <a href="/about" class="text-content-muted hover:text-content {$page.url.pathname === '/about' ? 'font-semibold text-content' : ''}">
            About
          </a>
          {#if isAuthenticated}
            <a href="/admin" class="text-content-muted hover:text-content {$page.url.pathname.startsWith('/admin') ? 'font-semibold text-content' : ''}">
              Admin
            </a>
          {/if}
          <!-- Dark mode toggle -->
          <button
            on:click={toggleDark}
            class="p-2 rounded-lg text-content-subtle hover:text-content hover:bg-surface-alt transition-colors"
            aria-label="Toggle dark mode"
            title={$darkMode ? "Switch to light mode" : "Switch to dark mode"}
          >
            {#if $darkMode}
              <!-- Sun icon -->
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707M17.657 17.657l-.707-.707M6.343 6.343l-.707-.707M12 8a4 4 0 100 8 4 4 0 000-8z" />
              </svg>
            {:else}
              <!-- Moon icon -->
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            {/if}
          </button>
        </div>
      </div>
    </div>
  </nav>

  <!-- Main Content -->
  <main>
    <slot />
  </main>

  <!-- Footer -->
  <footer class="bg-surface border-t border-stroke mt-12 sm:mt-16">
    <div class="container mx-auto px-4 py-6 sm:py-8 max-w-7xl">
      <div class="text-center text-content-muted text-sm">
        <p class="mb-2">© {new Date().getFullYear()} Smarter.vote. Analyzing public information to help voters make informed decisions.</p>
        <p class="text-xs text-content-subtle">Always verify information by visiting candidate websites directly. This tool provides analysis for informational purposes only.</p>
        <div class="mt-4">
          <a
            href="https://github.com/sponsors/smartervote"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-pink-300 dark:border-pink-700 text-pink-600 dark:text-pink-400 text-xs font-medium hover:bg-pink-50 dark:hover:bg-pink-950 transition-colors"
          >
            <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
            </svg>
            Sponsor
          </a>
        </div>
      </div>
    </div>
  </footer>
</div>
