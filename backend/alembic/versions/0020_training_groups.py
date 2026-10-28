"""Organization cards, training groups, enrollment history and confirmed attendance."""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("license_number", sa.String(160)))
    op.add_column("organizations", sa.Column("license_valid_until", sa.Date()))
    op.add_column("organizations", sa.Column("programs", sa.JSON(), nullable=False, server_default="[]"))
    op.create_table(
        "training_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("discipline_id", sa.Integer(), sa.ForeignKey("disciplines.id"), nullable=False),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coaches.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("stage", sa.String(10), nullable=False),
        sa.Column("program", sa.String(300), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("organization_id", "name"),
        sa.CheckConstraint("stage IN ('np','ut','ssm','vsm')"),
        sa.CheckConstraint("capacity > 0"),
    )
    op.create_table(
        "group_enrollments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("training_groups.id"), nullable=False),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date()),
        sa.Column("order_number", sa.String(120), nullable=False),
        sa.Column("end_order_number", sa.String(120)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date"),
    )
    op.create_table(
        "training_lessons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("training_groups.id"), nullable=False),
        sa.Column("held_on", sa.Date(), nullable=False),
        sa.Column("topic", sa.String(500), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.CheckConstraint("duration_minutes > 0"),
    )
    op.create_table(
        "lesson_attendance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("training_lessons.id"), nullable=False),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("marked_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("lesson_id", "athlete_id"),
        sa.CheckConstraint("status IN ('unmarked','present','absent')"),
    )
    for table, columns in {
        "group_enrollments": ("group_id", "athlete_id"),
        "training_lessons": ("group_id",),
        "lesson_attendance": ("lesson_id", "athlete_id"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table in ("lesson_attendance", "training_lessons", "group_enrollments", "training_groups"):
        op.drop_table(table)
    with op.batch_alter_table("organizations") as batch:
        for name in ("programs", "license_valid_until", "license_number"):
            batch.drop_column(name)
