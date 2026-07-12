<script lang="ts">
  import ContactCard from "$lib/components/support/ContactCard.svelte";
  import PolicySection from "$lib/components/support/PolicySection.svelte";
  import TrustPage from "$lib/components/support/TrustPage.svelte";
</script>

<TrustPage
  title="About Smarter.Vote"
  description="Smarter.Vote helps people compare candidates using sourced, reviewable election research."
  path="/about/"
>
  <PolicySection title="Our purpose">
    <p>
      Smarter.Vote makes public information about candidates easier to compare.
      Research pages link back to their sources, show uncertainty, and give
      readers a starting point for their own verification. Smarter.Vote does not
      endorse candidates or parties.
    </p>
  </PolicySection>

  <PolicySection title="What is available today">
    <p>
      Smarter.Vote is an early-stage service operated by Smarter.Vote LLC.
      Current research focuses on national and federal elections. It is not a
      complete ballot guide and does not yet provide dependable state, local,
      judicial, or ballot-measure coverage.
    </p>
    <p>
      Automated tools assist with research and review, but they can miss context
      or make mistakes. Readers should check linked sources and official
      election authorities before acting.
    </p>
  </PolicySection>

  <PolicySection title="Accountability">
    <p>
      Smarter.Vote LLC is responsible for the site, its editorial decisions,
      privacy inquiries, corrections, partnerships, and any future refunds.
      Learn more in our
      <a
        class="text-primary-600 underline dark:text-primary-500"
        href="/methodology/">methodology</a
      >,
      <a
        class="text-primary-600 underline dark:text-primary-500"
        href="/corrections/">corrections policy</a
      >, and
      <a
        class="text-primary-600 underline dark:text-primary-500"
        href="/funding-and-editorial-independence/"
        >funding and editorial independence policy</a
      >.
    </p>
  </PolicySection>

  <ContactCard subject="General question for Smarter.Vote LLC" />

  <p class="text-center text-sm">
    Smarter.Vote LLC support is not yet accepting payments. If you want to
    support the individual developer separately, visit
    <a
      class="text-primary-600 underline dark:text-primary-500"
      href="https://github.com/sponsors/loukotaj"
      target="_blank"
      rel="noopener noreferrer">Support the developer on GitHub</a
    >. This is personal support, not a contribution to Smarter.Vote LLC.
  </p>
</TrustPage>
