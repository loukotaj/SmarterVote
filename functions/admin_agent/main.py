"""Firestore-triggered durable admin agent with races-api tool access."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import functions_framework
import httpx
from cloudevents.http import CloudEvent

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("admin_agent")

_PROJECT_ID = os.getenv("FIRESTORE_PROJECT") or os.getenv("PROJECT_ID")
_RACES_API_URL = os.getenv("RACES_API_URL", "").rstrip("/")
_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
_OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
_MODEL = os.getenv("ADMIN_AGENT_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
_DEADLINE_SECONDS = int(os.getenv("ADMIN_AGENT_DEADLINE_SECONDS", "450"))
_MAX_ITERATIONS = int(os.getenv("ADMIN_AGENT_MAX_ITERATIONS", "40"))
_MAX_CONTINUATIONS = int(os.getenv("ADMIN_AGENT_MAX_CONTINUATIONS", "8"))
_MAX_TOTAL_TOKENS = int(os.getenv("ADMIN_AGENT_MAX_TOTAL_TOKENS", "200000"))
_MAX_OUTPUT_TOKENS = int(os.getenv("ADMIN_AGENT_MAX_OUTPUT_TOKENS", "4096"))
_MAX_COST_USD = float(os.getenv("ADMIN_AGENT_MAX_COST_USD", "5.0"))

_TASKS = "admin_agent_tasks"
_MESSAGES = "admin_agent_messages"
_CONVERSATIONS = "admin_agent_conversations"
_APPROVAL_REQUIRED = {
    "publish_race",
    "unpublish_race",
    "cancel_race",
    "cancel_or_delete_run",
    "clear_races_api_cache",
}

_fs_db = None


def _get_fs():
    global _fs_db
    if _fs_db is None:
        from google.cloud import firestore  # type: ignore

        _fs_db = firestore.Client(project=_PROJECT_ID) if _PROJECT_ID else firestore.Client()
    return _fs_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _message(
    db: Any,
    conversation_id: str,
    task_id: str,
    role: str,
    content: str,
    *,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    metadata: Dict[str, Any] | None = None,
) -> None:
    message_id = _new_id()
    db.collection(_MESSAGES).document(message_id).set(
        {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "task_id": task_id,
            "role": role,
            "content": content[:50000],
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "metadata": metadata or {},
            "created_at": _now(),
        }
    )


def _load_messages(db: Any, conversation_id: str) -> list[Dict[str, Any]]:
    docs = db.collection(_MESSAGES).where("conversation_id", "==", conversation_id).stream()
    stored = sorted(
        (doc.to_dict() or {} for doc in docs),
        key=lambda item: (str(item.get("created_at") or ""), str(item.get("message_id") or "")),
    )[-120:]
    while stored and stored[0].get("role") == "tool":
        stored.pop(0)
    messages: list[Dict[str, Any]] = []
    for item in stored:
        role = item.get("role")
        if role not in {"user", "assistant", "tool"}:
            continue
        message: Dict[str, Any] = {"role": role, "content": item.get("content") or ""}
        if role == "assistant" and item.get("metadata", {}).get("tool_calls"):
            message["tool_calls"] = item["metadata"]["tool_calls"]
        if role == "tool":
            message["tool_call_id"] = item.get("tool_call_id")
            message["name"] = item.get("tool_name")
        messages.append(message)
    return messages


@functions_framework.cloud_event
def process_admin_agent_task(cloud_event: CloudEvent) -> None:
    """Claim and execute a newly created admin-agent task."""
    subject = cloud_event.get("subject", "") or ""
    task_id = subject.split("/")[-1]
    if not task_id:
        logger.error("Missing task ID in event subject %s", subject)
        return

    db = _get_fs()
    task_ref = db.collection(_TASKS).document(task_id)

    from google.cloud import firestore  # type: ignore

    @firestore.transactional
    def _claim(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        status = data.get("status")
        if status == "running":
            started_at = _parse_time(data.get("started_at"))
            stale_after = _DEADLINE_SECONDS + 90
            if started_at and (datetime.now(timezone.utc) - started_at).total_seconds() <= stale_after:
                return {"busy": True}
            if data.get("approved_tool_call"):
                transaction.update(
                    ref,
                    {
                        "status": "failed",
                        "error": "Approved operation was interrupted; verify its result before retrying",
                        "updated_at": _now(),
                    },
                )
                return {"abandoned_approval": True, **data}
        elif status != "queued":
            return None
        transaction.update(
            ref,
            {
                "status": "running",
                "started_at": _now(),
                "updated_at": _now(),
                "attempt": int(data.get("attempt") or 0) + 1,
            },
        )
        return data

    task = _claim(db.transaction(), task_ref)
    if task and task.get("busy"):
        raise RuntimeError(f"Task {task_id} is already running; request Eventarc retry")
    if task and task.get("abandoned_approval"):
        _message(
            db,
            task["conversation_id"],
            task_id,
            "assistant",
            "The approved operation was interrupted. Verify the current production state before requesting it again.",
        )
        return
    if task is None:
        logger.info("Task %s already claimed or unavailable", task_id)
        return

    try:
        asyncio.run(_run_task(db, task_ref, {**task, "task_id": task_id}))
    except Exception as exc:
        logger.exception("Admin agent task %s failed", task_id)
        task_ref.set({"status": "failed", "error": str(exc), "updated_at": _now()}, merge=True)
        _message(db, task["conversation_id"], task_id, "assistant", f"Task failed: {exc}")


async def _run_task(db: Any, task_ref: Any, task: Dict[str, Any]) -> None:
    task_id = task["task_id"]
    conversation_id = task["conversation_id"]
    deadline = time.monotonic() + _DEADLINE_SECONDS
    iteration = int(task.get("iteration") or 0)
    continuation_count = int(task.get("continuation_count") or 0)
    total_tokens = int(task.get("total_tokens") or 0)
    cost_usd = float(task.get("cost_usd") or 0.0)

    latest = task_ref.get().to_dict() or {}
    if latest.get("cancel_requested") or latest.get("status") == "cancelled":
        task_ref.set({"status": "cancelled", "updated_at": _now()}, merge=True)
        _message(db, conversation_id, task_id, "assistant", "Task cancelled.")
        return

    approved = task.get("approved_tool_call")
    if approved:
        result = await _execute_tool(approved["name"], approved.get("arguments") or {})
        _message(
            db,
            conversation_id,
            task_id,
            "tool",
            _json_text(result),
            tool_call_id=approved["id"],
            tool_name=approved["name"],
        )

    while iteration < _MAX_ITERATIONS:
        latest = task_ref.get().to_dict() or {}
        if latest.get("cancel_requested"):
            task_ref.set({"status": "cancelled", "updated_at": _now()}, merge=True)
            _message(db, conversation_id, task_id, "assistant", "Task cancelled.")
            return

        if time.monotonic() >= deadline:
            if continuation_count >= _MAX_CONTINUATIONS:
                raise RuntimeError("Admin agent exceeded its continuation limit")
            continuation_id = _new_id()
            now = _now()
            task_ref.set(
                {"status": "continued", "continuation_task_id": continuation_id, "iteration": iteration, "updated_at": now},
                merge=True,
            )
            db.collection(_TASKS).document(continuation_id).set(
                {
                    "task_id": continuation_id,
                    "conversation_id": conversation_id,
                    "status": "queued",
                    "iteration": iteration,
                    "continuation_count": continuation_count + 1,
                    "total_tokens": total_tokens,
                    "cost_usd": cost_usd,
                    "parent_task_id": task_id,
                    "created_at": now,
                    "updated_at": now,
                    "cancel_requested": False,
                }
            )
            return

        messages = [{"role": "system", "content": _SYSTEM_PROMPT}, *_load_messages(db, conversation_id)]
        response = await _call_model(messages)
        usage = response.get("usage") or {}
        total_tokens += int(usage.get("total_tokens") or 0)
        cost_usd += float(usage.get("cost") or 0.0)
        if total_tokens > _MAX_TOTAL_TOKENS:
            raise RuntimeError(f"Admin agent exceeded {_MAX_TOTAL_TOKENS} total tokens")
        if cost_usd > _MAX_COST_USD:
            raise RuntimeError(f"Admin agent exceeded its ${_MAX_COST_USD:.2f} cost limit")
        assistant = response["choices"][0]["message"]
        content = assistant.get("content") or ""
        tool_calls = assistant.get("tool_calls") or []
        _message(
            db,
            conversation_id,
            task_id,
            "assistant",
            content,
            metadata={"tool_calls": tool_calls} if tool_calls else {},
        )

        iteration += 1
        task_ref.set(
            {"iteration": iteration, "total_tokens": total_tokens, "cost_usd": round(cost_usd, 6), "updated_at": _now()},
            merge=True,
        )

        if not tool_calls:
            task_ref.set({"status": "completed", "completed_at": _now(), "updated_at": _now()}, merge=True)
            db.collection(_CONVERSATIONS).document(conversation_id).set({"updated_at": _now()}, merge=True)
            return

        call = tool_calls[0]
        function = call.get("function") or {}
        name = function.get("name") or ""
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError as exc:
            arguments = {}
            result = {"error": f"Invalid tool arguments: {exc}"}
        else:
            if name in _APPROVAL_REQUIRED:
                pending = {"id": call.get("id"), "name": name, "arguments": arguments}
                task_ref.set(
                    {
                        "status": "waiting_approval",
                        "pending_tool_call": pending,
                        "approval_summary": _approval_summary(name, arguments),
                        "iteration": iteration,
                        "updated_at": _now(),
                    },
                    merge=True,
                )
                return
            result = await _execute_tool(name, arguments)

        _message(
            db,
            conversation_id,
            task_id,
            "tool",
            _json_text(result),
            tool_call_id=call.get("id"),
            tool_name=name,
        )

    raise RuntimeError("Admin agent exceeded its iteration limit")


async def _call_model(messages: list[Dict[str, Any]]) -> Dict[str, Any]:
    if not _OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=90) as client:
        for attempt in range(3):
            try:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {_OPENROUTER_API_KEY}",
                        "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://smarter.vote"),
                        "X-OpenRouter-Title": "SmarterVote Admin Agent",
                    },
                    json={
                        "model": _MODEL,
                        "messages": messages,
                        "tools": _TOOLS,
                        "tool_choice": "auto",
                        "parallel_tool_calls": False,
                        "max_tokens": _MAX_OUTPUT_TOKENS,
                    },
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
    raise RuntimeError(f"OpenRouter request failed after retries: {last_error}")


async def _execute_tool(name: str, arguments: Dict[str, Any]) -> Any:
    if not _RACES_API_URL:
        return {"error": "RACES_API_URL is not configured"}
    spec = _TOOL_ROUTES.get(name)
    if spec is None:
        return {"error": f"Unknown tool: {name}"}
    method, path_template, body_builder, query_builder = spec
    try:
        path = path_template.format(**arguments)
    except KeyError as exc:
        return {"error": f"Missing tool argument: {exc}"}
    body = body_builder(arguments) if body_builder else None
    params = query_builder(arguments) if query_builder else None

    last_error = ""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.request(
                    method,
                    f"{_RACES_API_URL}{path}",
                    headers={"X-Admin-Key": _ADMIN_API_KEY, "Accept": "application/json"},
                    params=params,
                    json=body,
                )
            response.raise_for_status()
            return response.json() if response.content else {"ok": True}
        except Exception as exc:
            last_error = str(exc)
            if attempt < 2:
                await asyncio.sleep(2**attempt)
    return {"error": last_error, "tool": name}


def _json_text(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))[:50000]


def _approval_summary(name: str, arguments: Dict[str, Any]) -> str:
    return f"Approve `{name}` with {json.dumps(arguments, default=str)}"


def _tool(name: str, description: str, properties: Dict[str, Any] | None = None, required: list[str] | None = None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


_RACE_ID = {"race_id": {"type": "string", "description": "Canonical lowercase race ID"}}
_RUN_ID = {"run_id": {"type": "string"}}
_RUN_OPTIONS = {
    "cheap_mode": {"type": "boolean"},
    "force_fresh": {"type": "boolean"},
    "save_artifact": {"type": "boolean"},
    "enabled_steps": {"type": "array", "items": {"type": "string"}},
    "research_model": {"type": "string"},
    "claude_model": {"type": "string"},
    "gemini_model": {"type": "string"},
    "grok_model": {"type": "string"},
    "model_profile": {"type": "string", "enum": ["economy", "balanced", "quality", "custom"]},
    "model_overrides": {"type": "object", "additionalProperties": {"type": "string"}},
    "review_providers": {
        "type": "array",
        "items": {"type": "string", "enum": ["claude", "gemini", "grok"]},
    },
    "max_candidates": {"type": "integer", "minimum": 1},
    "candidate_names": {"type": "array", "items": {"type": "string"}},
    "target_no_info": {"type": "boolean"},
    "note": {"type": "string"},
    "goal": {"type": "string"},
}

_TOOLS = [
    _tool("health", "Check races-api health."),
    _tool("list_published_races", "List published race IDs."),
    _tool("list_race_summaries", "List published race summaries."),
    _tool("get_published_race", "Get full published race data.", _RACE_ID, ["race_id"]),
    _tool("list_admin_races", "List admin race records with status and storage metadata."),
    _tool("get_race_record", "Get one admin race record.", _RACE_ID, ["race_id"]),
    _tool("list_draft_races", "List draft race summaries."),
    _tool("list_pipeline_steps", "List supported pipeline steps."),
    _tool(
        "get_race_data",
        "Get full published or draft RaceJSON.",
        {**_RACE_ID, "draft": {"type": "boolean"}},
        ["race_id"],
    ),
    _tool(
        "queue_races",
        "Queue one or more races for pipeline processing.",
        {"race_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1}, **_RUN_OPTIONS},
        ["race_ids"],
    ),
    _tool("run_race", "Queue one race for pipeline processing.", {**_RACE_ID, **_RUN_OPTIONS}, ["race_id"]),
    _tool("publish_race", "Publish a race draft. Requires approval.", _RACE_ID, ["race_id"]),
    _tool("unpublish_race", "Remove a race from the public site. Requires approval.", _RACE_ID, ["race_id"]),
    _tool("recheck_race", "Reconcile one race status.", _RACE_ID, ["race_id"]),
    _tool("recheck_all_races", "Reconcile all race statuses."),
    _tool("cancel_race", "Cancel a queued or running race. Requires approval.", _RACE_ID, ["race_id"]),
    _tool(
        "get_queue",
        "List queue items.",
        {"active_only": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}},
    ),
    _tool("list_runs", "List recent pipeline runs.", {"limit": {"type": "integer", "minimum": 1, "maximum": 200}}),
    _tool("list_active_runs", "List pending and running pipeline runs."),
    _tool("get_run", "Get a pipeline run.", _RUN_ID, ["run_id"]),
    _tool(
        "get_run_logs",
        "Get pipeline run logs.",
        {**_RUN_ID, "since": {"type": "integer", "minimum": 0}},
        ["run_id"],
    ),
    _tool("cancel_or_delete_run", "Cancel an active run or delete a finished run. Requires approval.", _RUN_ID, ["run_id"]),
    _tool("get_pipeline_metrics", "Get recent pipeline token and cost records.", {"limit": {"type": "integer"}}),
    _tool("get_pipeline_metrics_summary", "Get aggregate pipeline cost metrics."),
    _tool("clear_races_api_cache", "Clear the public API cache. Requires approval."),
    _tool("get_analytics_overview", "Get races-api request health analytics.", {"hours": {"type": "integer"}}),
    _tool("get_race_analytics", "Get legacy per-race API request analytics.", {"hours": {"type": "integer"}}),
    _tool(
        "get_analytics_timeseries",
        "Get bucketed races-api request analytics.",
        {
            "hours": {"type": "integer"},
            "bucket_minutes": {"type": "integer", "minimum": 5, "maximum": 360},
        },
    ),
    _tool("get_traffic_analytics", "Get static-site traffic analytics from Cloudflare.", {"hours": {"type": "integer"}}),
]


def _options(args: Dict[str, Any]) -> Dict[str, Any]:
    return {key: args[key] for key in _RUN_OPTIONS if key in args}


_TOOL_ROUTES = {
    "health": ("GET", "/health", None, None),
    "list_published_races": ("GET", "/races", None, None),
    "list_race_summaries": ("GET", "/races/summaries", None, None),
    "get_published_race": ("GET", "/races/{race_id}", None, None),
    "list_admin_races": ("GET", "/api/races", None, None),
    "get_race_record": ("GET", "/api/races/{race_id}", None, None),
    "list_draft_races": ("GET", "/api/races/drafts", None, None),
    "list_pipeline_steps": ("GET", "/steps", None, None),
    "get_race_data": ("GET", "/api/races/{race_id}/data", None, lambda a: {"draft": a.get("draft", False)}),
    "queue_races": (
        "POST",
        "/api/races/queue",
        lambda a: {"race_ids": a["race_ids"], "options": _options(a)},
        None,
    ),
    "run_race": ("POST", "/api/races/{race_id}/run", _options, None),
    "publish_race": ("POST", "/api/races/{race_id}/publish", None, None),
    "unpublish_race": ("POST", "/api/races/{race_id}/unpublish", None, None),
    "recheck_race": ("POST", "/api/races/{race_id}/recheck", None, None),
    "recheck_all_races": ("POST", "/api/races/recheck", None, None),
    "cancel_race": ("POST", "/api/races/{race_id}/cancel", None, None),
    "get_queue": (
        "GET",
        "/api/queue",
        None,
        lambda a: {"active_only": a.get("active_only", False), "limit": a.get("limit", 200)},
    ),
    "list_runs": ("GET", "/runs", None, lambda a: {"limit": a.get("limit", 50)}),
    "list_active_runs": ("GET", "/runs/active", None, None),
    "get_run": ("GET", "/runs/{run_id}", None, None),
    "get_run_logs": ("GET", "/runs/{run_id}/logs", None, lambda a: {"since": a.get("since", 0)}),
    "cancel_or_delete_run": ("DELETE", "/runs/{run_id}", None, None),
    "get_pipeline_metrics": ("GET", "/pipeline/metrics", None, lambda a: {"limit": a.get("limit", 50)}),
    "get_pipeline_metrics_summary": ("GET", "/pipeline/metrics/summary", None, None),
    "clear_races_api_cache": ("POST", "/cache/clear", None, None),
    "get_analytics_overview": ("GET", "/analytics/overview", None, lambda a: {"hours": a.get("hours", 24)}),
    "get_race_analytics": ("GET", "/analytics/races", None, lambda a: {"hours": a.get("hours", 24)}),
    "get_analytics_timeseries": (
        "GET",
        "/analytics/timeseries",
        None,
        lambda a: {"hours": a.get("hours", 24), "bucket": a.get("bucket_minutes", 60)},
    ),
    "get_traffic_analytics": ("GET", "/analytics/traffic", None, lambda a: {"hours": a.get("hours", 24)}),
}

_SYSTEM_PROMPT = """You are the deployed SmarterVote admin agent.
Use tools to inspect and operate the production-shaped races API. Prefer evidence from tools over assumptions.
You may queue pipeline work and monitor its current state, but do not repeatedly poll a long-running pipeline in one task.
Explain completed actions and provide IDs needed to follow up. Publishing, unpublishing, cancellation, deletion, and cache
clearing pause for explicit user approval. Keep responses concise and operationally precise."""
