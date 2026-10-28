"""agent_templates.brochure_*: brochure the agent emails when a customer asks for it

Revision ID: 0049
Revises: 0048
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("brochure_key", sa.String(512)),
    ("brochure_filename", sa.String(255)),
    ("brochure_content_type", sa.String(100)),
    ("brochure_email_subject", sa.String(255)),
    ("brochure_email_body", sa.Text()),
)


def upgrade() -> None:
    for name, type_ in _COLUMNS:
        op.add_column("agent_templates", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column("agent_templates", name)
