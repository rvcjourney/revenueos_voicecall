"""organizations.smtp_* / imap_*: each org sends (and reads replies) through its own mailbox

Revision ID: 0048
Revises: 0047
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("smtp_host", sa.String(255)),
    ("smtp_port", sa.Integer()),
    ("smtp_security", sa.String(16)),
    ("smtp_username", sa.String(255)),
    ("smtp_password", sa.String(512)),
    ("smtp_from_email", sa.String(255)),
    ("smtp_from_name", sa.String(255)),
    ("imap_host", sa.String(255)),
    ("imap_last_uid", sa.Integer()),
)


def upgrade() -> None:
    for name, type_ in _COLUMNS:
        op.add_column("organizations", sa.Column(name, type_, nullable=True))
    # One mailbox can serve only one customer.
    op.create_index(
        "uq_organizations_smtp_from_email", "organizations", [sa.text("lower(smtp_from_email)")],
        unique=True, postgresql_where=sa.text("smtp_from_email IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_organizations_smtp_from_email", table_name="organizations")
    for name, _ in reversed(_COLUMNS):
        op.drop_column("organizations", name)
