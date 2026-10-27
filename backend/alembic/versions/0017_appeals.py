"""Violations with sanctions and appeals against protocols and violations."""

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "violations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("competition_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sanction", sa.String(length=20), nullable=False),
        sa.Column("suspended_until", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('rules','conduct','doping','other')", name="ck_violation_kind"
        ),
        sa.CheckConstraint(
            "(sanction = 'warning' AND suspended_until IS NULL) OR "
            "(sanction = 'suspension' AND suspended_until IS NOT NULL)",
            name="ck_violation_sanction",
        ),
        sa.CheckConstraint(
            "status IN ('active','cancelled')", name="ck_violation_status"
        ),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"]),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_violations_athlete_id", "violations", ["athlete_id"])
    op.create_table(
        "appeals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=20), nullable=False),
        sa.Column("competition_id", sa.Integer(), nullable=True),
        sa.Column("result_id", sa.Integer(), nullable=True),
        sa.Column("protocol_version", sa.Integer(), nullable=True),
        sa.Column("violation_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("submitted_by", sa.Integer(), nullable=False),
        sa.Column("submitted_role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(subject = 'result' AND result_id IS NOT NULL AND violation_id IS NULL) OR "
            "(subject = 'violation' AND violation_id IS NOT NULL AND result_id IS NULL)",
            name="ck_appeal_subject",
        ),
        sa.CheckConstraint(
            "status IN ('pending','upheld','rejected','withdrawn')",
            name="ck_appeal_status",
        ),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"]),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"]),
        sa.ForeignKeyConstraint(["result_id"], ["competition_results.id"]),
        sa.ForeignKeyConstraint(["violation_id"], ["violations.id"]),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_appeals_athlete_id", "appeals", ["athlete_id"])


def downgrade():
    op.drop_index("ix_appeals_athlete_id", table_name="appeals")
    op.drop_table("appeals")
    op.drop_index("ix_violations_athlete_id", table_name="violations")
    op.drop_table("violations")
