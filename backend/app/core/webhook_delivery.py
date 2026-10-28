"""
app/core/webhook_delivery.py — signing, URL safety and payload for the per-org
"call.completed" webhook (customers point this at Zapier/Make/their CRM).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlparse

from app.core.exceptions import ValidationError
from app.core.net_guard import assert_public_host


def new_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(24)


def sign(secret: str, body: bytes, ts: int | None = None) -> str:
    """`t=<unix>,v1=<hmac_sha256(secret, "<t>.<body>")>` — same shape as sign_webhook_payload."""
    ts = int(time.time()) if ts is None else ts
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def assert_public_https_url(url: str) -> None:
    """SSRF guard: https only, and every resolved address must be public."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValidationError("Webhook URL must start with https://")
    assert_public_host(parsed.hostname, parsed.port or 443, "Webhook URL")


def build_payload(call, contact, transcript_segments: list) -> dict:
    return {
        "event": "call.completed",
        "call_id": str(call.id),
        "campaign_id": str(call.campaign_id) if call.campaign_id else None,
        "phone_number": call.phone_number,
        "direction": str(call.direction.value if hasattr(call.direction, "value") else call.direction),
        "status": str(call.status.value if hasattr(call.status, "value") else call.status),
        "outcome": str(call.outcome.value if hasattr(call.outcome, "value") else call.outcome),
        "summary": call.summary,
        "duration_seconds": call.duration_seconds,
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "recording_url": call.recording_url,
        "extracted_data": call.extracted_data or {},
        "contact": {
            "name": contact.name, "email": contact.email, "company": contact.company,
            "custom_fields": contact.custom_fields or {},
        } if contact else None,
        "transcript": transcript_segments,
    }


def encode(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), default=str).encode()
