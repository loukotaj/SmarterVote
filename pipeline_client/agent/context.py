"""Model-aware context budgeting and deterministic tool-result compaction."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .model_registry import MODEL_CATALOG, normalize_model_id

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'-]{2,}", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_DEFAULT_CONTEXT_WINDOW_TOKENS = 262_144
_COMPACT_TOOL_RESULT_TOKENS = 2_048


def estimate_tokens(value: Any) -> int:
    """Return a conservative token estimate for JSON-compatible content."""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str)
    return max(1, math.ceil(len(value) / 3))


def _env_int(name: str, default: int, minimum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


@dataclass(frozen=True)
class AgentContextBudget:
    """Large-context allocation for one model request loop."""

    context_window_tokens: int
    target_input_tokens: int
    maximum_input_tokens: int
    reserved_output_tokens: int
    minimum_context_headroom: int
    max_single_tool_result_tokens: int
    max_search_results: int
    max_retained_tool_turns: int
    max_iterations: int
    max_output_tokens: int
    narrow_phase: bool = False

    @classmethod
    def for_model(
        cls,
        model: str,
        *,
        phase_name: str,
        max_iterations: int,
        max_output_tokens: int,
    ) -> "AgentContextBudget":
        normalized = normalize_model_id(model) or model
        spec = MODEL_CATALOG.get(normalized)
        catalog_window = spec.context_window_tokens if spec else _DEFAULT_CONTEXT_WINDOW_TOKENS
        context_window = _env_int("OPENROUTER_DEFAULT_CONTEXT_TOKENS", catalog_window, 32_768)
        narrow = phase_name.lower().startswith(("issue-", "image-"))
        target_percent = _env_int("PIPELINE_CONTEXT_TARGET_PERCENT", 60 if narrow else 75, 40)
        target_percent = min(target_percent, 85)
        reserved_output = min(
            max_output_tokens,
            spec.max_completion_tokens if spec and spec.max_completion_tokens else max_output_tokens,
        )
        headroom = _env_int("PIPELINE_CONTEXT_HEADROOM_TOKENS", max(8_192, context_window // 20), 4_096)
        maximum_input = context_window - reserved_output - headroom
        if maximum_input < 16_384:
            maximum_input = max(1, context_window - reserved_output)
        target_input = min(maximum_input, context_window * target_percent // 100)
        max_tool_tokens = min(64_000, max(8_192, target_input // (5 if narrow else 3)))
        return cls(
            context_window_tokens=context_window,
            target_input_tokens=target_input,
            maximum_input_tokens=maximum_input,
            reserved_output_tokens=reserved_output,
            minimum_context_headroom=headroom,
            max_single_tool_result_tokens=max_tool_tokens,
            max_search_results=_env_int("PIPELINE_MAX_SEARCH_RESULTS", 10, 1),
            max_retained_tool_turns=_env_int("PIPELINE_MAX_RETAINED_TOOL_TURNS", 8 if narrow else 12, 2),
            max_iterations=max_iterations,
            max_output_tokens=reserved_output,
            narrow_phase=narrow,
        )


@dataclass
class ContextPreparation:
    messages: List[Dict[str, Any]]
    estimated_input_tokens: int
    deduplicated_results: int = 0
    compacted_results: int = 0
    truncated_results: int = 0
    dropped_tool_turns: int = 0


def _truncate_text(text: str, max_tokens: int) -> tuple[str, bool]:
    max_chars = max_tokens * 3
    if len(text) <= max_chars:
        return text, False
    marker = "\n\n[truncated to fit the model context budget]"
    return text[: max(0, max_chars - len(marker))].rstrip() + marker, True


def _keywords(text: str) -> set[str]:
    ignored = {
        "about",
        "after",
        "before",
        "candidate",
        "from",
        "have",
        "into",
        "more",
        "only",
        "race",
        "research",
        "return",
        "that",
        "their",
        "this",
        "with",
    }
    return {word.lower() for word in _WORD_RE.findall(text) if word.lower() not in ignored}


def _relevant_excerpt(text: str, terms: set[str], max_tokens: int) -> tuple[str, bool]:
    if estimate_tokens(text) <= max_tokens:
        return text, False
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
    if not paragraphs:
        return _truncate_text(text, max_tokens)
    scored = []
    for index, paragraph in enumerate(paragraphs):
        lowered = paragraph.lower()
        scored.append((sum(1 for term in terms if term in lowered), -index, paragraph))
    selected: List[str] = []
    used = 0
    for _, _, paragraph in sorted(scored, reverse=True):
        paragraph_tokens = estimate_tokens(paragraph)
        if selected and used + paragraph_tokens > max_tokens:
            continue
        selected.append(paragraph)
        used += paragraph_tokens
        if used >= max_tokens:
            break
    excerpt, _ = _truncate_text("\n\n".join(selected) if selected else text, max_tokens)
    return excerpt, True


class AgentContext:
    """Tracks source deduplication and prepares bounded request histories."""

    def __init__(self, budget: AgentContextBudget, *, task_text: str):
        self.budget = budget
        self._terms = _keywords(task_text)
        self._seen_payloads: set[str] = set()
        self._seen_urls: set[str] = set()
        self._seen_source_keys: set[str] = set()
        self._notebook: List[Dict[str, str]] = []
        self.deduplicated_results = 0
        self.truncated_results = 0

    def prepare_tool_result(
        self,
        tool_name: str,
        content: Any,
        *,
        source_url: Optional[str] = None,
    ) -> str:
        if tool_name == "web_search":
            content = self._normalize_search_results(content)
        elif not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=True, separators=(",", ":"), default=str)

        text = str(content)
        urls = [source_url] if source_url else []
        urls.extend(_URL_RE.findall(text))
        urls = list(dict.fromkeys(url for url in urls if url))
        digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
        source_key = f"{tool_name}:{source_url}" if source_url else ""
        if digest in self._seen_payloads or (source_key and source_key in self._seen_source_keys):
            self.deduplicated_results += 1
            citation = urls[0] if urls else "the prior tool result"
            return f"Duplicate result omitted; use the existing research notebook entry for {citation}."

        self._seen_payloads.add(digest)
        if source_key:
            self._seen_source_keys.add(source_key)
        self._seen_urls.update(urls)
        if tool_name == "fetch_page":
            text, truncated = _relevant_excerpt(text, self._terms, self.budget.max_single_tool_result_tokens)
        else:
            text, truncated = _truncate_text(text, self.budget.max_single_tool_result_tokens)
        if truncated:
            self.truncated_results += 1

        self._notebook.append(
            {
                "tool": tool_name,
                "url": urls[0] if urls else "",
                "summary": re.sub(r"\s+", " ", text).strip()[:600],
            }
        )
        return text

    def _normalize_search_results(self, content: Any) -> str:
        results = content
        if isinstance(content, str):
            try:
                results = json.loads(content)
            except json.JSONDecodeError:
                results = [{"snippet": content}]
        if not isinstance(results, list):
            results = [results]
        normalized = []
        for item in results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or item.get("link") or "")
            if url and url in self._seen_urls:
                self.deduplicated_results += 1
                continue
            normalized.append(
                {
                    "title": str(item.get("title") or "")[:300],
                    "url": url,
                    "snippet": str(item.get("snippet") or item.get("description") or "")[:1_500],
                }
            )
            if len(normalized) >= self.budget.max_search_results:
                break
        return json.dumps(normalized, ensure_ascii=True, separators=(",", ":"))

    def prepare_messages(
        self,
        messages: Sequence[Dict[str, Any]],
        *,
        tools: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> ContextPreparation:
        prepared = deepcopy(list(messages))
        tool_tokens = estimate_tokens(tools or [])
        compacted = 0
        dropped = 0

        groups = self._tool_groups(prepared)
        excess_groups = max(0, len(groups) - self.budget.max_retained_tool_turns)
        for start, end in reversed(groups[:excess_groups]):
            del prepared[start:end]
            dropped += 1

        groups = self._tool_groups(prepared)
        if self._estimate_request(prepared, tool_tokens) > self.budget.target_input_tokens:
            for start, end in groups:
                compacted += self._compact_group(prepared, start, end)
                if self._estimate_request(prepared, tool_tokens) <= self.budget.target_input_tokens:
                    break

        while self._estimate_request(prepared, tool_tokens) > self.budget.maximum_input_tokens:
            groups = self._tool_groups(prepared)
            if not groups:
                break
            start, end = groups[0]
            del prepared[start:end]
            dropped += 1

        notebook = self._notebook_message()
        if notebook:
            prepared.insert(2, notebook)
            while self._estimate_request(prepared, tool_tokens) > self.budget.maximum_input_tokens:
                groups = self._tool_groups(prepared)
                if not groups:
                    break
                start, end = groups[0]
                del prepared[start:end]
                dropped += 1

        estimated = self._estimate_request(prepared, tool_tokens)
        if estimated > self.budget.maximum_input_tokens:
            raise RuntimeError(
                f"Base prompt requires about {estimated:,} tokens, above the model input limit "
                f"of {self.budget.maximum_input_tokens:,} tokens after output reserve."
            )
        return ContextPreparation(
            messages=prepared,
            estimated_input_tokens=estimated,
            deduplicated_results=self.deduplicated_results,
            compacted_results=compacted,
            truncated_results=self.truncated_results,
            dropped_tool_turns=dropped,
        )

    @staticmethod
    def _tool_groups(messages: Sequence[Dict[str, Any]]) -> List[tuple[int, int]]:
        groups: List[tuple[int, int]] = []
        index = 2
        while index < len(messages):
            message = messages[index]
            if message.get("role") == "assistant" and message.get("tool_calls"):
                end = index + 1
                while end < len(messages) and messages[end].get("role") == "tool":
                    end += 1
                groups.append((index, end))
                index = end
            else:
                index += 1
        return groups

    @staticmethod
    def _compact_group(messages: List[Dict[str, Any]], start: int, end: int) -> int:
        changed = 0
        for index in range(start + 1, end):
            message = messages[index]
            if message.get("role") != "tool":
                continue
            compacted, truncated = _truncate_text(str(message.get("content") or ""), _COMPACT_TOOL_RESULT_TOKENS)
            if truncated:
                message["content"] = compacted
                changed += 1
        return changed

    def _estimate_request(self, messages: Sequence[Dict[str, Any]], tool_tokens: int) -> int:
        return estimate_tokens(messages) + tool_tokens

    def _notebook_message(self) -> Optional[Dict[str, str]]:
        if not self._notebook:
            return None
        return {
            "role": "system",
            "content": "Research notebook (durable source index):\n"
            + json.dumps(self._notebook, ensure_ascii=True, separators=(",", ":")),
        }
