"""Persistent limits for numeric Telegram pairing codes."""
from alembic import op
import sqlalchemy as sa

revision = "0008_telegram"
down_revision = "0007_telegram"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("telegram_code_attempts",
        sa.Column("chat_id", sa.BigInteger(), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("telegram_code_attempts")
