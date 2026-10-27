"""Persistent athlete and coach conversations."""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "coach_chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("link_id", sa.Integer(), sa.ForeignKey("athlete_coaches.id"), nullable=False),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sender_role", sa.String(20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_coach_chat_messages_link_id", "coach_chat_messages", ["link_id"])


def downgrade():
    op.drop_index("ix_coach_chat_messages_link_id", table_name="coach_chat_messages")
    op.drop_table("coach_chat_messages")
