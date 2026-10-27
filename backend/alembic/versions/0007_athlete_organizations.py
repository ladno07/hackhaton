"""History of athlete transfers between organizations."""

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
    athletes = sa.table("athletes", sa.column("id"), sa.column("organization_id"))
    disciplines = sa.table(
        "athlete_disciplines", sa.column("athlete_id"), sa.column("start_year")
    )
    year_text = sa.cast(sa.func.min(disciplines.c.start_year), sa.String()) + "-01-01"
    year_date = (
        sa.func.date(year_text)
        if op.get_bind().dialect.name == "sqlite"
        else sa.cast(year_text, sa.Date())
    )
    query = (
        sa.select(
            athletes.c.id,
            athletes.c.organization_id,
            sa.func.coalesce(year_date, sa.func.current_date()),
        )
        .select_from(
            athletes.outerjoin(disciplines, disciplines.c.athlete_id == athletes.c.id)
        )
        .where(athletes.c.organization_id.is_not(None))
        .group_by(athletes.c.id, athletes.c.organization_id)
    )
    op.execute(
        table.insert().from_select(
            ["athlete_id", "organization_id", "start_date"], query
        )
    )


def downgrade():
    op.drop_index(
        "ix_athlete_organizations_athlete_id", table_name="athlete_organizations"
    )
    op.drop_table("athlete_organizations")
