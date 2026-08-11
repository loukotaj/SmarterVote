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
      Current research focuses on national races. It is not a complete ballot
      guide and does not yet provide dependable coverage of state legislatures,
      local offices, judicial races, or ballot measures.
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

    <PolicySection title="How the research is made">
      <p>
        Automated research agents search public sources—including candidate
        statements, campaign websites, official records, voting databases, and
        reputable reporting—and organize the evidence into candidate summaries,
        issue positions, background, and race analysis. They are instructed to
        describe what candidates say and do without endorsing them.
      </p>
      <p>
        Source links remain attached to the research so readers can inspect the
        evidence directly. A source is not treated as neutral merely because it
        is linked: campaign material represents the candidate's own account,
        while records and reporting provide additional context.
      </p>
    </PolicySection>

    <PolicySection title="Evidence and confidence">
      <p>
        Confidence labels describe the strength of the available evidence—not
        the value of a candidate or policy. High confidence requires multiple
        corroborating sources or an official candidate position. Medium
        confidence requires at least one credible source. Low confidence marks
        information that is inferred, unverified, or unsupported by a source.
      </p>
      <p>
        “No public position found” means the research process looked for an
        attributable position and did not find one. It does not mean the
        candidate has no view, and it is different from an issue that has not
        yet been researched.
      </p>
    </PolicySection>

    <PolicySection title="Automated review and publication">
      <p>
        Separate AI models review the full race side by side for the correct
        candidate roster, internal consistency, source quality, completeness,
        background accuracy, and neutral treatment across candidates. Automated
        checks also look for broken sources, malformed polling, placeholders,
        and missing required research.
      </p>
      <p>
        The Automated Research Score combines the review models' scores and
        accounts for unresolved warnings. A failing score or an unresolved error
        blocks publication. This is automated editorial quality control, not a
        promise that every statement has been independently fact-checked by a
        human.
      </p>
    </PolicySection>

    <div id="forecast-methodology" class="scroll-mt-24">
      <PolicySection title="How forecasts work">
        <p>
          Race forecasts start with the published race record. They prefer
          candidate-level polling when it is available and otherwise weigh
          incumbency, party context, candidate strength, the documented race
          environment, and other evidence already gathered for the contest.
          Prediction-market signals may provide additional context, but they are
          never treated as ground truth.
        </p>
        <p>
          Each race forecast includes a rating, modeled win probability, key
          drivers, uncertainty, and supporting sources where the analysis relies
          on a specific external claim. Chamber forecasts combine those race
          probabilities with known holdover seats to calculate projected seats,
          seat-outcome distributions, and the chance of party control. For the
          2026 Senate forecast, a 50–50 result is counted as Republican control
          under the vice president tie-break assumption.
        </p>
      </PolicySection>
    </div>

    <PolicySection title="Limits and updates">
      <p>
        Sources can be incomplete, positions can change, and automated analysis
        can misunderstand nuance. Polls capture a period in time, and forecasts
        change as new evidence arrives. Forecasts are estimates—not election
        results, voting advice, or guarantees.
      </p>
    </PolicySection>

    <PolicySection title="Verification and corrections">
      <p>
        Use the linked evidence to check research claims, and rely on state and
        local election officials for registration, deadlines, voting methods,
        and official results. Report errors through our corrections process.
        Funding never determines findings, classifications, forecasts, or
        publication decisions.
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
