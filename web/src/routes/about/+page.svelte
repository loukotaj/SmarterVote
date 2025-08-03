<svelte:head>
  <title>About | Smarter.vote</title>
  <meta
    name="description"
    content="Learn about Smarter.vote's mission to provide unbiased, AI-powered candidate analysis to help voters make informed decisions."
  />
</svelte:head>

<div class="container mx-auto px-4 py-12 max-w-4xl">
  <h1 class="text-4xl font-bold text-gray-900 mb-8">About Smarter.vote</h1>

  <div class="prose prose-lg max-w-none">
    <div class="bg-white rounded-lg shadow-sm p-8 mb-8">
      <h2 class="text-2xl font-semibold text-gray-900 mb-4">Our Mission</h2>
      <p class="text-gray-700 leading-relaxed">
        Democracy works best when voters have access to clear, unbiased
        information about candidates and their positions. Smarter.vote uses
        artificial intelligence to analyze public sources and present candidate
        positions in an easy-to-understand format, helping voters make informed
        decisions based on the issues that matter most to them.
      </p>
    </div>

    <div class="bg-white rounded-lg shadow-sm p-8 mb-8">
      <h2 class="text-2xl font-semibold text-gray-900 mb-4">How We Work</h2>
      <div class="space-y-4">
        <div>
          <h3 class="text-lg font-semibold text-gray-900 mb-2">
            Source Discovery
          </h3>
          <p class="text-gray-700">
            We automatically discover and collect information from candidate
            websites, voting records, public speeches, position papers, and
            other publicly available sources.
          </p>
        </div>
        <div>
          <h3 class="text-lg font-semibold text-gray-900 mb-2">AI Analysis</h3>
          <p class="text-gray-700">
            Multiple AI models (including GPT-4 and Claude) independently
            analyze the collected information to extract candidate positions on
            key issues. This multi-model approach helps ensure accuracy and
            reduce bias.
          </p>
        </div>
        <div>
          <h3 class="text-lg font-semibold text-gray-900 mb-2">Transparency</h3>
          <p class="text-gray-700">
            Every position includes confidence ratings and links to the original
            sources, so you can verify the information yourself and understand
            how certain we are about each stance.
          </p>
        </div>
      </div>
    </div>

    <div class="bg-white rounded-lg shadow-sm p-8 mb-8">
      <h2 class="text-2xl font-semibold text-gray-900 mb-4">
        Key Issues We Cover
      </h2>
      <div class="grid md:grid-cols-2 gap-4">
        <ul class="space-y-2 text-gray-700">
          <li>• Healthcare</li>
          <li>• Economy</li>
          <li>• Climate/Energy</li>
          <li>• Reproductive Rights</li>
          <li>• Immigration</li>
          <li>• Guns & Safety</li>
        </ul>
        <ul class="space-y-2 text-gray-700">
          <li>• Foreign Policy</li>
          <li>• LGBTQ+ Rights</li>
          <li>• Education</li>
          <li>• Tech & AI</li>
          <li>• Election Reform</li>
        </ul>
      </div>
    </div>

    <div class="bg-white rounded-lg shadow-sm p-8 mb-8">
      <h2 class="text-2xl font-semibold text-gray-900 mb-4">
        Important Disclaimers
      </h2>
      <div class="space-y-3 text-gray-700">
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

    <div class="bg-blue-50 border border-blue-200 rounded-lg p-6 text-center">
      <h3 class="text-lg font-semibold text-blue-900 mb-2">
        Questions or Concerns?
      </h3>
      <p class="text-blue-800">
        If you notice any inaccuracies or have questions about our methodology,
        please contact us through our GitHub repository where this project is
        developed openly.
      </p>
    </div>
  </div>
</div>
