"""Competition teams, confirmed rosters and team applications."""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("competitions") as batch:
        batch.add_column(
            sa.Column(
                "entry_mode", sa.String(20), nullable=False, server_default="individual"
            )
        )
        batch.add_column(
            sa.Column("team_min", sa.Integer(), nullable=False, server_default="2")
        )
        batch.add_column(
            sa.Column("team_max", sa.Integer(), nullable=False, server_default="3")
        )
        batch.add_column(
            sa.Column(
                "team_rating", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch.create_check_constraint(
            "ck_comp_entry_mode", "entry_mode IN ('individual','team')"
        )
        batch.create_check_constraint(
            "ck_comp_team_size",
            "team_min >= 1 AND team_max >= team_min AND team_max <= 50",
        )
    op.create_table(
        "competition_teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "competition_id",
            sa.Integer(),
            sa.ForeignKey("competitions.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "captain_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False
        ),
        sa.Column(
            "created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "competition_id"),
        sa.UniqueConstraint("competition_id", "name"),
        sa.CheckConstraint(
            "status IN ('draft','pending','approved','returned','cancelled')"
        ),
    )
    op.create_table(
        "competition_team_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("competition_id", sa.Integer(), nullable=False),
        sa.Column(
            "athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["team_id", "competition_id"],
            ["competition_teams.id", "competition_teams.competition_id"],
        ),
        sa.UniqueConstraint("team_id", "athlete_id"),
        sa.CheckConstraint("status IN ('invited','accepted','declined')"),
    )
    op.create_index(
        "uq_team_accepted_athlete",
        "competition_team_members",
        ["competition_id", "athlete_id"],
        unique=True,
        postgresql_where=sa.text("status = 'accepted'"),
        sqlite_where=sa.text("status = 'accepted'"),
    )


def downgrade():
    op.drop_index("uq_team_accepted_athlete", table_name="competition_team_members")
    op.drop_table("competition_team_members")
    op.drop_table("competition_teams")
    with op.batch_alter_table("competitions") as batch:
        batch.drop_constraint("ck_comp_team_size", type_="check")
        batch.drop_constraint("ck_comp_entry_mode", type_="check")
        for name in ["team_rating", "team_max", "team_min", "entry_mode"]:
            batch.drop_column(name)
