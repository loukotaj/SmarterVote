"""OpenRouter/OpenAI-compatible function-calling tool schemas for the research agent.

All editing-tool JSON schemas live here so that ``agent.py`` stays focused on
orchestration logic.  Import the individual constants or the aggregate lists.
"""

from typing import List

# ---------------------------------------------------------------------------
# Web search / page fetch
# ---------------------------------------------------------------------------

SEARCH_TOOL: dict = {
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

FETCH_TOOL: dict = {
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

BALLOTPEDIA_ELECTION_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "ballotpedia_election_lookup",
        "description": (
            "Fetch the Ballotpedia election page for this race and return the authoritative list of "
            "candidates. This is the single most reliable source for who is officially in the race — "
            "call this FIRST in discovery before doing any web searches. "
            "Returns: found (bool), page_url, candidates list [{name, party, incumbent}], "
            "and a short description paragraph."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "race_id": {
                    "type": "string",
                    "description": "The race identifier (e.g. 'ar-senate-2026', 'ga-governor-2026').",
                }
            },
            "required": ["race_id"],
        },
    },
}

IMAGE_SEARCH_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "web_image_search",
        "description": (
            "Search the web for candidate headshot images. Returns a list of "
            "search results containing direct image URLs (imageUrl), titles, and parent website links."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to execute (e.g. 'Tommy Tuberville headshot').",
                }
            },
            "required": ["query"],
        },
    },
}

WEB_TOOLS: List[Dict] = [SEARCH_TOOL, FETCH_TOOL, BALLOTPEDIA_TOOL, BALLOTPEDIA_ELECTION_TOOL, IMAGE_SEARCH_TOOL]

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
                "roster_sources": {
                    "type": "array",
                    "description": "Sources proving this candidate is active in this exact race.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": ["official", "ballotpedia", "fec", "news", "campaign", "other"],
                            },
                            "title": {"type": "string"},
                            "evidence": {"type": "string", "description": "Short note explaining what the source confirms."},
                        },
                    },
                },
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

SET_CANDIDATE_ROSTER_SOURCES_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "set_candidate_roster_sources",
        "description": "Set source evidence proving that a candidate belongs on the current roster.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": ["official", "ballotpedia", "fec", "news", "campaign", "other"],
                            },
                            "title": {"type": "string"},
                            "evidence": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["candidate_name", "sources"],
        },
    },
}

SET_RACE_IDENTITY_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "set_race_identity",
        "description": "Record the locked race identity and contest stage used for roster verification.",
        "parameters": {
            "type": "object",
            "properties": {
                "office": {"type": "string"},
                "state": {"type": "string"},
                "district": {"type": "string"},
                "contest_stage": {
                    "type": "string",
                    "enum": [
                        "pre_primary",
                        "post_primary_general",
                        "runoff",
                        "top_two",
                        "top_four_rcv",
                        "uncontested",
                        "special",
                        "unknown",
                    ],
                },
                "election_date": {"type": "string"},
                "primary_status": {"type": "string"},
                "official_roster_source_url": {"type": "string"},
                "known_incumbent": {"type": "string"},
                "known_ineligible_or_not_running": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["contest_stage"],
        },
    },
}

ROSTER_TOOLS: List[Dict] = [
    ADD_CANDIDATE_TOOL,
    REMOVE_CANDIDATE_TOOL,
    RENAME_CANDIDATE_TOOL,
    SET_CANDIDATE_ROSTER_SOURCES_TOOL,
    SET_RACE_IDENTITY_TOOL,
]

# ---------------------------------------------------------------------------
# Candidate field / summary tools
# ---------------------------------------------------------------------------

SET_CANDIDATE_FIELD_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "set_candidate_field",
        "description": ("Update a scalar field on a candidate. Allowed fields: party, incumbent, " "website, image_url."),
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "field": {
                    "type": "string",
                    "enum": ["party", "incumbent", "website", "image_url"],
                    "description": "Field to update.",
                },
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

REMOVE_CAREER_ENTRY_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "remove_career_entry",
        "description": (
            "Remove a single career history entry from a candidate's profile by matching "
            "title and organization. Use this to surgically delete a fabricated or incorrect "
            "entry without disturbing the rest of the career history."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "organization": {
                    "type": "string",
                    "description": "Organization name to match (case-insensitive, partial match ok).",
                },
            },
            "required": ["candidate_name", "organization"],
        },
    },
}

UPDATE_CAREER_ENTRY_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "update_career_entry",
        "description": (
            "Update specific fields of an existing career history entry in-place, matched by "
            "organization name. Use this to correct dates, title, or description without "
            "removing and re-adding the entry. Only provided fields are changed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "organization": {
                    "type": "string",
                    "description": "Organization name to match (case-insensitive, partial match ok).",
                },
                "title": {"type": "string", "description": "Corrected role title (omit if unchanged)."},
                "start_year": {"type": "integer", "description": "Corrected start year (omit if unchanged)."},
                "end_year": {"type": "integer", "description": "Corrected end year (omit if unchanged)."},
                "description": {"type": "string", "description": "Corrected description (omit if unchanged)."},
            },
            "required": ["candidate_name", "organization"],
        },
    },
}

UPDATE_EDUCATION_ENTRY_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "update_education_entry",
        "description": (
            "Update specific fields of an existing education entry in-place, matched by "
            "institution name. Use this to fill in a missing field or year without "
            "removing and re-adding the entry. Only provided fields are changed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "institution": {
                    "type": "string",
                    "description": "Institution name to match (case-insensitive, partial match ok).",
                },
                "degree": {"type": "string", "description": "Corrected degree type (omit if unchanged)."},
                "field": {"type": "string", "description": "Corrected field of study (omit if unchanged)."},
                "year": {"type": "integer", "description": "Corrected graduation year (omit if unchanged)."},
            },
            "required": ["candidate_name", "institution"],
        },
    },
}

CLEAR_CAREER_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "clear_career_history",
        "description": "Clear ALL career history entries for a candidate before re-adding correct data. Prefer remove_career_entry for single-entry corrections.",
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

BIO_TOOLS: List[Dict] = [
    ADD_CAREER_ENTRY_TOOL,
    REMOVE_CAREER_ENTRY_TOOL,
    UPDATE_CAREER_ENTRY_TOOL,
    ADD_EDUCATION_ENTRY_TOOL,
    UPDATE_EDUCATION_ENTRY_TOOL,
    SET_SOCIAL_MEDIA_TOOL,
    CLEAR_CAREER_TOOL,
    CLEAR_EDUCATION_TOOL,
]
BACKGROUND_TOOLS = BIO_TOOLS  # backward-compat alias

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
                "confidence": {"type": "string", "enum": ["high", "medium", "low"], "description": "Confidence level."},
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
                "summary": {
                    "type": "string",
                    "description": "2-3 sentence summary of who funds the candidate. Do not include inline 'Sources:' text.",
                },
                "source_url": {
                    "type": "string",
                    "description": "URL to full donor data (OpenSecrets, FEC, state portal, etc.).",
                },
                "sources": {
                    "type": "array",
                    "description": "Structured finance sources supporting the donor summary.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "type": {"type": "string", "description": "Use finance for campaign-finance records."},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "published_at": {"type": "string"},
                        },
                        "required": ["url"],
                    },
                },
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
                "summary": {
                    "type": "string",
                    "description": "2-3 sentence summary of the candidate's voting patterns. Do not include inline 'Sources:' text or raw URLs.",
                },
                "source_url": {
                    "type": "string",
                    "description": "Best single URL for the full voting record (VoteSmart, GovTrack, legislature, etc.).",
                },
                "sources": {
                    "type": "array",
                    "description": "Structured sources supporting the voting summary.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "type": {
                                "type": "string",
                                "description": "Use website, government, news, or finance. Put VoteSmart pages under website and GovTrack/legislature pages under government.",
                            },
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "published_at": {"type": "string"},
                        },
                        "required": ["url"],
                    },
                },
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
                    "enum": [
                        "finance",
                        "ballotpedia",
                        "wiki",
                        "official",
                        "legislature",
                        "votesmart",
                        "govtrack",
                        "news",
                        "other",
                    ],
                    "description": "Link category.",
                },
            },
            "required": ["candidate_name", "url", "title", "type"],
        },
    },
}

REMOVE_CANDIDATE_SOURCE_URL_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "remove_candidate_source_url",
        "description": (
            "Remove a broken, duplicate, stale, or low-value URL from one candidate's "
            "summary sources, issue sources, donor/voting sources, scalar source URLs, "
            "and reference links. Use this before adding a replacement source."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "url": {"type": "string", "description": "Exact URL to remove from the candidate profile."},
            },
            "required": ["candidate_name", "url"],
        },
    },
}

RECORD_TOOLS: List[Dict] = [
    SET_DONOR_SUMMARY_TOOL,
    SET_VOTING_SUMMARY_TOOL,
    ADD_LINK_TOOL,
    REMOVE_CANDIDATE_SOURCE_URL_TOOL,
]

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
                    "description": "Use an empty list only when the source confirms a poll but does not publish numeric candidate percentages.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "candidates": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                            "percentages": {"type": "array", "items": {"type": "number"}, "minItems": 1},
                        },
                        "required": ["candidates", "percentages"],
                    },
                },
                "source_url": {"type": "string", "description": "URL to poll source."},
            },
            "required": ["pollster", "date", "matchups", "source_url"],
        },
    },
}

REMOVE_POLL_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "remove_poll",
        "description": (
            "Remove a poll from the race's polling data. Use this to delete duplicate polls, "
            "polls with null/missing result data, or polls that are redundant. "
            "Identify the poll by pollster name (required) and optionally by date."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pollster": {
                    "type": "string",
                    "description": "Name of the polling organization whose entry should be removed.",
                },
                "date": {
                    "type": "string",
                    "description": "Optional poll date (YYYY-MM-DD). If provided, only the poll with this exact pollster+date is removed. If omitted, all polls by this pollster are removed.",
                },
                "reason": {
                    "type": "string",
                    "description": "Brief reason for removal (e.g. 'duplicate', 'null result data', 'superseded by newer poll').",
                },
            },
            "required": ["pollster", "reason"],
        },
    },
}

UPDATE_RACE_FIELD_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "update_race_field",
        "description": "Update a race-level field. Allowed fields: description, office, election_date, polling_note, ballotpedia_url, register_to_vote_url, how_to_vote_url, contest_stage.",
        "parameters": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": [
                        "description",
                        "office",
                        "election_date",
                        "polling_note",
                        "ballotpedia_url",
                        "register_to_vote_url",
                        "how_to_vote_url",
                        "contest_stage",
                    ],
                    "description": "Field to update.",
                },
                "value": {"type": "string", "description": "New value."},
            },
            "required": ["field", "value"],
        },
    },
}

RACE_TOOLS: List[Dict] = [ADD_POLL_TOOL, REMOVE_POLL_TOOL, UPDATE_RACE_FIELD_TOOL]


def _restricted_race_field_tool(fields: List[str], description: str) -> Dict:
    return {
        "type": "function",
        "function": {
            "name": "update_race_field",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "enum": fields, "description": "Field to update."},
                    "value": {"type": "string", "description": "New value."},
                },
                "required": ["field", "value"],
            },
        },
    }


DESCRIPTION_TOOLS: List[Dict] = [_restricted_race_field_tool(["description"], "Update the race description.")]
POLLING_TOOLS: List[Dict] = [
    ADD_POLL_TOOL,
    REMOVE_POLL_TOOL,
    _restricted_race_field_tool(["polling_note"], "Update the race polling note."),
]

SET_FORECAST_TOOL: Dict = {
    "type": "function",
    "function": {
        "name": "set_forecast",
        "description": "Set the race-level informational forecast based only on existing race data.",
        "parameters": {
            "type": "object",
            "properties": {
                "predicted_winner_name": {
                    "type": "string",
                    "description": "Predicted winning candidate name, or empty if unknown.",
                },
                "predicted_winner_party": {"type": "string", "description": "Predicted winning party, or empty if unknown."},
                "win_probability": {"type": "number", "minimum": 0, "maximum": 1},
                "party_probabilities": {
                    "type": "object",
                    "additionalProperties": {"type": "number", "minimum": 0, "maximum": 1},
                    "description": "Party-level win probabilities keyed by normalized party name.",
                },
                "margin_estimate": {"type": "number", "description": "Estimated winner margin in percentage points."},
                "rating": {
                    "type": "string",
                    "enum": [
                        "safe_d",
                        "likely_d",
                        "lean_d",
                        "tilt_d",
                        "tossup",
                        "tilt_r",
                        "lean_r",
                        "likely_r",
                        "safe_r",
                        "other",
                    ],
                },
                "confidence": {"type": "string", "enum": ["high", "medium", "low", "unknown"]},
                "rationale": {"type": "string", "description": "Brief nonpartisan rationale."},
                "takeaway": {
                    "type": "string",
                    "description": "Concise, 1-sentence forecast takeaway summary (e.g., 'Democrats are slightly favored in this highly competitive race...').",
                },
                "key_reasons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of the 2-3 most important analytical reasons supporting this forecast (e.g., incumbency advantage, recent poll lead, national environment).",
                },
                "uncertainty": {
                    "type": "string",
                    "description": "A single sentence highlighting key caveats or sources of uncertainty (e.g., lack of polling, strong third-party candidates).",
                },
                "based_on_poll_count": {"type": "integer", "minimum": 0},
                "source_urls": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "rating",
                "confidence",
                "rationale",
                "based_on_poll_count",
                "party_probabilities",
                "source_urls",
            ],
        },
    },
}

FORECAST_TOOLS: List[Dict] = [SET_FORECAST_TOOL]
VOTER_RESOURCE_TOOLS: List[Dict] = [
    _restricted_race_field_tool(
        ["ballotpedia_url", "register_to_vote_url", "how_to_vote_url"],
        "Update a verified voter-resource URL.",
    )
]

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
                    "enum": ["full", "candidate", "candidates", "issues", "polling", "meta"],
                    "description": "Which section to read. Use 'issues' for a compact issues-only view.",
                },
                "candidate_name": {
                    "type": "string",
                    "description": "Exact candidate name. Required when section is 'candidate'.",
                },
            },
            "required": ["section"],
        },
    },
}
