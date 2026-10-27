"""History of athlete transfers between organizations."""

from datetime import date
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "athlete_organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False
        ),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date()),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date"),
    )
    op.create_index(
        "ix_athlete_organizations_athlete_id", "athlete_organizations", ["athlete_id"]
    )
    # Before the history existed the current organization was the only fact:
    # assume the athlete has been there since the first year of training.
    rows = op.get_bind().execute(
        sa.text(
            "SELECT a.id, a.organization_id, MIN(d.start_year) FROM athletes a "
            "LEFT JOIN athlete_disciplines d ON d.athlete_id = a.id "
            "WHERE a.organization_id IS NOT NULL GROUP BY a.id, a.organization_id"
        )
    )
    op.bulk_insert(
        table,
        [
            {
                "athlete_id": athlete_id,
                "organization_id": organization_id,
                "start_date": date(first_year, 1, 1) if first_year else date.today(),
            }
            for athlete_id, organization_id, first_year in rows
        ],
    )


def downgrade():
    op.drop_index(
        "ix_athlete_organizations_athlete_id", table_name="athlete_organizations"
    )
    op.drop_table("athlete_organizations")
