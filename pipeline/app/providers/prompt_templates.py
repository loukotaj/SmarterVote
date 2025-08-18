"""Prompt templates for LLM summarization tasks."""

from ..utils.prompt_loader import load_prompt


class PromptTemplates:
    """Collection of prompt templates for different summarization tasks."""

    @staticmethod
    def get_candidate_summary_prompt() -> str:
        """Get prompt template for candidate summarization."""
        return load_prompt("candidate_summary")

    @staticmethod
    def get_issue_stance_prompt() -> str:
        """Get prompt template for issue stance analysis."""
        return load_prompt("issue_stance")

    @staticmethod
    def get_general_summary_prompt() -> str:
        """Get prompt template for general content summarization."""
        return load_prompt("general_summary")

    @staticmethod
    def get_race_summary_prompt() -> str:
        """Get prompt template for overall race summarization."""
        return load_prompt("race_summary")

    @staticmethod
    def get_issue_summary_prompt() -> str:
        """Get prompt template for issue-specific summarization."""
        return load_prompt("issue_summary")
