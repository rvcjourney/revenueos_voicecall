"""subscriptions: scope the org_id uniqueness to non-deleted rows

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-11

The subscriptions table has always carried a plain UNIQUE(org_id)
constraint, but the model (app/models/subscription.py) documents a
soft-delete-then-insert pattern for recording plan history ("soft-delete +
insert a new row to record a plan change"). Those two things are
incompatible: once any row for an org exists -- soft-deleted or not -- the
plain constraint blocks inserting a replacement, and POST /billing/checkout
(and the superadmin plan-change path in app/api/platform.py) both do exactly
that whenever _active_subscription() finds no *active* row for the org,
which is also true right after a row has been soft-deleted. Replacing the
constraint with a partial unique index on deleted_at IS NULL keeps "one
active subscription per org" while allowing historical soft-deleted rows to
coexist.
"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("subscriptions_org_id_key", "subscriptions", type_="unique")
    op.create_index(
        "ix_subscriptions_org_id_active_unique",
        "subscriptions",
        ["org_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_subscriptions_org_id_active_unique", table_name="subscriptions")
    op.create_unique_constraint("subscriptions_org_id_key", "subscriptions", ["org_id"])
