"""Prompts for the Pipeline V2 multi-step research agent.

The agent runs in phases:
1. **Discovery** – identify the race and candidates.
2. **Issue research** – one focused prompt per canonical issue group.
3. **Refinement** – merge, clean, and improve the full profile.
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

# ------------------------------------------------------------------
# Phase 1: Discovery prompt
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

Return JSON:
{{
  "id": "{race_id}",
  "title": "<descriptive race title>",
  "office": "<office name>",
  "jurisdiction": "<state or district>",
  "election_date": "<YYYY-MM-DD or best estimate>",
  "candidates": [
    {{
      "name": "<full name>",
      "party": "<party affiliation>",
      "incumbent": true|false,
      "summary": "<2-3 sentence nonpartisan summary>",
      "website": "<official campaign URL or null>",
      "social_media": {{}},
      "top_donors": [],
      "issues": {{}}
    }}
  ],
  "updated_utc": "<ISO timestamp>",
  "generator": ["pipeline-v2-agent"]
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
- Source URLs

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
# Phase 3: Refinement prompt
# ------------------------------------------------------------------

REFINE_SYSTEM = f"""\
You are a nonpartisan editorial agent. Your job is to review, clean up,
and improve a candidate research profile for accuracy and completeness.

{_SHARED_RULES}"""

REFINE_USER = """\
Here is a draft candidate profile for the race "{race_id}":

{draft_json}

Review and improve this profile:
1. Fix any factual inconsistencies you can verify with web_search.
2. Fill in missing or weak stances (confidence "low") if better info exists.
3. Ensure every stance has at least one source URL.
4. Improve candidate summaries so they are clear, concise, and nonpartisan.
5. Add top donor information if findable.
6. Ensure all 12 canonical issues are covered for each candidate:
   {all_issues}

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

Update this profile:
1. Search for any NEW developments, position changes, or news since the
   profile was last updated ({last_updated}).
2. Verify existing stances still hold – correct any that changed.
3. Fill in any missing issue positions or weak (low confidence) stances.
4. Update candidate summaries if there are significant new developments.
5. Keep all existing source URLs and add new ones.

Return the COMPLETE updated JSON profile (same schema as input).
Do NOT omit any fields – return the full object."""
