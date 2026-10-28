"""Training schedule and attendance lifecycle; historical journal stays completed."""
from alembic import op
import sqlalchemy as sa

revision = "0021_training"
down_revision = "0020_training"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("start_time", sa.Time()),
        sa.Column("timezone", sa.String(80), nullable=False, server_default="Asia/Yekaterinburg"),
        sa.Column("format", sa.String(20), nullable=False, server_default="onsite"),
        sa.Column("location", sa.String(500), nullable=False, server_default=""),
        sa.Column("meeting_url", sa.String(2000)),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("cancellation_reason", sa.String(1000)),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    ):
        op.add_column("training_lessons", column)
    op.add_column("lesson_attendance", sa.Column("dispute_reason", sa.String(1000)))


def downgrade():
    with op.batch_alter_table("lesson_attendance") as batch:
        batch.drop_column("dispute_reason")
    with op.batch_alter_table("training_lessons") as batch:
        for name in ("revision", "cancellation_reason", "status", "instructions", "meeting_url", "location", "format", "timezone", "start_time"):
            batch.drop_column(name)
