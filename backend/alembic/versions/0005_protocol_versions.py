"""Shared places, team entries and versions of published protocols."""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "competition_results_competition_id_place_key",
        "competition_results",
        type_="unique",
    )
    op.add_column(
        "competition_results",
        sa.Column("team_name", sa.String(length=120), nullable=True),
    )
    op.create_table(
        "protocol_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("competition_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("competition_id", "version"),
    )
    # Already published protocols become version 1 without an author.
    op.execute(
        """
        INSERT INTO protocol_versions
            (competition_id, version, created_at, created_by, reason, entries)
        SELECT c.id, 1, now(), NULL, 'Первичная публикация',
            json_agg(json_build_object(
                'result_id', r.id,
                'athlete_id', r.athlete_id,
                'full_name', u.full_name,
                'organization', COALESCE(o.name, 'Без организации'),
                'team_name', r.team_name,
                'place', r.place,
                'score', r.score
            ) ORDER BY r.place, r.id)
        FROM competitions c
        JOIN competition_results r ON r.competition_id = c.id
        JOIN athletes a ON a.id = r.athlete_id
        JOIN users u ON u.id = a.user_id
        LEFT JOIN organizations o ON o.id = a.organization_id
        WHERE c.state = 'published'
        GROUP BY c.id
        """
    )


def downgrade():
    op.drop_table("protocol_versions")
    op.drop_column("competition_results", "team_name")
    op.create_unique_constraint(
        "competition_results_competition_id_place_key",
        "competition_results",
        ["competition_id", "place"],
    )
