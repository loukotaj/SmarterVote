<script lang="ts">
  import ContactCard from "$lib/components/support/ContactCard.svelte";
  import PolicySection from "$lib/components/support/PolicySection.svelte";
  import TrustPage from "$lib/components/support/TrustPage.svelte";
</script>

<TrustPage
  title="Partner with Smarter.Vote"
  description="Information for newsrooms, universities, civic organizations, grantmakers, sponsors, and data partners."
  path="/partners/"
>
  <PolicySection title="Ways to collaborate">
    <p>
      Smarter.Vote LLC welcomes conversations about election-data access, civic
      and academic collaboration, grants, newsroom use, accessibility, and
      program-level sponsorship. We are not yet offering a self-service
      institutional payment or inquiry portal.
    </p>
  </PolicySection>
  <PolicySection title="Use and cite our research">
    <p>
      Newsrooms, libraries, educators, researchers, and civic organizations may
      link directly to a race, candidate, or comparison page. Please credit
      Smarter.Vote and link to the exact page so readers can inspect its cited
      evidence and update date.
    </p>
    <p>
      A machine-readable <a
        class="text-primary-600 underline dark:text-primary-500"
        href="/summaries.json">public race index</a
      > is available for coverage discovery. Contact us before bulk republication
      or embedding so we can agree on attribution, update expectations, and any source-specific
      limitations.
    </p>
  </PolicySection>
  <PolicySection title="Before you contact us">
    <p>
      Briefly identify your organization, proposed collaboration, timing,
      geography, and the minimum contact details needed to reply. Do not email
      confidential data without first agreeing on a secure channel.
    </p>
    <p>
      Institutional relationships require written scope and independence terms.
      Funding may support a published, standards-based coverage priority, but
      may not influence findings, sources, classifications, forecasts, or
      publication decisions. Contributions to Smarter.Vote LLC are not
      tax-deductible.
    </p>
  </PolicySection>
  <ContactCard
    subject="Partnership inquiry: [organization]"
    label="Start a partnership conversation"
  />
</TrustPage>
