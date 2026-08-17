"""Enable RLS on invoice_counters and invoices

0031_gst_tax_invoices created these two tables without enabling RLS,
missing the precedent set in 0025_enable_rls_remaining_tables (see that
migration's docstring for the full rationale: Supabase auto-exposes every
public-schema table over PostgREST to anyone holding the anon key unless
RLS blocks it -- the backend itself is unaffected since it connects as
`postgres`, which owns these tables and bypasses RLS automatically).

No policies added, same reasoning as 0025: enabling RLS with zero
policies simply locks out anon/authenticated (the PostgREST roles)
entirely, which is the desired outcome for tables only `postgres` ever
queries.

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-17
"""
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

TABLES = ["invoice_counters", "invoices"]


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
