"""Governor prizes: amounts by rating level and place, decisions on candidates."""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    rules = op.create_table(
        "governor_award_rules",
        sa.Column("level", sa.String(length=40), nullable=False),
        sa.Column("first", sa.Integer(), nullable=False),
        sa.Column("second", sa.Integer(), nullable=False),
        sa.Column("third", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("level"),
    )
    op.bulk_insert(
        rules,
        [
            {"level": "russian_championship", "first": 100000, "second": 75000, "third": 50000},
            {"level": "russian_junior", "first": 60000, "second": 45000, "third": 30000},
            {"level": "interregional", "first": 30000, "second": 20000, "third": 15000},
            {"level": "regional", "first": 0, "second": 0, "third": 0},
        ],
    )
    op.create_table(
        "governor_awards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("basis", sa.JSON(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("order_number", sa.String(length=120), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('nominated','awarded','rejected')",
            name="ck_governor_award_status",
        ),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("year", "athlete_id"),
    )
    op.create_index("ix_governor_awards_year", "governor_awards", ["year"])


def downgrade():
    op.drop_table("governor_awards")
    op.drop_table("governor_award_rules")
