"""campaigns.voice_id: per-campaign cloned-voice override

Lets a campaign use one of the org's own cloned voices directly, instead of
always being stuck with whatever voice the chosen agent template has. NULL =
use the agent template's own voice, so every existing campaign keeps
behaving exactly as before. Always ElevenLabs underneath (cloned voices are
ElevenLabs-only), so there's no matching voice_provider column needed here.

Revision ID: 0040
Revises: 0039
Create Date: 2026-10-15
"""
import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("voice_id", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("campaigns", "voice_id")
