"""Training standards (FSSP), test results and transfers between stages."""

from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "training_standards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=10), nullable=False),
        sa.Column("category", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("better", sa.String(length=10), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("sex", sa.String(length=10), nullable=True),
        sa.Column("discipline_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("stage IN ('np','ut','ssm','vsm')", name="ck_standard_stage"),
        sa.CheckConstraint("category IN ('ofp','sfp')", name="ck_standard_category"),
        sa.CheckConstraint("better IN ('higher','lower')", name="ck_standard_better"),
        sa.CheckConstraint(
            "sex IS NULL OR sex IN ('male','female')", name="ck_standard_sex"
        ),
        sa.ForeignKeyConstraint(["discipline_id"], ["disciplines.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_training_standards_stage", "training_standards", ["stage"])
    op.create_table(
        "standard_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("standard_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("tested_on", sa.Date(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("recorded_by", sa.Integer(), nullable=True),
        sa.Column("recorded_role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"]),
        sa.ForeignKeyConstraint(["standard_id"], ["training_standards.id"]),
        sa.ForeignKeyConstraint(["recorded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_standard_results_athlete_id", "standard_results", ["athlete_id"]
    )
    op.create_table(
        "stage_transfers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("from_stage", sa.String(length=120), nullable=True),
        sa.Column("to_stage", sa.String(length=10), nullable=False),
        sa.Column("decided_on", sa.Date(), nullable=False),
        sa.Column("order_number", sa.String(length=120), nullable=False),
        sa.Column("basis", sa.JSON(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "to_stage IN ('np','ut','ssm','vsm')", name="ck_transfer_stage"
        ),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_stage_transfers_athlete_id", "stage_transfers", ["athlete_id"]
    )


def downgrade():
    op.drop_index("ix_stage_transfers_athlete_id", table_name="stage_transfers")
    op.drop_table("stage_transfers")
    op.drop_index("ix_standard_results_athlete_id", table_name="standard_results")
    op.drop_table("standard_results")
    op.drop_index("ix_training_standards_stage", table_name="training_standards")
    op.drop_table("training_standards")
