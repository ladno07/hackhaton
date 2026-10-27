"""Telegram linking, independent delivery and competition start time."""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("competitions", sa.Column("start_time", sa.Time(), nullable=True))
    op.add_column("competitions", sa.Column("timezone", sa.String(80), nullable=False, server_default="Asia/Yekaterinburg"))
    op.add_column("notifications", sa.Column("telegram_context", sa.JSON(), nullable=True))
    op.create_table("telegram_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("chat_id", sa.BigInteger(), unique=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baseline_id", sa.Integer(), nullable=False),
        sa.Column("blocked_at", sa.DateTime(timezone=True)))
    op.create_table("telegram_link_tokens",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("chat_id", sa.BigInteger()))
    op.create_table("telegram_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("link_id", sa.Integer(), sa.ForeignKey("telegram_links.id"), nullable=False),
        sa.Column("notification_id", sa.Integer(), sa.ForeignKey("notifications.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.UniqueConstraint("link_id", "notification_id"))
    op.create_table("telegram_cursor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("send_after", sa.DateTime(timezone=True)))


def downgrade():
    for table in ("telegram_cursor", "telegram_deliveries", "telegram_link_tokens", "telegram_links"):
        op.drop_table(table)
    op.drop_column("notifications", "telegram_context")
    op.drop_column("competitions", "timezone")
    op.drop_column("competitions", "start_time")
