"""Lesson materials and correspondence assignments, without live meeting requirements."""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("training_lessons", sa.Column("due_on", sa.Date()))
    op.create_table(
        "training_materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("training_lessons.id"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("url", sa.String(2000)),
        sa.Column("filename", sa.String(255)),
        sa.Column("content_type", sa.String(120)),
        sa.Column("size", sa.Integer()),
        sa.Column("data", sa.LargeBinary()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind IN ('file','link')"),
        sa.CheckConstraint("(kind = 'file' AND data IS NOT NULL AND url IS NULL AND filename IS NOT NULL AND size > 0) OR (kind = 'link' AND url IS NOT NULL AND data IS NULL AND filename IS NULL)"),
    )
    op.create_index("ix_training_materials_lesson_id", "training_materials", ["lesson_id"])


def downgrade():
    op.drop_table("training_materials")
    with op.batch_alter_table("training_lessons") as batch:
        batch.drop_column("due_on")
