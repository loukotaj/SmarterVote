<script lang="ts">
  import PolicySection from "$lib/components/support/PolicySection.svelte";
  import TrustPage from "$lib/components/support/TrustPage.svelte";
</script>

<TrustPage
  title="Corrections"
  description="How to report an error and how Smarter.Vote LLC reviews corrections."
  path="/corrections/"
>
  <PolicySection title="Report a possible error">
    <p>
      Include the page URL, candidate or contest, the specific statement at
      issue, and a reliable supporting source. Do not include sensitive personal
      information.
    </p>
    <p>
      Correction reports are filed as public GitHub issues so their status and
      resolution can be reviewed openly. A GitHub account is required.
    </p>
    <a
      href="https://github.com/SmarterVote/SmarterVote/issues/new/choose"
      target="_blank"
      rel="noopener noreferrer"
      class="inline-flex min-h-11 items-center justify-center rounded-lg bg-blue-600 px-5 py-2.5 font-semibold text-white transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
    >
      Report a correction on GitHub →
    </a>
  </PolicySection>
  <PolicySection title="What happens next">
    <p>
      Smarter.Vote LLC reviews the cited evidence and retains editorial control
      over the outcome. We may correct, clarify, add context, update sources, or
      determine that no change is warranted. Material updates should be
      reflected on the relevant page.
    </p>
    <p>
      We are a small early-stage organization and do not yet promise a response
      time, but election-sensitive and safety-related reports receive priority.
    </p>
  </PolicySection>
</TrustPage>
