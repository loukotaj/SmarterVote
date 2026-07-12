<script lang="ts">
  import ContactCard from "$lib/components/support/ContactCard.svelte";
  import PolicySection from "$lib/components/support/PolicySection.svelte";
  import TrustPage from "$lib/components/support/TrustPage.svelte";
</script>

<TrustPage
  title="Methodology"
  description="How Smarter.Vote researches, reviews, and presents election information."
  path="/methodology/"
>
  <PolicySection title="Research">
    <p>
      We gather public material such as candidate statements, campaign websites,
      official records, and reputable reporting. Automated tools help discover
      and organize evidence; they do not make endorsements.
    </p>
  </PolicySection>
  <PolicySection title="Review and publication">
    <p>
      We compare claims with their sources, flag conflicts, run consistency and
      quality checks, and publish citations and update dates. Confidence labels
      describe the available evidence, not the value of a candidate or policy.
    </p>
  </PolicySection>
  <PolicySection title="Limits">
    <p>
      Sources can be incomplete, positions can change, and automated analysis
      can misunderstand nuance. Current coverage focuses on national and federal
      races and is not a complete ballot. Forecasts are estimates—not election
      results, voting advice, or guarantees.
    </p>
  </PolicySection>
  <PolicySection title="Verify and correct">
    <p>
      Use the linked evidence and official election resources to verify
      important information. Funding never determines findings, classifications,
      forecasts, or publication decisions.
    </p>
  </PolicySection>
  <ContactCard
    subject="Methodology question"
    label="Ask about our methodology"
  />
</TrustPage>
