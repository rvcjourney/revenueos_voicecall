"""deliver_webhook against a real local HTTP receiver (DB lookups stubbed)."""
import hashlib
import hmac
import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.crypto import encrypt_value
from app.workers.tasks import webhook as task


def _receiver(status: int):
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.headers["X-MOTM-Signature"], self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(status)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


class _Session:
    def __init__(self, call, org, contact):
        self._m = {id(type(call)): call}
        self.call, self.org, self.contact = call, org, contact

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, model, _id):
        return {"Call": self.call, "Organization": self.org, "CampaignContact": self.contact}[model.__name__]

    async def execute(self, _q):
        return SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(segments=[{"speaker": "user", "text": "hi"}]))


@pytest.fixture
def setup(monkeypatch):
    def make(status):
        srv, seen = _receiver(status)
        call = SimpleNamespace(
            id=uuid4(), org_id=uuid4(), campaign_id=None, contact_id=uuid4(), phone_number="+911234567890",
            direction="outbound", status="completed", outcome="interested", summary="ok", duration_seconds=42,
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc), ended_at=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
            recording_url=None,
            extracted_data={"budget": "5L"},
        )
        org = SimpleNamespace(webhook_url=f"https://127.0.0.1:{srv.server_port}/h", webhook_secret=encrypt_value("whsec_t"))
        contact = SimpleNamespace(name="Asha", email=None, company="Acme", custom_fields={"city": "Pune"})
        monkeypatch.setattr(task, "AsyncSessionLocal", lambda: _Session(call, org, contact))
        monkeypatch.setattr(task.wd, "assert_public_https_url", lambda u: None)
        # Receiver is plain http on loopback; point the client at http instead of https.
        org.webhook_url = org.webhook_url.replace("https://", "http://")
        return call, seen

    return make


async def test_delivers_signed_payload(setup):
    call, seen = setup(200)
    await task._send_async(str(call.id))
    sig, body = seen[0]
    ts = sig.split(",")[0][2:]
    mac = hmac.new(b"whsec_t", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    assert sig == f"t={ts},v1={mac}"
    data = json.loads(body)
    assert data["event"] == "call.completed" and data["outcome"] == "interested"
    assert data["extracted_data"] == {"budget": "5L"}
    assert data["contact"]["custom_fields"] == {"city": "Pune"}
    assert data["transcript"] == [{"speaker": "user", "text": "hi"}]


async def test_waits_until_call_is_finalized_then_sends_anyway_after_cap(setup):
    call, seen = setup(200)
    call.ended_at = None  # agent reported before the dispatcher finalized the call
    assert await task._send_async(str(call.id), wait_attempt=0) is False and not seen
    assert await task._send_async(str(call.id), wait_attempt=task.MAX_WAIT_ATTEMPTS) is True
    assert len(seen) == 1  # never finalized: sent after the cap rather than dropped


async def test_non_2xx_raises_so_celery_retries(setup):
    call, _ = setup(500)
    with pytest.raises(Exception):
        await task._send_async(str(call.id))
