<script lang="ts">
  import ContactCard from "$lib/components/support/ContactCard.svelte";
  import PolicySection from "$lib/components/support/PolicySection.svelte";
  import TrustPage from "$lib/components/support/TrustPage.svelte";

  const paymentsEnabled = import.meta.env.VITE_PAYMENTS_ENABLED === "true";
</script>

<TrustPage
  title="About Smarter.Vote"
  description="Smarter.Vote uses AI to help produce sourced election research so people can compare candidates and inspect the underlying evidence."
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

  <div id="ai-generated-content" class="scroll-mt-24">
    <PolicySection title="This site uses AI-generated content">
      <p class="font-semibold text-content">
        Much of the candidate and election research on Smarter.Vote is drafted,
        organized, classified, or summarized by artificial intelligence.
      </p>
      <p>
        This includes candidate summaries, issue-position comparisons,
        confidence labels, race analysis, and forecasts. Automated research and
        review systems work from public sources, but source links and automated
        checks do not guarantee that the resulting text is complete, current,
        neutral, or correct. Do not assume that every published statement has
        been individually fact-checked by a human.
      </p>
      <p>
        Smarter.Vote LLC chooses what systems to use and is responsible for what
        it publishes. Readers should inspect the cited evidence, compare it with
        official records and candidate statements, and report errors through the <a
          class="text-primary-600 underline dark:text-primary-500"
          href="/corrections/">corrections process</a
        >.
      </p>
    </PolicySection>
  </div>

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

  <div id="methodology" class="scroll-mt-24 space-y-6">
    <div class="pt-2">
      <p
        class="text-sm font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-500"
      >
        Our methodology
      </p>
      <p class="mt-2 leading-7">
        How Smarter.Vote researches, reviews, and presents election information.
      </p>
    </div>

    <PolicySection title="Research">
      <p>
        We gather public material such as candidate statements, campaign
        websites, official records, and reputable reporting. Automated tools
        help discover and organize evidence; they do not make endorsements.
      </p>
    </PolicySection>

    <PolicySection title="Review and publication">
      <p>
        We compare claims with their sources, flag conflicts, run consistency
        and quality checks, and publish citations and update dates. Confidence
        labels describe the available evidence, not the value of a candidate or
        policy.
      </p>
    </PolicySection>

    <PolicySection title="Limits">
      <p>
        Sources can be incomplete, positions can change, and automated analysis
        can misunderstand nuance. Current coverage focuses on national and
        federal races and is not a complete ballot. Forecasts are estimates—not
        election results, voting advice, or guarantees.
      </p>
    </PolicySection>

    <PolicySection title="Verify and correct">
      <p>
        Use the linked evidence and official election resources to verify
        important information. Funding never determines findings,
        classifications, forecasts, or publication decisions.
      </p>
    </PolicySection>
  </div>

  <PolicySection title="Accountability">
    <p>
      Smarter.Vote LLC is responsible for the site, its editorial decisions,
      privacy inquiries, corrections, partnerships, and any future refunds.
      Learn more about our
      <a
        class="text-primary-600 underline dark:text-primary-500"
        href="#methodology">methodology</a
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
    {#if paymentsEnabled}
      Smarter.Vote LLC accepts support through the
      <a
        class="text-primary-600 underline dark:text-primary-500"
        href="/support/">secure support page</a
      >. You can also support the individual developer separately through GitHub
      Sponsors.
    {:else}
      Smarter.Vote LLC support is not yet accepting payments. If you want to
      support the individual developer separately, visit
    {/if}
    <a
      class="text-primary-600 underline dark:text-primary-500"
      href="https://github.com/sponsors/loukotaj"
      target="_blank"
      rel="noopener noreferrer">Support the developer on GitHub</a
    >. GitHub Sponsors is personal support, not a contribution to Smarter.Vote
    LLC.
  </p>
</TrustPage>
