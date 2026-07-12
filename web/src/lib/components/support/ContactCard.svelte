<script lang="ts">
  export let subject: string;
  export let label = "Email Smarter.Vote";
  export let intro = "Contact Smarter.Vote LLC at";

  const email = "SmarterDotVote@gmail.com";
  $: href = `mailto:${email}?subject=${encodeURIComponent(subject)}`;
</script>

<div
  class="rounded-xl border border-primary-500/30 bg-primary-50 p-5 dark:bg-blue-950/20"
>
  <p class="text-content">
    {intro}
    <a
      class="font-medium text-primary-600 underline hover:no-underline dark:text-primary-500"
      {href}>{email}</a
    >.
  </p>
  <a
    class="mt-4 inline-flex rounded-lg bg-primary-600 px-4 py-2 font-semibold text-white transition hover:bg-primary-700"
    {href}>{label}</a
  >
</div>
