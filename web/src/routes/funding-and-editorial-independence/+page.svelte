<script lang="ts">
  import ContactCard from "$lib/components/support/ContactCard.svelte";
  import PolicySection from "$lib/components/support/PolicySection.svelte";
  import TrustPage from "$lib/components/support/TrustPage.svelte";
</script>

<TrustPage
  title="Funding and editorial independence"
  description="The rules separating Smarter.Vote funding from its election research and publication decisions."
  path="/funding-and-editorial-independence/"
>
  <PolicySection title="Editorial control">
    <p>
      Smarter.Vote LLC retains final authority over research methods, sources,
      findings, confidence labels, forecasts, corrections, and publication.
      Financial support never guarantees coverage or favorable treatment.
    </p>
  </PolicySection>
  <PolicySection title="Funding we will not accept">
    <p>
      We will not accept institutional funding from political candidates or
      campaigns, political parties, PACs, ballot committees, foreign political
      actors, undisclosed institutional funders, or anyone conditioning payment
      on an editorial outcome.
    </p>
    <p>
      We may also decline funding that creates a material conflict, threatens
      reader trust, or cannot be disclosed appropriately. These rules apply even
      when funding would otherwise expand coverage.
    </p>
  </PolicySection>
  <PolicySection title="Priorities, disclosure, and recognition">
    <p>
      Funding may help prioritize a geography or coverage category only through
      published quality standards; it cannot change what the research says.
      Individual recognition will be private by default and opt-in.
      Institutional relationships should be disclosed at the program level with
      the sponsor, purpose, and an amount band once those bands receive
      appropriate professional review.
    </p>
    <p>
      Until disclosure bands and exceptions are approved, Smarter.Vote LLC
      should use specific written agreements and avoid promising anonymity or
      public recognition.
    </p>
  </PolicySection>
  <PolicySection title="Support is not a charitable donation">
    <p>
      Smarter.Vote LLC is not presenting itself as a nonprofit or tax-exempt
      charity. Contributions are not tax-deductible. Supporter allocation
      choices are nonbinding preferences unless a written agreement expressly
      creates a restriction.
    </p>
  </PolicySection>
  <ContactCard subject="Funding independence question" />
</TrustPage>
