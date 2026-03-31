<script lang="ts">
  import "../app.css";
  import { page, navigating } from "$app/stores";
  import { onMount } from "svelte";
  import { writable } from "svelte/store";

  const darkMode = writable(false);

  onMount(() => {
    const saved = localStorage.getItem("darkMode");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const enabled = saved !== null ? saved === "true" : prefersDark;
    darkMode.set(enabled);
    document.documentElement.classList.toggle("dark", enabled);
  });

  function toggleDark() {
    darkMode.update(d => {
      const next = !d;
      document.documentElement.classList.toggle("dark", next);
      localStorage.setItem("darkMode", String(next));
      return next;
    });
  }
</script>

<div class="min-h-screen bg-page">
  <!-- Navigation loading bar -->
  {#if $navigating}
    <div class="fixed top-0 left-0 right-0 z-50 h-0.5 overflow-hidden">
      <div class="h-full bg-blue-600 animate-[navprogress_1.2s_ease-in-out_infinite]"></div>
    </div>
  {/if}

  <!-- Navigation -->
  <nav class="bg-surface shadow-sm border-b border-stroke">
    <div class="container mx-auto px-4 py-3 max-w-7xl">
      <div class="flex items-center justify-between">
        <a href="/" class="text-xl sm:text-2xl font-bold text-blue-600 hover:text-blue-700">
          Smarter.vote
        </a>
        <div class="flex items-center gap-4 sm:gap-6 text-sm">
          <a href="/" class="text-content-muted hover:text-content {$page.url.pathname === '/' ? 'font-semibold text-content' : ''}">
            Home
          </a>
          <a href="/about" class="text-content-muted hover:text-content {$page.url.pathname === '/about' ? 'font-semibold text-content' : ''}">
            About
          </a>
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
        <p class="mb-2">© 2025 Smarter.vote. Analyzing public information to help voters make informed decisions.</p>
        <p class="text-xs text-content-subtle">Always verify information by visiting candidate websites directly. This tool provides analysis for informational purposes only.</p>
      </div>
    </div>
  </footer>
</div>
