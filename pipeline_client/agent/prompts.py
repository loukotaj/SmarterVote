"""Prompts for the multi-step research agent.

The agent runs in phases:
1. **Discovery** – identify the race, candidates, background, and images.
2. **Issue research** – one focused prompt per canonical issue group.
3. **Refinement** – merge, clean, and improve the full profile.

Optionally followed by multi-LLM **review** (Claude / Gemini).
"""

CANONICAL_ISSUES = [
    "Healthcare",
    "Economy",
    "Climate/Energy",
    "Reproductive Rights",
    "Immigration",
    "Guns & Safety",
    "Foreign Policy",
    "Social Justice",
    "Education",
    "Tech & AI",
    "Election Reform",
    "Local Issues",
]

# Groups of issues researched together (keeps each prompt focused)
ISSUE_GROUPS = [
    ["Healthcare", "Reproductive Rights"],
    ["Economy", "Education"],
    ["Climate/Energy", "Tech & AI"],
    ["Immigration", "Foreign Policy"],
    ["Guns & Safety", "Social Justice"],
    ["Election Reform", "Local Issues"],
]

# ------------------------------------------------------------------
# Shared rules that apply to every prompt
# ------------------------------------------------------------------

_SHARED_RULES = """\
RULES (apply to every response):
1. Be factual and nonpartisan. Report what candidates say and do.
2. Use the web_search tool to find information.
3. Confidence levels:
   - "high": Multiple corroborating sources or official campaign position
   - "medium": Single credible source
   - "low": Inferred or unverified
4. Always include source URLs for every claim.
5. Return ONLY valid JSON – no markdown fences, no extra text."""

_DONOR_SCHEMA_NOTE = """\
For top_donors, include up to 3-5 major donors when credible finance data is available.
Every donor entry must include a source object using this shape:
{{
  "name": "<donor name>",
  "amount": <number or null>,
  "organization": "<organization or null>",
  "source": {{"url": "<url>", "type": "government|news|website", "title": "<title>"}}
}}
Prefer campaign finance databases, FEC pages, or established donor-tracking sources over generic news coverage."""

# ------------------------------------------------------------------
# Phase 1: Discovery prompt (enhanced with career & images)
# ------------------------------------------------------------------

DISCOVERY_SYSTEM = f"""\
You are a nonpartisan political research agent.

{_SHARED_RULES}"""

DISCOVERY_USER = """\
Research the U.S. election race "{race_id}".

Search for:
1. What office is this for? What state/district?
2. Who are the candidates? (name, party, incumbent status)
3. Each candidate's official campaign website and social media.
4. A brief 2-3 sentence nonpartisan summary of each candidate.
5. Each candidate's career history (political offices held, major jobs).
6. Each candidate's education (degrees, institutions).
7. Notable voting record items (for incumbents or former legislators).
8. A direct image URL for each candidate's headshot. Use these strategies:
   a) Search "<candidate name> wikipedia" — Wikipedia images are at
      https://upload.wikimedia.org/wikipedia/commons/... (NOT commons.wikimedia.org/wiki/File:)
   b) Search "<candidate name> official photo site:house.gov OR site:senate.gov"
   c) Search "<candidate name> headshot site:ballotpedia.org" (Ballotpedia images are at
      https://ballotpedia.org/wiki/images/...)
   The URL MUST end in .jpg, .jpeg, .png, .gif, or .webp, or be from a known image CDN.
   Do NOT use a Wikipedia/Commons page URL (commons.wikimedia.org/wiki/File:...) — that is a
   gallery page, not an image file. Set to null if you cannot confirm a direct image file URL.
9. A 2-3 sentence nonpartisan description of this race — what office is being
   contested, why this race matters (e.g. open seat, competitive, national
   implications), and the key themes or contrasts between the candidates.
""" + _DONOR_SCHEMA_NOTE + """

Return JSON:
{{
  "id": "{race_id}",
  "title": "<descriptive race title>",
  "office": "<office name>",
  "jurisdiction": "<state or district>",
  "election_date": "<YYYY-MM-DD or best estimate>",
  "description": "<2-3 sentence nonpartisan overview of the race>",
  "candidates": [
    {{
      "name": "<full name>",
      "party": "<party affiliation>",
      "incumbent": true|false,
      "summary": "<2-3 sentence nonpartisan summary>",
      "image_url": "<direct image file URL ending in .jpg/.png/.gif/.webp, or null if not found>",
      "website": "<official campaign URL or null>",
      "social_media": {{}},
      "career_history": [
        {{
          "title": "<role/position>",
          "organization": "<employer or body>",
          "start_year": 2020,
          "end_year": null,
          "description": "<brief note>"
        }}
      ],
      "education": [
        {{
          "institution": "<school name>",
          "degree": "<degree type>",
          "field": "<major/field>",
          "year": 2005
        }}
      ],
      "voting_record": [
        {{
          "bill_name": "<bill>",
          "bill_description": "<short desc>",
          "vote": "yes|no|abstain|absent",
          "date": "<YYYY-MM-DD>",
          "source": {{"url": "<url>", "type": "government", "title": "<title>"}}
        }}
      ],
      "top_donors": [
        {{
          "name": "<donor name>",
          "amount": 1000000,
          "organization": "<organization or null>",
          "source": {{"url": "<url>", "type": "government|news|website", "title": "<title>"}}
        }}
      ],
      "issues": {{}}
    }}
  ],
  "updated_utc": "<ISO timestamp>",
  "generator": ["pipeline-agent"]
}}"""

# ------------------------------------------------------------------
# Phase 2: Issue research prompt (one per issue group)
# ------------------------------------------------------------------

ISSUE_RESEARCH_SYSTEM = f"""\
You are a nonpartisan political research agent specialising in policy positions.

{_SHARED_RULES}"""

ISSUE_RESEARCH_USER = """\
You are researching the race "{race_id}".
Candidates: {candidate_names}

Research each candidate's positions on THESE issues ONLY:
{issues_list}

For EACH candidate and EACH issue, provide:
- Their stated position (1-2 sentences)
- Confidence level (high/medium/low)
- Source URLs with titles

Return JSON – an object keyed by candidate name:
{{
  "<Candidate Name>": {{
    "<Issue>": {{
      "stance": "<position>",
      "confidence": "high|medium|low",
      "sources": [
        {{"url": "<url>", "type": "website|news|government|social_media", "title": "<title>"}}
      ]
    }}
  }}
}}"""

# ------------------------------------------------------------------
# Phase 3: Refinement prompt (enhanced)
# ------------------------------------------------------------------

REFINE_SYSTEM = f"""\
You are a nonpartisan editorial agent. Your job is to review, clean up,
and improve a candidate research profile for accuracy and completeness.

{_SHARED_RULES}"""

REFINE_USER = """\
Here is a draft candidate profile for the race "{race_id}":

{draft_json}
""" + _DONOR_SCHEMA_NOTE + """

Review and improve this profile:
1. Fix any factual inconsistencies you can verify with web_search.
2. Fill in missing or weak stances (confidence "low") if better info exists.
3. Ensure every stance has at least one source URL.
4. Improve candidate summaries so they are clear, concise, and nonpartisan.
5. Add top donor information if findable, and include a source object on every donor entry.
6. Ensure all 12 canonical issues are covered for each candidate:
   {all_issues}
7. Fill gaps in career_history and education if you find better data.
8. Search for a direct image file URL for any candidate missing image_url. Use:
   - Wikipedia: search the article, then use https://upload.wikimedia.org/wikipedia/commons/... URLs
     (NOT commons.wikimedia.org/wiki/File:... — that is a page, not an image file)
   - Ballotpedia: https://ballotpedia.org/wiki/images/...
   - Official government sites that serve .jpg files directly.
   Only set image_url if you find a URL that directly serves an image file.
9. Verify voting record entries are accurate.
10. Write or improve the top-level 'description' field: 2-3 sentences
    describing the office being contested, why this race matters, and key
    contrasts between the candidates.

Return the COMPLETE improved JSON profile (same schema as input).
Do NOT omit any fields – return the full object."""

# ------------------------------------------------------------------
# Update / rerun prompt
# ------------------------------------------------------------------

UPDATE_SYSTEM = f"""\
You are a nonpartisan political research agent. You are given an existing
candidate profile that may be outdated. Your job is to update it with the
latest information.

{_SHARED_RULES}"""

UPDATE_USER = """\
Here is the current published profile for race "{race_id}":

{existing_json}
""" + _DONOR_SCHEMA_NOTE + """

Update this profile:
1. Search for any NEW developments, position changes, or news since the
   profile was last updated ({last_updated}).
2. Verify existing stances still hold – correct any that changed.
3. Fill in any missing issue positions or weak (low confidence) stances.
4. Update candidate summaries if there are significant new developments.
5. Keep all existing source URLs and add new ones.
6. Update career_history and education if new information is available.
7. Search for a direct image file URL for any candidate missing image_url. Use:
   - Wikipedia: search the article, then use https://upload.wikimedia.org/wikipedia/commons/... URLs
     (NOT commons.wikimedia.org/wiki/File:... — that is a page, not an image file)
   - Ballotpedia: https://ballotpedia.org/wiki/images/...
   - Official government sites that serve .jpg files directly.
   Only set image_url if you find a URL that directly serves an image file.
8. Add or update voting record entries.
9. Add or update top_donors entries, and include a source object on every donor item.
10. Write or improve the top-level 'description' field: 2-3 sentences
    describing the office being contested, why this race matters, and key
    contrasts between the candidates.

Return the COMPLETE updated JSON profile (same schema as input).
Do NOT omit any fields – return the full object."""

# ------------------------------------------------------------------
# Image URL resolution prompt (standalone phase)
# ------------------------------------------------------------------

IMAGE_SEARCH_SYSTEM = f"""\
You are a research agent whose ONLY job is to find a working direct image URL
for a political candidate's official headshot or portrait.

{_SHARED_RULES}"""

IMAGE_SEARCH_USER = """\
Find a working, directly-accessible image file URL for: {candidate_name}

SEARCH STRATEGIES (try in order):
1. Search "{candidate_name} wikipedia" — find their Wikipedia article, then
   look for the image URL. Wikipedia images live at:
   https://upload.wikimedia.org/wikipedia/commons/...
   (NOT https://commons.wikimedia.org/wiki/File:... — that is a page, not an image)
2. Search "{candidate_name} official photo site:house.gov OR site:senate.gov" —
   government sites sometimes serve .jpg files directly.
3. Search "{candidate_name} headshot site:ballotpedia.org" — Ballotpedia
   stores images at https://ballotpedia.org/wiki/images/...
4. Search "{candidate_name} campaign site photo" — campaign sites often have
   /wp-content/uploads/*.jpg or similar direct image paths.

CRITICAL RULES:
- The URL MUST end in .jpg, .jpeg, .png, .gif, .webp, or be a known direct
  image CDN path (e.g. upload.wikimedia.org, ballotpedia.org/wiki/images/).
- Do NOT return a Wikipedia/Commons page URL like commons.wikimedia.org/wiki/File:
- Do NOT return an HTML page that shows an image, return the image file itself.
- Return null if no reliable direct image URL can be confirmed.

Return JSON only:
{{"image_url": "<direct image file URL or null>"}}"""

# ------------------------------------------------------------------
# Multi-LLM review prompts (Claude / Gemini)
# ------------------------------------------------------------------

REVIEW_SYSTEM = """\
You are a fact-checking review agent. You are given a candidate research
profile in JSON format. Your job is to review it for accuracy, bias,
completeness, and source quality.

Be thorough but fair. Flag specific problems with field paths."""

REVIEW_USER = """\
Review this candidate profile for the race "{race_id}":

{profile_json}

Check for:
1. Factual accuracy – are stated positions consistent with sources?
2. Bias – is the language neutral and nonpartisan?
3. Completeness – are there missing issues, weak sources, or gaps?
4. Source quality – are sources credible and current?
5. Candidate background – is career history and education reasonable?

Return JSON:
{{
  "verdict": "approved|needs_revision|flagged",
  "summary": "<1-2 sentence overall assessment>",
  "flags": [
    {{
      "field": "<dot-path to field, e.g. candidates[0].issues.Healthcare.stance>",
      "concern": "<what is wrong>",
      "suggestion": "<how to fix it or null>",
      "severity": "info|warning|error"
    }}
  ]
}}"""
