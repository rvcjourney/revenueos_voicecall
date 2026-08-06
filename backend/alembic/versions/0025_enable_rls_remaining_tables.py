"""Enable RLS on remaining public tables

Supabase's Advisor flags any public-schema table with RLS disabled as a
CRITICAL security issue, because Supabase auto-exposes every public table
over its PostgREST API to anyone holding the project's anon key unless RLS
blocks it. This app doesn't use PostgREST/Supabase client SDKs anywhere
(the backend connects with the `postgres` role directly, which has
BYPASSRLS and owns every table, so it is completely unaffected by RLS) --
but Supabase is still reachable over its own REST endpoint by default, so
leaving these tables open is a real hole if the anon key ever leaks.

No policies are added: the only role that ever queries these tables
(`postgres`) bypasses RLS automatically as the table owner, so enabling
RLS with zero policies simply locks out `anon`/`authenticated` (the
PostgREST roles) entirely, which is exactly the desired outcome.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-07
"""
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

TABLES = [
    "agent_access_requests",
    "agent_creation_requests",
    "alembic_version",
    "audit_log",
    "campaign_folders",
    "cloned_voices",
    "inbound_agent_templates",
    "plans",
    "platform_admins",
    "platform_cost_settings",
    "prompt_library_entries",
    "prompt_library_versions",
    "subscriptions",
    "user_sip_trunks",
    "voice_clone_requests",
]


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
