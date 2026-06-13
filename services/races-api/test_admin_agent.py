"""Tests for durable admin-agent conversation and task persistence."""

import asyncio
from copy import deepcopy

import pytest
from fastapi import HTTPException
from request_models import AdminAgentMessageRequest
from routers import admin_agent


class FakeSnapshot:
    def __init__(self, doc_id, value):
        self.id = doc_id
        self._value = deepcopy(value)
        self.exists = value is not None

    def to_dict(self):
        return deepcopy(self._value)


class FakeDocument:
    def __init__(self, collection, doc_id):
        self.collection = collection
        self.doc_id = doc_id

    def get(self):
        return FakeSnapshot(self.doc_id, self.collection.values.get(self.doc_id))

    def set(self, value, merge=False):
        if merge and self.doc_id in self.collection.values:
            self.collection.values[self.doc_id].update(deepcopy(value))
        else:
            self.collection.values[self.doc_id] = deepcopy(value)


class FakeQuery:
    def __init__(self, collection, field, value):
        self.collection = collection
        self.field = field
        self.value = value

    def stream(self):
        return [
            FakeSnapshot(doc_id, value)
            for doc_id, value in self.collection.values.items()
            if value.get(self.field) == self.value
        ]


class FakeCollection:
    def __init__(self):
        self.values = {}

    def document(self, doc_id):
        return FakeDocument(self, doc_id)

    def where(self, field, _operator, value):
        return FakeQuery(self, field, value)


class FakeFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, FakeCollection())


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeFirestore()
    monkeypatch.setattr(admin_agent.firestore_helpers, "_get_fs", lambda: db)
    return db


def test_create_submit_and_load_conversation(fake_db):
    conversation = asyncio.run(admin_agent.create_conversation())
    task = asyncio.run(
        admin_agent.submit_message(
            conversation["conversation_id"],
            AdminAgentMessageRequest(content="Review stale races"),
        )
    )
    loaded = asyncio.run(admin_agent.get_conversation(conversation["conversation_id"]))

    assert task["status"] == "queued"
    assert loaded["messages"][0]["role"] == "user"
    assert loaded["messages"][0]["content"] == "Review stale races"
    assert loaded["tasks"][0]["task_id"] == task["task_id"]


def test_approve_creates_continuation_task(fake_db):
    conversation = asyncio.run(admin_agent.create_conversation())
    task = asyncio.run(
        admin_agent.submit_message(conversation["conversation_id"], AdminAgentMessageRequest(content="Publish it"))
    )
    task_ref = fake_db.collection(admin_agent._TASKS).document(task["task_id"])
    task_ref.set(
        {
            "status": "waiting_approval",
            "pending_tool_call": {
                "id": "call-1",
                "name": "publish_race",
                "arguments": {"race_id": "ga-senate-2026"},
            },
            "iteration": 2,
        },
        merge=True,
    )

    continuation = asyncio.run(admin_agent.approve_task(task["task_id"]))

    assert continuation["status"] == "queued"
    assert continuation["approved_tool_call"]["name"] == "publish_race"
    assert continuation["iteration"] == 2
    assert task_ref.get().to_dict()["status"] == "continued"


def test_declining_approval_closes_tool_call(fake_db):
    conversation = asyncio.run(admin_agent.create_conversation())
    task = asyncio.run(
        admin_agent.submit_message(conversation["conversation_id"], AdminAgentMessageRequest(content="Unpublish it"))
    )
    fake_db.collection(admin_agent._TASKS).document(task["task_id"]).set(
        {
            "status": "waiting_approval",
            "pending_tool_call": {
                "id": "call-2",
                "name": "unpublish_race",
                "arguments": {"race_id": "ga-senate-2026"},
            },
        },
        merge=True,
    )

    result = asyncio.run(admin_agent.cancel_task(task["task_id"]))
    loaded = asyncio.run(admin_agent.get_conversation(conversation["conversation_id"]))

    assert result["status"] == "cancelled"
    assert loaded["messages"][-1]["role"] == "tool"
    assert loaded["messages"][-1]["tool_call_id"] == "call-2"


def test_submit_message_rejects_pending_approval(fake_db):
    conversation = asyncio.run(admin_agent.create_conversation())
    task = asyncio.run(
        admin_agent.submit_message(
            conversation["conversation_id"],
            AdminAgentMessageRequest(content="Publish it"),
        )
    )
    fake_db.collection(admin_agent._TASKS).document(task["task_id"]).set(
        {
            "status": "waiting_approval",
            "pending_tool_call": {
                "id": "call-1",
                "name": "publish_race",
                "arguments": {"race_id": "tx-governor"},
            },
        },
        merge=True,
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            admin_agent.submit_message(
                conversation["conversation_id"],
                AdminAgentMessageRequest(content="Do something else"),
            )
        )

    assert exc.value.status_code == 409
