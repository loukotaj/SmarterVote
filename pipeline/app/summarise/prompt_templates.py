"""
Prompt templates for LLM Summarization Engine.

This module contains all the prompt templates used for different
summarization tasks including candidate summaries, issue analysis,
and race overviews.
"""


class PromptTemplates:
    """Collection of prompt templates for different summarization tasks."""

    @staticmethod
    def get_candidate_summary_prompt() -> str:
        """Get prompt template for candidate summarization."""
        return """
You are analyzing electoral content to summarize candidates for the {race_id} election.

Based on the following content, create comprehensive profiles for each candidate that include:

1. Biographical information and background
2. Key policy positions and campaign platform
3. Notable endorsements or supporters
4. Recent campaign activities and statements
5. Experience and qualifications
6. Any controversies or significant issues

Content to analyze:
{content}

IMPORTANT: Your response must follow this exact format:

CONFIDENCE: [HIGH|MEDIUM|LOW|UNKNOWN]
- HIGH: Multiple reliable sources confirm most key information
- MEDIUM: Some reliable sources with limited conflicting information
- LOW: Limited sources or significant conflicting information
- UNKNOWN: Insufficient information to make reliable assessment

SUMMARY:
[Your factual, balanced summary here. Include specific source citations in the format (Source: [URL or title]) when referencing information. Clearly distinguish between verified facts and claims.]

SOURCES CITED:
- [List the specific sources you referenced in your summary]

Summary:
"""

    @staticmethod
    def get_issue_stance_prompt() -> str:
        """Get prompt template for issue stance analysis."""
        return """
You are analyzing candidate positions on specific policy issues for the {race_id} election.

Based on the following content, identify and summarize each candidate's stance on the key issues.
For each position:

1. State the candidate's position clearly
2. Provide supporting evidence or quotes
3. Note the source and date of the information
4. Identify any changes or evolution in the position
5. Flag any ambiguous or unclear statements

Content to analyze:
{content}

IMPORTANT: Your response must follow this exact format:

CONFIDENCE: [HIGH|MEDIUM|LOW|UNKNOWN]
- HIGH: Multiple reliable sources confirm candidate positions with clear statements
- MEDIUM: Some reliable sources with minor ambiguities or gaps
- LOW: Limited sources or conflicting/unclear position statements
- UNKNOWN: Insufficient information to determine candidate positions

ISSUE ANALYSIS:
[Your factual analysis here. Include specific source citations in the format (Source: [URL or title]) for each position or statement. Focus on factual positions and avoid interpretation or bias.]

SOURCES CITED:
- [List the specific sources you referenced in your analysis]

Issue Analysis:
"""

    @staticmethod
    def get_general_summary_prompt() -> str:
        """Get prompt template for general content summarization."""
        return """
You are summarizing electoral content for the {race_id} race.

Please provide a comprehensive summary of the following content that includes:

1. Key factual information about the race
2. Major developments and news
3. Candidate positions and statements
4. Important dates and events
5. Relevant context and background

Content to summarize:
{content}

IMPORTANT: Your response must follow this exact format:

CONFIDENCE: [HIGH|MEDIUM|LOW|UNKNOWN]
- HIGH: Multiple reliable sources confirm most key information with good coverage
- MEDIUM: Adequate sources with some gaps or minor inconsistencies
- LOW: Limited sources or significant information gaps
- UNKNOWN: Insufficient information for reliable analysis

SUMMARY:
[Your comprehensive summary here. Include specific source citations in the format (Source: [URL or title]) when referencing information. Maintain objectivity and distinguish between facts, claims, and opinions. Organize the information logically and highlight the most important points.]

SOURCES CITED:
- [List the specific sources you referenced in your summary]

Summary:
"""

    @staticmethod
    def get_race_summary_prompt() -> str:
        """Get prompt template for overall race summarization."""
        return """
You are analyzing electoral content to create an overall race summary for {race_id}.

Please provide a comprehensive race overview that includes:

1. Race basics: Office, jurisdiction, election date, key context
2. Competitive landscape: Who are the main candidates, their parties
3. Major themes and issues driving the race
4. Recent developments and key events
5. Electoral dynamics and what makes this race significant
6. Historical context and precedent

Content to analyze:
{content}

Focus on providing voters with essential information to understand this electoral contest. Be factual, balanced, and comprehensive.

Race Summary:
"""

    @staticmethod
    def get_issue_summary_prompt() -> str:
        """Get prompt template for issue-specific summarization."""
        return """
You are analyzing electoral content to summarize how {issue_name} is being addressed in the {race_id} race.

Please provide a focused analysis that includes:

1. How this issue is relevant to this particular race
2. Different candidate positions or approaches to {issue_name}
3. Recent developments or news related to this issue in the race
4. Key policy proposals or statements from candidates
5. Public opinion or stakeholder perspectives on this issue
6. How this issue might influence voter decisions

Content to analyze:
{content}

Focus on the specific issue of {issue_name} and how it relates to this electoral race. Provide balanced coverage of different perspectives.

Issue Analysis for {issue_name}:
"""
