#!/usr/bin/env python3
"""
replay_failed_reports.py — Resend agent-report payloads that failed to reach the
backend after all retries (see _persist_failed_report in agent.py).

Each line in FAILED_REPORTS_PATH (default: failed_reports.jsonl, next to this
script) is one lost call report: {"call_id", "failed_at", "error", "payload"}.
This POSTs each payload to the same /api/calls/{call_id}/agent-report endpoint
the agent itself uses, then rewrites the file to keep only the ones that still
failed — so it's safe to re-run.

Run from the agent/ directory (or wherever FAILED_REPORTS_PATH points):
    python replay_failed_reports.py
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

import httpx

from config import AGENT_WEBHOOK_SECRET, BACKEND_INTERNAL_URL, FAILED_REPORTS_PATH


def _sign_webhook_body(body: bytes) -> str:
    """Same HMAC-SHA256 scheme as agent.py's _sign_webhook_body / app/core/security.py
    on the backend — /agent-report now requires this on every request."""
    ts = int(time.time())
    signed = f"{ts}.".encode() + body
    mac = hmac.new(AGENT_WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


async def replay() -> None:
    path = Path(FAILED_REPORTS_PATH)
    if not path.exists():
        print(f"No failed reports at {path} — nothing to do.")
        return

    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        print(f"{path} is empty — nothing to do.")
        return

    print(f"Found {len(lines)} failed report(s) in {path}.\n")
    still_failed: list[str] = []
    ok = 0

    async with httpx.AsyncClient(timeout=10.0) as http:
        for i, line in enumerate(lines, 1):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[{i:>3}/{len(lines)}] → skip (malformed line: {exc})")
                still_failed.append(line)
                continue
            call_id = entry.get("call_id")
            payload = entry.get("payload", {})
            print(f"[{i:>3}/{len(lines)}] call={call_id}", end="  ")

            if not call_id:
                print("→ skip (no call_id)")
                still_failed.append(line)
                continue

            try:
                body = json.dumps(payload).encode()
                resp = await http.post(
                    f"{BACKEND_INTERNAL_URL}/api/calls/{call_id}/agent-report",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": _sign_webhook_body(body),
                    },
                )
                resp.raise_for_status()
                print("→ ok")
                ok += 1
            except Exception as exc:
                print(f"→ still failing: {exc}")
                still_failed.append(line)

    path.write_text("\n".join(still_failed) + ("\n" if still_failed else ""), encoding="utf-8")

    print(f"\nDone: {ok} resent, {len(still_failed)} still failing (left in {path}).")


if __name__ == "__main__":
    try:
        asyncio.run(replay())
    except KeyboardInterrupt:
        sys.exit(1)
