#!/usr/bin/env python3
"""
create_platform_admin.py — Bootstrap a PlatformAdmin (SuperAdmin) account.

Run inside the api container (or locally with the backend venv active):
    python scripts/create_platform_admin.py --email you@example.com --password "..." --full-name "Your Name"
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(_backend_dir))
os.chdir(_backend_dir)

from dotenv import load_dotenv
load_dotenv(_backend_dir / ".env")

from sqlalchemy import select

from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models.platform_admin import PlatformAdmin


async def main(email: str, password: str, full_name: str | None) -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(PlatformAdmin).where(PlatformAdmin.email == email)
        )
        if existing:
            print(f"A platform admin with email {email!r} already exists (id={existing.id}).")
            return

        admin = PlatformAdmin(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        print(f"Created platform admin {admin.email} (id={admin.id}).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap a platform admin account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--full-name", default=None)
    args = parser.parse_args()

    if len(args.password) < 8:
        print("Password must be at least 8 characters.")
        sys.exit(1)

    asyncio.run(main(args.email, args.password, args.full_name))
