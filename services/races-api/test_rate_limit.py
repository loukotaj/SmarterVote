from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from rate_limit import FirestoreRateLimitStorage, get_rate_limit_key
from starlette.requests import Request


def _request(origin: str | None = None) -> Request:
    headers = [] if origin is None else [(b"origin", origin.encode())]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": ("203.0.113.5", 1)})


def test_rate_limit_key_ignores_spoofed_prerender_origin():
    assert get_rate_limit_key(_request("http://sveltekit-prerender")) == "203.0.113.5"


def test_firestore_storage_increments_existing_window():
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    snapshot = MagicMock(exists=True)
    snapshot.to_dict.return_value = {"count": 4, "expires_at": expires_at}
    doc_ref = MagicMock()
    doc_ref.get.return_value = snapshot
    collection = MagicMock()
    collection.document.return_value = doc_ref
    db = MagicMock()
    db.collection.return_value = collection
    transaction = MagicMock()
    db.transaction.return_value = transaction
    storage = FirestoreRateLimitStorage("firestore://")
    storage._db = db

    with patch("google.cloud.firestore.transactional", side_effect=lambda fn: fn):
        assert storage.incr("client:/races", 60) == 5

    transaction.set.assert_called_once()
    payload = transaction.set.call_args.args[1]
    assert payload["count"] == 5
    assert payload["expires_at"] == expires_at


def test_firestore_storage_resets_expired_window():
    snapshot = MagicMock(exists=True)
    snapshot.to_dict.return_value = {
        "count": 9,
        "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    doc_ref = MagicMock()
    doc_ref.get.return_value = snapshot
    collection = MagicMock()
    collection.document.return_value = doc_ref
    db = MagicMock()
    db.collection.return_value = collection
    transaction = MagicMock()
    db.transaction.return_value = transaction
    storage = FirestoreRateLimitStorage("firestore://")
    storage._db = db

    with patch("google.cloud.firestore.transactional", side_effect=lambda fn: fn):
        assert storage.incr("client:/races", 60) == 1

    assert transaction.set.call_args.args[1]["count"] == 1


def test_firestore_storage_read_health_and_cleanup_operations():
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    snapshot = MagicMock(exists=True)
    snapshot.to_dict.return_value = {"count": 3, "expires_at": expires_at}
    doc_ref = MagicMock()
    doc_ref.get.return_value = snapshot
    collection = MagicMock()
    collection.document.return_value = doc_ref
    collection.limit.return_value = collection
    cleanup_doc = MagicMock()
    collection.stream.return_value = iter([cleanup_doc])
    db = MagicMock()
    db.collection.return_value = collection
    storage = FirestoreRateLimitStorage("firestore://")
    storage._db = db

    assert storage.get("client:/races") == 3
    assert storage.get_expiry("client:/races") == expires_at.timestamp()
    assert storage.check() is True
    collection.stream.return_value = iter([cleanup_doc])
    assert storage.reset() == 1
    cleanup_doc.reference.delete.assert_called_once_with()
    storage.clear("client:/races")
    doc_ref.delete.assert_called_once_with()
