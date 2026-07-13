<script lang="ts">
  const links = [
    { href: "/about/", label: "About" },
    { href: "/about/#methodology", label: "Methodology" },
    { href: "/partners/", label: "Partners" },
    { href: "/corrections/", label: "Corrections" },
    {
      href: "/funding-and-editorial-independence/",
      label: "Funding & independence",
    },
    { href: "/privacy/", label: "Privacy" },
    { href: "/terms/", label: "Terms" },
    {
      href: "https://github.com/loukotaj/SmarterVote",
      label: "GitHub",
      external: true,
    },
  ];
</script>

<footer class="mt-12 border-t border-stroke bg-surface sm:mt-16">
  <div class="container mx-auto max-w-7xl px-4 py-8">
    <div
      class="flex flex-col gap-6 md:flex-row md:items-start md:justify-between"
    >
      <div class="max-w-xl">
        <a href="/" class="font-bold text-blue-600">Smarter.Vote</a>
        <p class="mt-2 text-sm text-content-muted">
          Independent, sourced election research for informational purposes.
          Always confirm voting information with official election authorities.
        </p>
      </div>
      <nav
        class="flex max-w-xl flex-wrap gap-x-5 gap-y-3 text-sm"
        aria-label="Footer navigation"
      >
        {#each links as link}
          <a
            href={link.href}
            target={link.external ? "_blank" : undefined}
            rel={link.external ? "noopener noreferrer" : undefined}
            class="text-content-muted hover:text-content">{link.label}</a
          >
        {/each}
      </nav>
    </div>
    <div
      class="mt-7 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100"
      role="note"
      aria-label="AI-generated content notice"
    >
      <strong>AI-generated content notice:</strong> Candidate summaries,
      comparisons, classifications, and forecasts may be generated with AI and
      can be incomplete, incorrect, or outdated. Check the linked evidence and
      official election sources before relying on them.
      <a
        href="/about/#ai-generated-content"
        class="ml-1 font-semibold underline underline-offset-2 hover:no-underline"
        >How Smarter.Vote uses AI</a
      >.
    </div>
    <p class="mt-8 border-t border-stroke pt-5 text-xs text-content-subtle">
      © {new Date().getFullYear()} Smarter.Vote LLC. Not affiliated with any government
      or political campaign.
    </p>
  </div>
</footer>
