"""OpenAI function-calling tool schemas for the research agent.

All editing-tool JSON schemas live here so that ``agent.py`` stays focused on
orchestration logic.  Import the individual constants or the aggregate lists.
"""

from typing import Dict, List

# ---------------------------------------------------------------------------
# Web search / page fetch
# ---------------------------------------------------------------------------

SEARCH_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current information about candidates, "
            "elections, and political positions. Returns a list of search "
            "results with titles, snippets, and URLs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to execute.",
                }
            },
            "required": ["query"],
        },
    },
}

FETCH_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "fetch_page",
        "description": (
            "Fetch the full text content of a web page. Use this when a search "
            "result URL looks promising but you need more detail than the snippet "
            "provides — e.g. to read a full article, find an image URL embedded "
            "in a page, or extract specific data from a government site. "
            "Returns the page's readable text (HTML stripped), truncated to ~8000 characters."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL to fetch.",
                }
            },
            "required": ["url"],
        },
    },
}

BALLOTPEDIA_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "ballotpedia_lookup",
        "description": (
            "Look up a political candidate on Ballotpedia and return structured data "
            "directly from their page — without needing to spend a web search or parse HTML. "
            "Returns: a bio extract (intro paragraph), a list of useful external links "
            "(campaign website, FEC profile, VoteSmart, OpenSecrets, social media), "
            "a thumbnail image URL, and the Ballotpedia page URL. "
            "Use this early in research for any candidate to quickly gather their "
            "official website, finance links, and a clean biography."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {
                    "type": "string",
                    "description": "Full name of the candidate to look up (e.g. 'Tom Cotton').",
                }
            },
            "required": ["candidate_name"],
        },
    },
}

# ---------------------------------------------------------------------------
# Roster editing tools
# ---------------------------------------------------------------------------

ADD_CANDIDATE_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "add_candidate",
        "description": "Add a new candidate to the race. Use when a new entrant has joined the race.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Full name of the candidate."},
                "party": {"type": "string", "description": "Party affiliation (e.g. 'Democratic', 'Republican')."},
                "incumbent": {"type": "boolean", "description": "Whether this candidate is the incumbent."},
            },
            "required": ["name", "party"],
        },
    },
}

REMOVE_CANDIDATE_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "remove_candidate",
        "description": "Remove a candidate who has dropped out or withdrawn from the race.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Exact name of the candidate to remove."},
                "reason": {"type": "string", "description": "Brief reason for removal (e.g. 'withdrew', 'disqualified')."},
            },
            "required": ["name"],
        },
    },
}

RENAME_CANDIDATE_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "rename_candidate",
        "description": "Correct a candidate's name (e.g. fix spelling, use formal name).",
        "parameters": {
            "type": "object",
            "properties": {
                "old_name": {"type": "string", "description": "Current name in the profile."},
                "new_name": {"type": "string", "description": "Corrected name."},
            },
            "required": ["old_name", "new_name"],
        },
    },
}

ROSTER_TOOLS: List[Dict] = [ADD_CANDIDATE_TOOL, REMOVE_CANDIDATE_TOOL, RENAME_CANDIDATE_TOOL]

# ---------------------------------------------------------------------------
# Candidate field / summary tools
# ---------------------------------------------------------------------------

SET_CANDIDATE_FIELD_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "set_candidate_field",
        "description": (
            "Update a scalar field on a candidate. Allowed fields: party, incumbent, "
            "website, image_url."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "field": {"type": "string", "enum": ["party", "incumbent", "website", "image_url"],
                          "description": "Field to update."},
                "value": {"description": "New value for the field."},
            },
            "required": ["candidate_name", "field", "value"],
        },
    },
}

SET_CANDIDATE_SUMMARY_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "set_candidate_summary",
        "description": "Rewrite a candidate's biographical summary. Keep it 2-3 sentences, nonpartisan.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "summary": {"type": "string", "description": "New 2-3 sentence nonpartisan summary."},
                "sources": {
                    "type": "array",
                    "description": "Source URLs for the summary.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "type": {"type": "string"},
                            "title": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["candidate_name", "summary"],
        },
    },
}

CANDIDATE_TOOLS: List[Dict] = [SET_CANDIDATE_FIELD_TOOL, SET_CANDIDATE_SUMMARY_TOOL]

# ---------------------------------------------------------------------------
# Career, education, and social media tools
# ---------------------------------------------------------------------------

ADD_CAREER_ENTRY_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "add_career_entry",
        "description": "Add a career history entry to a candidate's profile.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "title": {"type": "string", "description": "Role or position title."},
                "organization": {"type": "string", "description": "Employer or body."},
                "start_year": {"type": "integer", "description": "Year started (null if unknown)."},
                "end_year": {"type": "integer", "description": "Year ended (null if current/unknown)."},
                "description": {"type": "string", "description": "Brief description of the role."},
            },
            "required": ["candidate_name", "title", "organization"],
        },
    },
}

ADD_EDUCATION_ENTRY_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "add_education_entry",
        "description": "Add an education entry to a candidate's profile.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "institution": {"type": "string", "description": "School or university name."},
                "degree": {"type": "string", "description": "Degree type (e.g. 'Bachelor of Arts', 'Juris Doctor')."},
                "field": {"type": "string", "description": "Major or field of study (null if unknown)."},
                "year": {"type": "integer", "description": "Graduation year (null if unknown)."},
            },
            "required": ["candidate_name", "institution", "degree"],
        },
    },
}

SET_SOCIAL_MEDIA_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "set_social_media",
        "description": "Set a social media URL for a candidate (e.g. twitter, facebook, instagram).",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "platform": {"type": "string", "description": "Platform name (e.g. 'twitter', 'facebook', 'instagram')."},
                "url": {"type": "string", "description": "Full URL to the candidate's profile."},
            },
            "required": ["candidate_name", "platform", "url"],
        },
    },
}

CLEAR_CAREER_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "clear_career_history",
        "description": "Clear all career history entries for a candidate before re-adding correct data.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
            },
            "required": ["candidate_name"],
        },
    },
}

CLEAR_EDUCATION_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "clear_education",
        "description": "Clear all education entries for a candidate before re-adding correct data.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
            },
            "required": ["candidate_name"],
        },
    },
}

BACKGROUND_TOOLS: List[Dict] = [
    ADD_CAREER_ENTRY_TOOL, ADD_EDUCATION_ENTRY_TOOL, SET_SOCIAL_MEDIA_TOOL,
    CLEAR_CAREER_TOOL, CLEAR_EDUCATION_TOOL,
]

# ---------------------------------------------------------------------------
# Issue stance tool
# ---------------------------------------------------------------------------

SET_ISSUE_STANCE_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "set_issue_stance",
        "description": "Set or update a candidate's stance on a canonical issue.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "issue": {"type": "string", "description": "Canonical issue name (e.g. 'Healthcare')."},
                "stance": {"type": "string", "description": "1-2 sentence position description."},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"],
                               "description": "Confidence level."},
                "sources": {
                    "type": "array",
                    "description": "Source URLs supporting this stance.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "type": {"type": "string"},
                            "title": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["candidate_name", "issue", "stance", "confidence"],
        },
    },
}

ISSUE_TOOLS: List[Dict] = [SET_ISSUE_STANCE_TOOL]

# ---------------------------------------------------------------------------
# Record tools (summary setters + links)
# ---------------------------------------------------------------------------

SET_DONOR_SUMMARY_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "set_donor_summary",
        "description": "Set a candidate's campaign finance summary text and source link.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "summary": {"type": "string", "description": "2-3 sentence summary of who funds the candidate."},
                "source_url": {"type": "string", "description": "URL to full donor data (OpenSecrets, FEC, state portal, etc.)."},
            },
            "required": ["candidate_name", "summary"],
        },
    },
}

SET_VOTING_SUMMARY_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "set_voting_summary",
        "description": "Set a candidate's voting record summary text and source link.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "summary": {"type": "string", "description": "2-3 sentence summary of the candidate's voting patterns."},
                "source_url": {"type": "string", "description": "URL to full voting record (VoteSmart, GovTrack, legislature, etc.)."},
            },
            "required": ["candidate_name", "summary"],
        },
    },
}

ADD_LINK_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "add_candidate_link",
        "description": "Add a high-value reference link to a candidate's profile (Ballotpedia, Wikipedia, OpenSecrets, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "url": {"type": "string", "description": "Full URL."},
                "title": {"type": "string", "description": "Human-readable page title."},
                "type": {
                    "type": "string",
                    "enum": ["finance", "ballotpedia", "wiki", "official", "legislature", "votesmart", "govtrack", "news", "other"],
                    "description": "Link category.",
                },
            },
            "required": ["candidate_name", "url", "title", "type"],
        },
    },
}

RECORD_TOOLS: List[Dict] = [SET_DONOR_SUMMARY_TOOL, SET_VOTING_SUMMARY_TOOL, ADD_LINK_TOOL]

# ---------------------------------------------------------------------------
# Race-level tools
# ---------------------------------------------------------------------------

ADD_POLL_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "add_poll",
        "description": "Add a new poll to the race's polling data.",
        "parameters": {
            "type": "object",
            "properties": {
                "pollster": {"type": "string", "description": "Polling organization name."},
                "date": {"type": "string", "description": "Date of poll (YYYY-MM-DD)."},
                "sample_size": {"type": "integer", "description": "Number of respondents."},
                "matchups": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "candidates": {"type": "array", "items": {"type": "string"}},
                            "percentages": {"type": "array", "items": {"type": "number"}},
                        },
                    },
                },
                "source_url": {"type": "string", "description": "URL to poll source."},
            },
            "required": ["pollster", "date", "matchups", "source_url"],
        },
    },
}

UPDATE_RACE_FIELD_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "update_race_field",
        "description": "Update a race-level field. Allowed fields: description, office, election_date, polling_note.",
        "parameters": {
            "type": "object",
            "properties": {
                "field": {"type": "string", "enum": ["description", "office", "election_date", "polling_note"],
                          "description": "Field to update."},
                "value": {"type": "string", "description": "New value."},
            },
            "required": ["field", "value"],
        },
    },
}

RACE_TOOLS: List[Dict] = [ADD_POLL_TOOL, UPDATE_RACE_FIELD_TOOL]

# ---------------------------------------------------------------------------
# Read-only verification tool
# ---------------------------------------------------------------------------

READ_PROFILE_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "read_profile",
        "description": (
            "Read the current state of the race profile JSON. Use this to verify "
            "your edits took effect or to check what data already exists."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["full", "candidates", "issues", "polling", "meta"],
                    "description": "Which section to read. Use 'issues' for a compact issues-only view.",
                },
            },
            "required": ["section"],
        },
    },
}
