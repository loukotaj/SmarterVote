<script lang="ts">
  const links = [
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
    <p class="mt-8 border-t border-stroke pt-5 text-xs text-content-subtle">
      © {new Date().getFullYear()} Smarter.Vote LLC. Not affiliated with any government
      or political campaign.
    </p>
  </div>
</footer>
