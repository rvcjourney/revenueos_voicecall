#!/usr/bin/env python3
"""Debug script — prints raw Vobiz CDR and Recording API responses."""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path

_backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(_backend_dir))
os.chdir(_backend_dir)

from dotenv import load_dotenv
load_dotenv(_backend_dir / ".env")

import aiohttp
from app.config import settings

VOBIZ_BASE = "https://api.vobiz.ai/api/v1"

def hdrs():
    return {
        "X-Auth-ID": settings.VOBIZ_AUTH_ID,
        "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
        "Content-Type": "application/json",
    }

async def main():
    print(f"Auth ID : {settings.VOBIZ_AUTH_ID}")
    print(f"Auth Tok: {settings.VOBIZ_AUTH_TOKEN[:10]}...\n")

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as http:

        # ── 1. Recent CDR ──────────────────────────────────────────────────────
        url = f"{VOBIZ_BASE}/Account/{settings.VOBIZ_AUTH_ID}/cdr/recent"
        print(f"GET {url}")
        async with http.get(url, headers=hdrs(), timeout=aiohttp.ClientTimeout(total=15)) as r:
            print(f"  Status: {r.status}")
            text = await r.text()
            try:
                data = json.loads(text)
                print("  Keys:", list(data.keys()))
                # Print first record if any
                for key in ("objects", "calls", "data", "cdrs", "records"):
                    records = data.get(key)
                    if records:
                        print(f"  '{key}' has {len(records)} records")
                        print("  First record keys:", list(records[0].keys()))
                        print("  First record:\n", json.dumps(records[0], indent=4))
                        break
                else:
                    print("  Full response:\n", json.dumps(data, indent=2)[:2000])
            except Exception as e:
                print("  Raw text (first 500):", text[:500])

        print()

        # ── 2. CDR with date filter ────────────────────────────────────────────
        url2 = f"{VOBIZ_BASE}/Account/{settings.VOBIZ_AUTH_ID}/cdr"
        params = {"start_date": "2026-05-13", "end_date": "2026-05-15", "call_direction": "outbound", "per_page": "10"}
        print(f"GET {url2}  params={params}")
        async with http.get(url2, headers=hdrs(), params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
            print(f"  Status: {r.status}")
            text = await r.text()
            try:
                data = json.loads(text)
                print("  Keys:", list(data.keys()))
                for key in ("objects", "calls", "data", "cdrs", "records"):
                    records = data.get(key)
                    if records:
                        print(f"  '{key}' has {len(records)} records")
                        print("  First record keys:", list(records[0].keys()))
                        print("  First record:\n", json.dumps(records[0], indent=4))
                        break
                else:
                    print("  Full response:\n", json.dumps(data, indent=2)[:2000])
            except Exception as e:
                print("  Raw text (first 500):", text[:500])

        print()

        # ── 3. Recordings list ─────────────────────────────────────────────────
        url3 = f"{VOBIZ_BASE}/Account/{settings.VOBIZ_AUTH_ID}/Recording/"
        print(f"GET {url3}")
        async with http.get(url3, headers=hdrs(), timeout=aiohttp.ClientTimeout(total=15)) as r:
            print(f"  Status: {r.status}")
            text = await r.text()
            try:
                data = json.loads(text)
                print("  Keys:", list(data.keys()))
                for key in ("objects", "recordings", "data", "records"):
                    records = data.get(key)
                    if records:
                        print(f"  '{key}' has {len(records)} records")
                        print("  First record keys:", list(records[0].keys()))
                        print("  First record:\n", json.dumps(records[0], indent=4))
                        break
                else:
                    print("  Full response:\n", json.dumps(data, indent=2)[:2000])
            except Exception as e:
                print("  Raw text (first 500):", text[:500])

asyncio.run(main())
