"""Durable conversation and task API for the deployed admin agent."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import firestore_helpers
from auth import verify_token
from fastapi import APIRouter, Depends, HTTPException
from request_models import AdminAgentMessageRequest

router = APIRouter(prefix="/api/admin-agent", dependencies=[Depends(verify_token)])

_CONVERSATIONS = "admin_agent_conversations"
_MESSAGES = "admin_agent_messages"
_TASKS = "admin_agent_tasks"
_TERMINAL = {"completed", "failed", "cancelled", "continued"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _plain(doc: Any) -> Dict[str, Any] | None:
    return firestore_helpers._doc_to_plain(doc)


def _transactional(func):
    from google.cloud import firestore  # type: ignore

    return firestore.transactional(func)


def _conversation_messages(db: Any, conversation_id: str, limit: int = 200) -> list[Dict[str, Any]]:
    docs = db.collection(_MESSAGES).where("conversation_id", "==", conversation_id).stream()
    messages = [_plain(doc) for doc in docs]
    return sorted(
        (message for message in messages if message is not None),
        key=lambda message: (str(message.get("created_at") or ""), str(message.get("message_id") or "")),
    )[-limit:]


def _conversation_tasks(db: Any, conversation_id: str, limit: int = 20) -> list[Dict[str, Any]]:
    docs = db.collection(_TASKS).where("conversation_id", "==", conversation_id).stream()
    tasks = [_plain(doc) for doc in docs]
    return sorted(
        (task for task in tasks if task is not None),
        key=lambda task: (str(task.get("created_at") or ""), str(task.get("task_id") or "")),
        reverse=True,
    )[:limit]


def _add_message(
    db: Any,
    conversation_id: str,
    role: str,
    content: str,
    *,
    task_id: str | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    message_id = _new_id()
    message = {
        "message_id": message_id,
        "conversation_id": conversation_id,
        "task_id": task_id,
        "role": role,
        "content": content,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "metadata": metadata or {},
        "created_at": _now(),
    }
    db.collection(_MESSAGES).document(message_id).set(message)
    return message


@router.post("/conversations")
async def create_conversation() -> Dict[str, Any]:
    db = firestore_helpers._get_fs()
    conversation_id = _new_id()
    now = _now()
    conversation = {
        "conversation_id": conversation_id,
        "title": "New admin conversation",
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    db.collection(_CONVERSATIONS).document(conversation_id).set(conversation)
    return conversation


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> Dict[str, Any]:
    db = firestore_helpers._get_fs()
    conversation = _plain(db.collection(_CONVERSATIONS).document(conversation_id).get())
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "conversation": conversation,
        "messages": _conversation_messages(db, conversation_id),
        "tasks": _conversation_tasks(db, conversation_id),
    }


@router.get("/conversations")
async def list_conversations() -> Dict[str, Any]:
    db = firestore_helpers._get_fs()
    docs = db.collection(_CONVERSATIONS).order_by("updated_at", direction="DESCENDING").limit(100).stream()
    conversations = [_plain(doc) for doc in docs]
    return {"conversations": [c for c in conversations if c is not None]}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str) -> Dict[str, Any]:
    db = firestore_helpers._get_fs()
    conversation_ref = db.collection(_CONVERSATIONS).document(conversation_id)
    if not conversation_ref.get().exists:
        raise HTTPException(status_code=404, detail="Conversation not found")

    message_docs = db.collection(_MESSAGES).where("conversation_id", "==", conversation_id).stream()
    for doc in message_docs:
        doc.reference.delete()

    task_docs = db.collection(_TASKS).where("conversation_id", "==", conversation_id).stream()
    for doc in task_docs:
        doc.reference.delete()

    conversation_ref.delete()
    return {"message": f"Conversation {conversation_id} deleted", "conversation_id": conversation_id}


@router.post("/conversations/{conversation_id}/messages")
async def submit_message(conversation_id: str, request: AdminAgentMessageRequest) -> Dict[str, Any]:
    db = firestore_helpers._get_fs()
    conversation_ref = db.collection(_CONVERSATIONS).document(conversation_id)
    conversation = conversation_ref.get()
    if not conversation.exists:
        raise HTTPException(status_code=404, detail="Conversation not found")

    active_tasks = [task for task in _conversation_tasks(db, conversation_id) if task.get("status") not in _TERMINAL]
    if active_tasks:
        raise HTTPException(status_code=409, detail="Conversation already has an active task")

    task_id = _new_id()
    _add_message(db, conversation_id, "user", request.content.strip(), task_id=task_id)
    now = _now()
    task = {
        "task_id": task_id,
        "conversation_id": conversation_id,
        "status": "queued",
        "iteration": 0,
        "continuation_count": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "created_at": now,
        "updated_at": now,
        "cancel_requested": False,
        "pending_tool_call": None,
        "error": None,
    }
    db.collection(_TASKS).document(task_id).set(task)

    conv_data = conversation.to_dict() or {}
    current_title = conv_data.get("title", "New admin conversation")

    update_data: Dict[str, Any] = {"updated_at": now, "status": "active"}
    if current_title == "New admin conversation":
        msg_content = request.content.strip()
        new_title = msg_content[:40] + ("..." if len(msg_content) > 40 else "")
        update_data["title"] = new_title

    conversation_ref.set(update_data, merge=True)
    return task


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> Dict[str, Any]:
    task = _plain(firestore_helpers._get_fs().collection(_TASKS).document(task_id).get())
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/tasks/{task_id}/approve")
async def approve_task(task_id: str) -> Dict[str, Any]:
    db = firestore_helpers._get_fs()
    task_ref = db.collection(_TASKS).document(task_id)
    continuation_id = _new_id()
    continuation_ref = db.collection(_TASKS).document(continuation_id)
    now = _now()

    @_transactional
    def approve(transaction):
        snapshot = task_ref.get(transaction=transaction)
        task = _plain(snapshot)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.get("status") == "continued" and task.get("continuation_task_id"):
            return {"existing_continuation_id": task["continuation_task_id"]}
        if task.get("status") != "waiting_approval" or not task.get("pending_tool_call"):
            raise HTTPException(status_code=409, detail="Task is not waiting for approval")

        continuation = {
            "task_id": continuation_id,
            "conversation_id": task["conversation_id"],
            "status": "queued",
            "iteration": int(task.get("iteration") or 0),
            "continuation_count": int(task.get("continuation_count") or 0) + 1,
            "total_tokens": int(task.get("total_tokens") or 0),
            "cost_usd": float(task.get("cost_usd") or 0.0),
            "approved_tool_call": task["pending_tool_call"],
            "parent_task_id": task_id,
            "created_at": now,
            "updated_at": now,
            "cancel_requested": False,
            "pending_tool_call": None,
            "error": None,
        }
        transaction.update(
            task_ref,
            {"status": "continued", "continuation_task_id": continuation_id, "updated_at": now},
        )
        transaction.set(continuation_ref, continuation)
        return continuation

    result = approve(db.transaction())
    existing_id = result.get("existing_continuation_id")
    if existing_id:
        existing = _plain(db.collection(_TASKS).document(existing_id).get())
        if existing is None:
            raise HTTPException(status_code=409, detail="Approval continuation is unavailable")
        return existing
    return result


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> Dict[str, Any]:
    db = firestore_helpers._get_fs()
    task_ref = db.collection(_TASKS).document(task_id)
    now = _now()

    @_transactional
    def cancel(transaction):
        snapshot = task_ref.get(transaction=transaction)
        task = _plain(snapshot)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        continuation_id = task.get("continuation_task_id")
        if task.get("status") == "continued" and continuation_id:
            continuation_ref = db.collection(_TASKS).document(continuation_id)
            continuation = _plain(continuation_ref.get(transaction=transaction))
            if continuation and continuation.get("status") not in _TERMINAL:
                if continuation.get("status") in {"queued", "waiting_approval"}:
                    update = {"status": "cancelled", "cancel_requested": True, "updated_at": now}
                else:
                    update = {"cancel_requested": True, "updated_at": now}
                transaction.update(continuation_ref, update)
                return {"task": {**continuation, **update}, "pending": None}
        if task.get("status") in _TERMINAL:
            return {"task": task, "pending": None}

        if task.get("status") in {"queued", "waiting_approval"}:
            update = {"status": "cancelled", "cancel_requested": True, "updated_at": now}
        else:
            update = {"cancel_requested": True, "updated_at": now}
        transaction.update(task_ref, update)
        pending = task.get("pending_tool_call") if task.get("status") == "waiting_approval" else None
        return {"task": {**task, **update}, "pending": pending}

    result = cancel(db.transaction())
    task = result["task"]
    pending = result["pending"]
    if isinstance(pending, dict):
        _add_message(
            db,
            task["conversation_id"],
            "tool",
            '{"cancelled":true,"reason":"User declined approval"}',
            task_id=task_id,
            tool_call_id=pending.get("id"),
            tool_name=pending.get("name"),
        )
    return task
