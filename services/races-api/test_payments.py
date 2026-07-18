"""Focused tests for the public Stripe checkout boundary."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import payments
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded


def _client() -> TestClient:
    payments.limiter.reset()
    app = FastAPI()
    app.state.limiter = payments.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(payments.router)
    return TestClient(app)


def test_checkout_derives_return_urls_from_exact_origin(monkeypatch):
    monkeypatch.setattr(payments, "_STRIPE_SECRET_KEY", "test-server-key")
    create = MagicMock(
        return_value=SimpleNamespace(
            id="cs_test_example",
            url="https://checkout.stripe.com/c/pay/example",
        )
    )
    monkeypatch.setattr(payments.stripe.checkout.Session, "create", create)

    response = _client().post(
        "/payments/checkout",
        headers={"Origin": "https://smarter.vote"},
        json={"amount_cents": 1000, "mode": "payment"},
    )

    assert response.status_code == 200
    request = create.call_args.kwargs
    assert request["success_url"] == "https://smarter.vote/support/success/?session_id={CHECKOUT_SESSION_ID}"
    assert request["cancel_url"] == "https://smarter.vote/support/cancel/"
    assert request["api_key"] == "test-server-key"


def test_checkout_rejects_untrusted_origin_and_client_redirects(monkeypatch):
    monkeypatch.setattr(payments, "_STRIPE_SECRET_KEY", "test-server-key")
    client = _client()

    assert (
        client.post(
            "/payments/checkout",
            headers={"Origin": "https://example.com"},
            json={"amount_cents": 1000, "mode": "payment"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/payments/checkout",
            headers={"Origin": "https://smarter.vote"},
            json={
                "amount_cents": 1000,
                "mode": "payment",
                "success_url": "https://example.com",
            },
        ).status_code
        == 422
    )


def test_session_status_is_verified_with_stripe(monkeypatch):
    monkeypatch.setattr(payments, "_STRIPE_SECRET_KEY", "test-server-key")
    retrieve = MagicMock(return_value=SimpleNamespace(status="complete", payment_status="paid", mode="payment"))
    monkeypatch.setattr(payments.stripe.checkout.Session, "retrieve", retrieve)

    response = _client().get("/payments/session/cs_test_example")

    assert response.status_code == 200
    assert response.json() == {"status": "confirmed", "mode": "payment"}
    assert response.headers["cache-control"] == "no-store"
    retrieve.assert_called_once_with("cs_test_example", api_key="test-server-key")


def test_checkout_is_rate_limited(monkeypatch):
    monkeypatch.setattr(payments, "_STRIPE_SECRET_KEY", "test-server-key")
    monkeypatch.setattr(
        payments.stripe.checkout.Session,
        "create",
        MagicMock(
            return_value=SimpleNamespace(
                id="cs_test_example",
                url="https://checkout.stripe.com/c/pay/example",
            )
        ),
    )
    client = _client()
    request = {
        "headers": {"Origin": "https://smarter.vote"},
        "json": {"amount_cents": 1000, "mode": "payment"},
    }

    for _ in range(10):
        assert client.post("/payments/checkout", **request).status_code == 200
    assert client.post("/payments/checkout", **request).status_code == 429


def test_webhook_rejects_malformed_payload(monkeypatch):
    monkeypatch.setattr(payments, "_STRIPE_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setattr(
        payments.stripe.Webhook,
        "construct_event",
        MagicMock(side_effect=ValueError("invalid payload")),
    )

    response = _client().post(
        "/payments/webhook",
        content=b"not-json",
        headers={"stripe-signature": "invalid"},
    )
    assert response.status_code == 400
