"""
scripts/init_db.py — Bootstrap the database and create the first admin user.
Run once after deploying a fresh instance.

Usage:
    python -m scripts.init_db \\
        --org-name "Baba Valve India" \\
        --org-slug "baba-valve-india" \\
        --admin-email admin@example.com \\
        --admin-password "SecurePassword123!"
"""
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys


async def _create_initial_records(
    org_name: str,
    org_slug: str,
    admin_email: str,
    admin_password: str,
) -> None:
    """
    Create the first Organization + admin User.
    This function is filled in during Phase 2 once models are available.
    """
    # Deferred import: models don't exist yet in Phase 1
    try:
        # Phase 2 will add:
        # from app.models.user import Organization, User
        # async with get_db_context() as db:
        #     org = Organization(name=org_name, slug=org_slug)
        #     db.add(org)
        #     await db.flush()
        #     user = User(org_id=org.id, email=admin_email, role="admin",
        #                 hashed_password=hash_password(admin_password))
        #     db.add(user)
        print("  Note: org/user creation requires Phase 2 models.")
        print("  Re-run this script after Phase 2 is deployed.")
    except Exception as exc:
        print(f"  Warning: could not create records: {exc}", file=sys.stderr)


async def init_db(
    org_name: str,
    org_slug: str,
    admin_email: str,
    admin_password: str,
) -> None:
    # 1. Run Alembic migrations
    print("Running Alembic migrations...")
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Migration failed:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    print(result.stdout.strip() or "  Migrations up-to-date.")

    # 2. Create initial records
    print(f"Creating org '{org_name}' and admin user '{admin_email}'...")
    await _create_initial_records(org_name, org_slug, admin_email, admin_password)

    print("\nDatabase initialized successfully.")
    print(f"  Organization : {org_name}  (slug: {org_slug})")
    print(f"  Admin email  : {admin_email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize MOTMVoice database")
    parser.add_argument("--org-name", required=True, help="Display name for the organization")
    parser.add_argument("--org-slug", required=True, help="URL-safe slug (e.g. baba-valve-india)")
    parser.add_argument("--admin-email", required=True, help="Admin user email")
    parser.add_argument("--admin-password", required=True, help="Admin user password (min 8 chars)")
    args = parser.parse_args()

    if len(args.admin_password) < 8:
        print("Error: admin password must be at least 8 characters.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(init_db(args.org_name, args.org_slug, args.admin_email, args.admin_password))


if __name__ == "__main__":
    main()
