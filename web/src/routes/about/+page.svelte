<svelte:head>
  <title>About | Smarter.vote</title>
  <meta
    name="description"
    content="Learn about Smarter.vote's mission to provide unbiased candidate analysis from public, traceable sources to help voters make informed decisions."
  />
</svelte:head>

<div class="container mx-auto px-4 py-8 sm:py-12 max-w-4xl">
  <h1
    class="text-2xl sm:text-3xl lg:text-4xl font-bold text-content mb-6 sm:mb-8"
  >
    About Smarter.vote
  </h1>

  <div class="prose prose-lg max-w-none">
    <!-- Alpha Notice -->
    <div class="bg-amber-50 dark:bg-amber-950 border border-amber-300 dark:border-amber-800 rounded-lg px-4 py-3 mb-6 sm:mb-8 flex items-start gap-3">
      <svg class="w-5 h-5 text-amber-500 dark:text-amber-400 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
      </svg>
      <div>
        <p class="text-amber-800 dark:text-amber-200 font-semibold text-sm">Alpha — actively under development.</p>
        <p class="text-amber-700 dark:text-amber-300 text-sm mt-0.5">This site is in early development. Content is AI-generated and may contain errors, omissions, or outdated information. Always follow the source links provided and apply your own critical judgment — do not rely solely on the summaries shown here.</p>
      </div>
    </div>

    <div class="bg-surface rounded-lg shadow-sm p-4 sm:p-8 mb-6 sm:mb-8">
      <h2 class="text-xl sm:text-2xl font-semibold text-content mb-3 sm:mb-4">
        Our Mission
      </h2>
      <p class="text-content-muted leading-relaxed text-sm sm:text-base">
        Democracy works best when voters have access to clear, unbiased
        information about candidates and their positions. Smarter.vote uses
        automated research from public sources and presents candidate
        positions in an easy-to-understand format with traceable citations,
        helping voters make informed decisions based on the issues that
        matter most to them.
      </p>
    </div>

    <div class="bg-surface rounded-lg shadow-sm p-4 sm:p-8 mb-6 sm:mb-8">
      <h2 class="text-xl sm:text-2xl font-semibold text-content mb-3 sm:mb-4">
        How We Work
      </h2>
      <div class="space-y-3 sm:space-y-4">
        <div>
          <h3 class="text-base sm:text-lg font-semibold text-content mb-2">
            Source Discovery
          </h3>
          <p class="text-content-muted text-sm sm:text-base">
            We automatically discover and collect information from candidate
            websites, voting records, public speeches, position papers, and
            other publicly available sources.
          </p>
        </div>
        <div>
          <h3 class="text-base sm:text-lg font-semibold text-content mb-2">
            AI Analysis
          </h3>
          <p class="text-content-muted text-sm sm:text-base">
            Research agents (Claude, GPT, Gemini, Grok) independently
            analyze the collected information to extract candidate positions on
            key issues. This multi-model approach helps ensure accuracy and
            reduce bias.
          </p>
        </div>
        <div>
          <h3 class="text-base sm:text-lg font-semibold text-content mb-2">
            Transparency
          </h3>
          <p class="text-content-muted text-sm sm:text-base">
            Every position includes confidence ratings and links to the original
            sources, so you can verify the information yourself and understand
            how certain we are about each stance.
          </p>
        </div>
      </div>
    </div>

    <div class="bg-surface rounded-lg shadow-sm p-4 sm:p-8 mb-6 sm:mb-8">
      <h2 class="text-xl sm:text-2xl font-semibold text-content mb-3 sm:mb-4">
        Key Issues We Cover
      </h2>
      <div class="grid gap-3 sm:gap-4 sm:grid-cols-2">
        <ul class="space-y-1 sm:space-y-2 text-content-muted text-sm sm:text-base">
          <li>• Healthcare</li>
          <li>• Economy</li>
          <li>• Climate/Energy</li>
          <li>• Reproductive Rights</li>
          <li>• Immigration</li>
          <li>• Guns & Safety</li>
        </ul>
        <ul class="space-y-1 sm:space-y-2 text-content-muted text-sm sm:text-base">
          <li>• Foreign Policy</li>
          <li>• Social Justice</li>
          <li>• Education</li>
          <li>• Tech & AI</li>
          <li>• Election Reform</li>
          <li>• Local Issues</li>
        </ul>
      </div>
    </div>

    <div class="bg-surface rounded-lg shadow-sm p-4 sm:p-8 mb-6 sm:mb-8">
      <h2 class="text-xl sm:text-2xl font-semibold text-content mb-3 sm:mb-4">
        Important Disclaimers
      </h2>
      <div class="space-y-3 text-content-muted text-sm sm:text-base">
        <p>
          <strong>Verify Information:</strong> While we strive for accuracy, always
          verify information by visiting candidate websites directly. Candidate positions
          may evolve, and our analysis reflects information available at the time
          of processing.
        </p>
        <p>
          <strong>AI Limitations:</strong> AI analysis, while sophisticated, may
          occasionally misinterpret complex positions or nuanced statements. Confidence
          ratings help indicate our certainty level for each position.
        </p>
        <p>
          <strong>No Endorsements:</strong> Smarter.vote does not endorse candidates
          or political parties. Our goal is to present factual information to help
          you make your own informed decisions.
        </p>
        <p>
          <strong>Public Sources Only:</strong> We only analyze publicly available
          information. Private communications, internal documents, or off-the-record
          statements are not included in our analysis.
        </p>
      </div>
    </div>

    <div class="bg-surface rounded-lg shadow-sm p-4 sm:p-8 mb-6 sm:mb-8">
      <h2 class="text-xl sm:text-2xl font-semibold text-content mb-3 sm:mb-4">
        Who's Behind This?
      </h2>
      <p class="text-content-muted leading-relaxed text-sm sm:text-base mb-3">
        Smarter.vote is an independent, self-funded project — built and
        maintained by one person. Hosting and AI API costs come entirely out of
        pocket.
      </p>
      <p class="text-content-muted leading-relaxed text-sm sm:text-base">
        The long-term goal is to grow this into a non-profit with broader
        coverage and a team of contributors.
      </p>
    </div>

    <div class="bg-surface rounded-lg shadow-sm p-4 sm:p-8 mb-6 sm:mb-8">
      <h2 class="text-xl sm:text-2xl font-semibold text-content mb-3 sm:mb-4">
        Get Involved
      </h2>
      <div class="space-y-4">
        <div class="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h3 class="text-base font-semibold text-blue-900 mb-1">
            🗳️ Request a race or report an issue
          </h3>
          <p class="text-blue-800 text-sm mb-3">
            Want a race added? Spotted something inaccurate? Open a GitHub issue
            — no sponsoring required. The project is open source and community
            input is always welcome.
          </p>
          <a
            href="https://github.com/loukotaj/SmarterVote/issues/new/choose"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-lg transition-colors duration-200 text-sm"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M10 0C4.477 0 0 4.484 0 10.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0110 4.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.203 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.942.359.31.678.921.678 1.856 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0020 10.017C20 4.484 15.522 0 10 0z" clip-rule="evenodd" />
            </svg>
            Open an Issue
          </a>
        </div>

          <div class="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
          <h3 class="text-base font-semibold text-amber-900 dark:text-amber-200 mb-1">
            ❤️ Support development
          </h3>
          <p class="text-amber-800 dark:text-amber-300 text-sm mb-4">
            Smarter.vote is free and open-source. If you find it useful,
            sponsoring helps cover API and hosting costs and keeps the project
            running.
          </p>
          <div class="flex justify-center">
            <iframe
              src="https://github.com/sponsors/loukotaj/card"
              title="Sponsor loukotaj"
              height="225"
              width="600"
              style="border: 0; max-width: 100%;"
            ></iframe>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
