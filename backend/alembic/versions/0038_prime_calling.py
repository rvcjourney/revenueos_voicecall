"""Prime Calling: org company profile + per-contact generated prompts

- org_company_profiles: one row per org describing the calling company, fed
  to the LLM alongside each contact's CSV row (app/services/prime_prompt.py).
- campaigns.is_prime: marks a campaign whose contacts get personalised prompts.
- campaign_contacts.generated_*: the per-contact prompt/welcome message,
  generated just before the first dial attempt and reused on retries.

RLS enabled on the new table with no policies, same reasoning as 0025/0033.

Revision ID: 0038
Revises: 0037
Create Date: 2026-09-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_company_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column("what_we_offer", sa.Text, nullable=True),
        sa.Column("value_proposition", sa.Text, nullable=True),
        sa.Column("target_customers", sa.Text, nullable=True),
        sa.Column("key_points", sa.Text, nullable=True),
        sa.Column("call_objective", sa.Text, nullable=True),
        sa.Column("tone_notes", sa.Text, nullable=True),
        sa.Column("extra_info", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("org_id", name="uq_org_company_profiles_org_id"),
    )
    op.create_index("ix_org_company_profiles_org_id", "org_company_profiles", ["org_id"])
    op.execute("ALTER TABLE org_company_profiles ENABLE ROW LEVEL SECURITY")

    op.add_column("campaigns", sa.Column("is_prime", sa.Boolean, nullable=False, server_default=sa.text("false")))

    op.add_column("campaign_contacts", sa.Column("generated_system_prompt", sa.Text, nullable=True))
    op.add_column("campaign_contacts", sa.Column("generated_welcome_message", sa.Text, nullable=True))
    op.add_column("campaign_contacts", sa.Column("prompt_generated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("campaign_contacts", sa.Column("prompt_error", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("campaign_contacts", "prompt_error")
    op.drop_column("campaign_contacts", "prompt_generated_at")
    op.drop_column("campaign_contacts", "generated_welcome_message")
    op.drop_column("campaign_contacts", "generated_system_prompt")
    op.drop_column("campaigns", "is_prime")
    op.drop_index("ix_org_company_profiles_org_id", table_name="org_company_profiles")
    op.drop_table("org_company_profiles")
