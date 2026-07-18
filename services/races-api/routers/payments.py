"""Stripe payment checkout and webhook endpoints."""

import logging
import os
import re
from typing import Literal

import stripe
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from rate_limit import limiter

logger = logging.getLogger("pipeline")

router = APIRouter(prefix="/payments", tags=["payments"])

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
_STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Preset amounts in cents — must match the frontend tier list
PRESET_AMOUNTS_CENTS = {500, 1000, 2500, 5000}
MIN_CUSTOM_CENTS = 100  # $1.00
MAX_CUSTOM_CENTS = 100_000  # $1,000.00

# Checkout return locations are derived server-side from an exact browser origin.
_ALLOWED_ORIGINS = {
    "https://smarter.vote",
    "https://www.smarter.vote",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
}
_CHECKOUT_SESSION_ID = re.compile(r"^cs_(?:test_|live_)?[A-Za-z0-9]+$")


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_cents: int = Field(..., gt=0, strict=True, description="Amount in cents (e.g. 1000 = $10.00)")
    mode: Literal["payment", "subscription"] = Field(..., description="payment = one-time, subscription = monthly")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_amount(amount_cents: int) -> None:
    if amount_cents in PRESET_AMOUNTS_CENTS:
        return
    if MIN_CUSTOM_CENTS <= amount_cents <= MAX_CUSTOM_CENTS:
        return
    raise HTTPException(
        status_code=400,
        detail=f"Amount must be one of {sorted(PRESET_AMOUNTS_CENTS)} or between {MIN_CUSTOM_CENTS} and {MAX_CUSTOM_CENTS} cents.",
    )


def _checkout_origin(request: Request) -> str:
    origin = request.headers.get("origin", "").rstrip("/")
    if origin not in _ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="Checkout is not available from this origin.")
    return origin


def _validate_session_id(session_id: str) -> None:
    if not _CHECKOUT_SESSION_ID.fullmatch(session_id):
        raise HTTPException(status_code=400, detail="Invalid checkout session ID.")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/checkout")
@limiter.limit("10/minute")
async def create_checkout_session(body: CheckoutRequest, request: Request):
    """Create a Stripe Checkout session and return the hosted session URL."""
    if not _STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payments are not yet available.")

    _validate_amount(body.amount_cents)
    origin = _checkout_origin(request)

    price_data: dict = {
        "currency": "usd",
        "unit_amount": body.amount_cents,
        "product_data": {
            "name": "Support Smarter.Vote",
            "description": "Funds election research and coverage by Smarter.Vote LLC.",
        },
    }

    if body.mode == "subscription":
        price_data["recurring"] = {"interval": "month"}

    try:
        session = stripe.checkout.Session.create(
            mode=body.mode,
            line_items=[{"price_data": price_data, "quantity": 1}],
            success_url=f"{origin}/support/success/?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/support/cancel/",
            api_key=_STRIPE_SECRET_KEY,
        )
    except stripe.StripeError as exc:
        logger.error("Stripe checkout error: %s", exc)
        raise HTTPException(status_code=502, detail="Could not create checkout session.") from exc

    if not session.url:
        logger.error("Stripe checkout session %s did not include a redirect URL", session.id)
        raise HTTPException(status_code=502, detail="Could not create checkout session.")

    return {"url": session.url}


@router.get("/session/{session_id}")
@limiter.limit("30/minute")
async def checkout_session_status(session_id: str, request: Request, response: Response):
    """Confirm a checkout result with Stripe; never infer success from a redirect alone."""
    if not _STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payments are not yet available.")
    _validate_session_id(session_id)

    try:
        session = stripe.checkout.Session.retrieve(session_id, api_key=_STRIPE_SECRET_KEY)
    except stripe.StripeError as exc:
        logger.warning("Could not retrieve Stripe checkout session %s: %s", session_id, exc)
        raise HTTPException(status_code=502, detail="Could not verify checkout status.") from exc

    response.headers["Cache-Control"] = "no-store"
    confirmed = session.status == "complete" and session.payment_status in {"paid", "no_payment_required"}
    return {"status": "confirmed" if confirmed else "pending", "mode": session.mode}


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events (signature-verified)."""
    if not _STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook not configured.")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, _STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError):
        logger.warning("Stripe webhook signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        logger.info(
            "checkout.session.completed session_id=%s amount=%s mode=%s",
            obj.get("id"),
            obj.get("amount_total"),
            obj.get("mode"),
        )
    elif event_type == "invoice.payment_succeeded":
        logger.info(
            "invoice.payment_succeeded invoice_id=%s amount=%s subscription=%s",
            obj.get("id"),
            obj.get("amount_paid"),
            obj.get("subscription"),
        )
    elif event_type in ("customer.subscription.deleted", "customer.subscription.updated"):
        logger.info(
            "%s subscription_id=%s status=%s",
            event_type,
            obj.get("id"),
            obj.get("status"),
        )

    return Response(status_code=200)
