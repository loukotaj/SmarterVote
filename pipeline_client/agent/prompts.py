"""Prompts for the multi-step research agent.

The agent runs in phases:
1. **Discovery** – identify the race, candidates, background, and images.
2. **Issue research** – one focused prompt per canonical issue group.
3. **Refinement** – merge, clean, and improve the full profile.

Optionally followed by multi-LLM **review** (Claude / Gemini).
"""

CANONICAL_ISSUES = [
    "Economy",
    "Education",
    "Healthcare",
    "Reproductive Rights",
    "Climate/Energy",
    "Tech & AI",
    "Immigration",
    "Foreign Policy",
    "Guns & Safety",
    "Social Justice",
    "Election Reform",
    "Local Issues",
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
5. voting_record entries MUST use field names "bill_name" and "vote".
   "vote" MUST be exactly one of: "yes", "no", "abstain", "absent" — never free text like "voted against".
6. Return ONLY valid JSON – no markdown fences, no extra text."""

_DONOR_SCHEMA_NOTE = """\
For top_donors, include up to 5 real named donors with amounts.
Search in this order — stop when you have real names:
  1. Search "<candidate name> top donors opensecrets" → opensecrets.org/candidates has a "Top Contributors" section
  2. Search "<candidate name> campaign finance followthemoney" → followthemoney.org
  3. FEC receipts (NOT the overview page): https://www.fec.gov/data/candidate/<ID>/?tab=raising
     or search "<candidate name> FEC top contributors site:fec.gov"
  4. News articles: "<candidate name> biggest donors 2026"
Do NOT record "None identified" as a donor — if you cannot find real names leave top_donors as [].
Every donor entry must follow this shape exactly:
{{
  "name": "<donor full name>",
  "amount": <dollar amount as number or null>,
  "organization": "<employer or organization or null>",
  "source": {{"url": "<direct url to the page showing this donor>", "type": "government|news|website", "title": "<page title>"}}
}}"""

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
4. A brief 2-3 sentence nonpartisan summary of each candidate. Do NOT append inline "Sources: ..." text to the summary — put sources in the summary_sources array instead.
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
9. A 3-4 sentence nonpartisan description of this race — what office is being
   contested, why this race matters (e.g. open seat, competitive, national
   implications), the political context (partisan lean, recent election history),
   and the key themes or contrasts between the candidates.
10. Recent opinion polls for this race. Search for "[state] [office] poll 2026"
    or "[candidates] poll". Include up to 5 of the most recent polls with:
    - Pollster name, date conducted, sample size
    - Each candidate's percentage
    - Source URL
    Only include real polls from credible pollsters. Set polling to [] if none found.
""" + _DONOR_SCHEMA_NOTE + """

Return JSON:
{{
  "id": "{race_id}",
  "title": "<descriptive race title>",
  "office": "<office name>",
  "jurisdiction": "<state or district>",
  "election_date": "<YYYY-MM-DD or best estimate>",
  "description": "<3-4 sentence nonpartisan overview of the race>",
  "polling": [
    {{
      "pollster": "<polling organization>",
      "date": "<YYYY-MM-DD>",
      "sample_size": 600,
      "matchups": [
        {{
          "candidates": ["<Candidate A>", "<Candidate B>"],
          "percentages": [48.5, 41.0]
        }}
      ],
      "source_url": "<direct URL to poll or article>"
    }}
  ],
  "candidates": [
    {{
      "name": "<full name>",
      "party": "<party affiliation>",
      "incumbent": true|false,
      "summary": "<2-3 sentence nonpartisan summary — plain prose only, no 'Sources:' appended>",
      "summary_sources": [
        {{"url": "<url>", "type": "government|news|website", "title": "<page title>", "last_accessed": "<ISO timestamp>"}}
      ],
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
          "bill_name": "<bill name or number, e.g. S.5 Laken Riley Act>",
          "bill_description": "<one sentence description>",
          "vote": "yes",
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
Here is a draft candidate profile for the race "{race_id}".
You are improving ONE candidate at a time to keep responses small.

Candidate name: {candidate_name}
Candidate data:
{candidate_json}

Race-level context:
- Race description: {race_description}
- Other candidates in this race: {other_candidates}
- All canonical issues that must be covered: {all_issues}
""" + _DONOR_SCHEMA_NOTE + """

Research and improve this ONE candidate:
1. Fix factual inconsistencies you can verify with web_search.
2. Fill missing or low-confidence stances with better sourced data.
3. Ensure every stance has at least one source URL.
4. Improve the summary — plain prose, nonpartisan, 2-3 sentences. No inline "Sources:". Sources go in summary_sources.
5. Add real named top donors if findable (source object required on each).
6. Ensure all 12 canonical issues are covered: {all_issues}
7. Fill gaps in career_history and education if better data exists.
8. If image_url is missing or null, search for a direct image file URL:
   - Wikipedia: use https://upload.wikimedia.org/wikipedia/commons/... (NOT commons.wikimedia.org/wiki/File:)
   - Ballotpedia: https://ballotpedia.org/wiki/images/...
   Only set image_url if the URL directly serves an image file.
9. Verify voting_record entries — each must have "bill_name" and "vote" (yes/no/abstain/absent).

Use your editing tools to record every improvement directly. When you are satisfied
that the profile is accurate and complete, reply with a short plain-text summary
of what you changed (e.g. "Updated Healthcare stance, added 2 donors, fixed image URL.")."""

REFINE_META_USER = """\
Here is the top-level metadata for race "{race_id}".

Current description: {race_description}
Current polling: {polling_json}

Search for:
1. Any better or more accurate race description (3-4 sentences: office, why it matters, partisan context, key contrasts).
2. Recent polls (last 90 days). Include pollster, date, sample_size, matchups, source_url.

Use your editing tools (update_race_field for description and add_poll for each poll)
to record any improvements directly. When done, reply with a short confirmation
of what you updated (e.g. "Updated description, added 2 new polls.")."""

# ------------------------------------------------------------------
# Update prompts — phase-based (mirrors fresh run)
# ------------------------------------------------------------------

UPDATE_META_SYSTEM = f"""\
You are a nonpartisan political research agent updating an existing race profile.

{_SHARED_RULES}"""

UPDATE_META_USER = """\
Race: "{race_id}" — last updated {last_updated}
Candidates: {candidate_names}

Search for NEW information since {last_updated}:
1. Any major news, announcements, or developments for each candidate.
2. Updated or corrected candidate summaries (keep them 2-3 sentences, nonpartisan).
3. Recent polls (last 90 days). Include pollster, date, sample size, percentages, source URL.
4. Updated race description (office context, why it matters, key contrasts).
""" + _DONOR_SCHEMA_NOTE + """

Use your editing tools to record every improvement directly:
- update_race_field for description
- add_poll for each new poll
- set_candidate_summary for updated summaries
- set_candidate_field for other candidate fields

When you are done, reply with a short plain-text summary of what changed
(e.g. "Updated description, added 1 poll, refreshed summary for Candidate A.")."""

UPDATE_ISSUE_SYSTEM = f"""\
You are a nonpartisan political research agent updating issue positions in an existing profile.

{_SHARED_RULES}"""

UPDATE_ISSUE_USER = """\
Race: "{race_id}" — updating since {last_updated}
Candidates: {candidate_names}

Issues to update: {issues_list}

Existing stances (for reference — only return better/corrected data):
{existing_stances}

Search for the LATEST positions on these issues. Focus on:
- Statements, votes, or actions since {last_updated}
- Filling any gaps where confidence is "low" or stance is missing

Return JSON keyed by candidate name (only include candidates/issues where you have new or better data):
{{
  "<Candidate Name>": {{
    "<Issue>": {{
      "stance": "<updated position>",
      "confidence": "high|medium|low",
      "sources": [{{"url": "<url>", "type": "website|news|government", "title": "<title>"}}]
    }}
  }}
}}"""

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

Be thorough but fair. Flag specific problems with field paths.
When the profile is accurate and well-sourced, say so warmly and specifically."""

REVIEW_USER = """\
Review this candidate profile for the race "{race_id}":

{profile_json}

Check for:
1. Factual accuracy – are stated positions consistent with sources?
2. Bias – is the language neutral and nonpartisan?
3. Completeness – are there missing issues, weak sources, or gaps?
4. Source quality – are sources credible and current?
5. Candidate background – is career history and education reasonable?

For the "summary" field:
- If verdict is "approved": write a warm, specific positive statement about what the profile
  does well (e.g. "Strong sourcing across all 12 issues with high-confidence citations from
  official campaign sites and credible news outlets. Candidate backgrounds are accurate and
  well-documented."). Do NOT just say "looks good" — be specific.
- If verdict is "needs_revision" or "flagged": summarize the key concerns concisely.

Return JSON:
{{
  "verdict": "approved|needs_revision|flagged",
  "summary": "<specific assessment — warm and positive if approved, focused on key issues if not>",
  "flags": [
    {{
      "field": "<dot-path to field, e.g. candidates[0].issues.Healthcare.stance>",
      "concern": "<what is wrong>",
      "suggestion": "<how to fix it or null>",
      "severity": "info|warning|error"
    }}
  ]
}}"""

# ------------------------------------------------------------------
# Phase 2b: Dedicated finance & voting record research
# ------------------------------------------------------------------

FINANCE_VOTING_SYSTEM = f"""\
You are a nonpartisan political research agent specializing in campaign
finance data and legislative voting records.

{_SHARED_RULES}"""

FINANCE_VOTING_USER = """\
You are researching campaign finance and voting records for the race "{race_id}".
Candidates: {candidate_names}

PART 1 — TOP DONORS (for each candidate):
Search aggressively using ALL of these strategies — do NOT stop after one attempt:
  1. OpenSecrets: search "<candidate name> top donors opensecrets" or
     "<candidate name> contributors opensecrets.org". Fetch the page and look for
     the "Top Contributors" table. Extract real names and dollar amounts.
  2. FollowTheMoney: search "<candidate name> campaign finance followthemoney"
     Look for top individual and organizational contributors.
  3. FEC: search "<candidate name> FEC individual contributions" or go to
     https://www.fec.gov/data/receipts/?data_type=processed&committee_id=<ID>
     Sort by amount descending. Also try: "<candidate name> top contributors site:fec.gov"
  4. News articles: search "<candidate name> biggest donors 2026" or
     "<candidate name> campaign fundraising donors"
  5. State-level: search "<candidate name> campaign contributions state"
     (for state/local races, OpenSecrets may not have data — use state disclosures)

You MUST attempt at least 3 different search queries per candidate for donors.
Include up to 5 real named donors per candidate with actual dollar amounts.
Do NOT fabricate names. If you genuinely cannot find donor data after multiple
searches, return an empty array — but try hard first.

PART 2 — VOTING RECORD (for each candidate, especially incumbents):
Search for actual roll-call votes and bill sponsorships:
  1. Congress.gov: search "<candidate name> votes site:congress.gov" or
     "<candidate name> sponsored bills congress.gov"
  2. GovTrack: search "<candidate name> voting record govtrack.us"
  3. VoteSmart: search "<candidate name> voting record votesmart.org"
  4. State legislature: for state-level candidates, search
     "<candidate name> voting record [state] legislature" or
     "<candidate name> bills [state]"
  5. News: search "<candidate name> voted against" or "<candidate name> key votes 2025 2026"

You MUST attempt at least 3 different search queries per candidate for voting records.
Include up to 10 notable votes per candidate. For each vote include the exact bill
name/number, a one-sentence description, how they voted (yes/no/abstain/absent),
the date, and a source URL.

For non-incumbents or candidates with no legislative history, search for any public
statements about how they WOULD have voted on key bills (note these as "stated
position" not a vote).

IMPORTANT — DEDUPLICATION:
- If the same donor name appears multiple times, consolidate into ONE entry
  with the highest amount (or most recent cycle). Do NOT list the same
  person/organization more than once.

""" + _DONOR_SCHEMA_NOTE + """

Return JSON keyed by candidate name:
{{
  "<Candidate Name>": {{
    "top_donors": [
      {{
        "name": "<donor full name>",
        "amount": <dollar amount or null>,
        "organization": "<employer/org or null>",
        "donation_year": "<election cycle e.g. 2025-2026, or year e.g. 2026>",
        "source": {{"url": "<url>", "type": "government|news|website", "title": "<page title>"}}
      }}
    ],
    "donor_source_url": "<best URL where users can browse the full donor list, e.g. OpenSecrets candidate page, FEC candidate page>",
    "voting_record": [
      {{
        "bill_name": "<bill name or number>",
        "bill_description": "<one sentence>",
        "vote": "yes|no|abstain|absent",
        "date": "<YYYY-MM-DD>",
        "source": {{"url": "<url>", "type": "government|news", "title": "<title>"}}
      }}
    ],
    "voting_summary": "<2-3 sentences summarizing the candidate's voting patterns, e.g. 'Consistently voted for environmental protections and gun safety measures. Sponsored 3 education funding bills.'>",
    "voting_source_url": "<best URL where users can browse the full voting record — prefer VoteSmart > GovTrack > Congress.gov > state legislature site>"
  }}
}}"""

# ------------------------------------------------------------------
# Iteration prompt — apply review feedback to improve a profile
# ------------------------------------------------------------------

ITERATE_SYSTEM = f"""\
You are a nonpartisan editorial agent. You are given a candidate research
profile and specific review feedback (flags) from fact-checking reviewers.
Your job is to address each flag by researching and fixing the issues.

CRITICAL — SOURCE-VERIFICATION RULE:
Before changing ANY factual claim (a vote, a donor amount, a stated position),
you MUST first verify the flag by searching the original source cited in the
profile. If the source confirms the original data is correct, REJECT the
reviewer's flag — do NOT change accurate data to satisfy a mistaken reviewer.
When you reject a flag, add an entry to "dismissed_flags" in your output
explaining why (e.g. "Source confirms the vote was real").

Only modify data when:
- The source contradicts the profile, OR
- The source is unavailable/broken, OR
- Additional sources disprove the claim.

{_SHARED_RULES}"""

ITERATE_USER = """\
Race "{race_id}" — addressing review flags for ONE candidate at a time.

Candidate name: {candidate_name}
Candidate data:
{candidate_json}

Review flags to address for this candidate:
{review_flags}

For EACH flag above:
1. If the flag identifies a factual error, use web_search to verify and fix it.
2. If the flag identifies missing data, search for it and add it.
3. If the flag identifies weak sourcing, find better/additional sources.
4. If the flag identifies bias, rewrite the text to be neutral.
5. If the flag is informational only (severity "info"), address if easily fixable.

CRITICAL — SOURCE-VERIFICATION RULE: Before changing ANY factual claim, verify it
by re-fetching the original source. Only change data when the source actually
contradicts the profile, or when the source is unavailable. If the source confirms
the original data, skip that flag and leave the data unchanged.

Also ensure:
- All 12 canonical issues covered: {all_issues}
- voting_record uses "bill_name" and "vote" (yes/no/abstain/absent)
- top_donors have source objects

Use your editing tools to record every fix directly. When you have addressed all
actionable flags, reply with a short plain-text summary of what you changed
(e.g. "Fixed Healthcare stance sourcing, added missing Economy stance.")."""

ITERATE_META_USER = """\
Race "{race_id}" — addressing review flags for race-level metadata.

Current description: {race_description}
Current polling: {polling_json}

Review flags to address:
{review_flags}

Search and fix any flagged issues with the description or polling.

Use your editing tools (update_race_field for description, add_poll for new polls)
to record any fixes directly. When done, reply with a short plain-text confirmation
of what you changed (e.g. "Fixed race description bias, added corrected poll.")."""


# ------------------------------------------------------------------
# Roster sync prompt (update mode only)
# ------------------------------------------------------------------

ROSTER_SYNC_SYSTEM = f"""\
You are a nonpartisan political research agent. Your ONLY task is to verify
the current list of candidates in a race and correct it using your editing
tools. Do NOT change any other data — only the candidate roster.

{_SHARED_RULES}"""

ROSTER_SYNC_USER = """\
Race: "{race_id}" — last updated {last_updated}
Current candidates: {candidate_names}

Search for whether any candidates have:
1. Dropped out, withdrawn, or been disqualified since {last_updated}
2. Newly entered the race since {last_updated}
3. Had their name corrected (e.g. legal name change, common misspelling)

Use your editing tools to make corrections:
- add_candidate — for new entrants
- remove_candidate — for withdrawals (include reason)
- rename_candidate — for name corrections

If the roster is already correct, reply with a short confirmation. Do NOT
modify any other data (issues, summaries, polls, etc.)."""


# ------------------------------------------------------------------
# Per-candidate per-issue sub-agent prompt
# ------------------------------------------------------------------

ISSUE_SUBAGENT_SYSTEM = f"""\
You are a nonpartisan political research agent researching ONE candidate's
position on ONE issue. Use web_search and fetch_page to find the most
authoritative sources, then use your set_issue_stance tool to record the
finding.

{_SHARED_RULES}"""

ISSUE_SUBAGENT_USER = """\
Candidate: {candidate_name}
Race: {race_id}
Issue to research: {issue}

{handoff_context}

Research this candidate's position on "{issue}". Look for:
- Official campaign positions or policy pages
- Voting record on relevant legislation
- Public statements, interviews, debate answers
- Endorsements or scorecards from issue-focused organizations

Then use the set_issue_stance tool to record:
- stance: 1-2 sentence factual description of their position
- confidence: "high" (multiple corroborating sources), "medium" (single credible source), "low" (inferred)
- sources: array of source objects with url, type, title

When you are done, reply briefly confirming what you found."""


# ------------------------------------------------------------------
# Update issue sub-agent prompt (for update/rerun mode)
# ------------------------------------------------------------------

UPDATE_ISSUE_SUBAGENT_SYSTEM = f"""\
You are a nonpartisan political research agent updating ONE candidate's
position on ONE issue. An existing stance is provided — use web_search and
fetch_page to find newer or better-sourced information, then use your
set_issue_stance tool ONLY if you find an improvement.

{_SHARED_RULES}"""

UPDATE_ISSUE_SUBAGENT_USER = """\
Candidate: {candidate_name}
Race: {race_id} — updating since {last_updated}
Issue to update: {issue}

Current stance:
{existing_stance}

{handoff_context}

Search for NEWER information about this candidate's position on "{issue}"
since {last_updated}. Focus on:
- New statements, votes, or policy changes
- Better sources if current confidence is "low" or "medium"
- Corrections if the current stance is inaccurate

Use set_issue_stance ONLY if you find genuinely new or better data.
If the existing stance is already accurate and well-sourced, reply with
a short confirmation (no tool call needed)."""
