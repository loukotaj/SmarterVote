<script lang="ts">
  import "../app.css";
  import { page } from "$app/stores";
</script>

<div class="min-h-screen bg-gray-50">
  <!-- Navigation -->
  <nav class="bg-white shadow-sm border-b border-gray-200">
    <div class="container mx-auto px-4 py-3 max-w-7xl">
      <div class="flex items-center justify-between">
        <a
          href="/"
          class="text-2xl font-bold text-blue-600 hover:text-blue-700"
        >
          Smarter.vote
        </a>
        <div class="flex items-center gap-6 text-sm">
          <a
            href="/"
            class="text-gray-600 hover:text-gray-900 {$page.url.pathname === '/'
              ? 'font-semibold text-gray-900'
              : ''}"
          >
            Home
          </a>
          <a
            href="/about"
            class="text-gray-600 hover:text-gray-900 {$page.url.pathname ===
            '/about'
              ? 'font-semibold text-gray-900'
              : ''}"
          >
            About
          </a>
        </div>
      </div>
    </div>
  </nav>

  <!-- Main Content -->
  <main>
    <slot />
  </main>

  <!-- Footer -->
  <footer class="bg-white border-t border-gray-200 mt-16">
    <div class="container mx-auto px-4 py-8 max-w-7xl">
      <div class="text-center text-gray-600 text-sm">
        <p class="mb-2">
          © 2025 Smarter.vote. Analyzing public information to help voters make
          informed decisions.
        </p>
        <p class="text-xs text-gray-500">
          Always verify information by visiting candidate websites directly.
          This tool provides analysis for informational purposes only.
        </p>
      </div>
    </div>
  </footer>
</div>
