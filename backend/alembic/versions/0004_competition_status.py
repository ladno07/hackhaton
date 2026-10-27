"""Competition status separated from the rating level; rating class of types."""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "competition_types",
        sa.Column(
            "rating_class", sa.String(length=20), nullable=False, server_default="other"
        ),
    )
    op.create_check_constraint(
        "ck_competition_types_rating_class",
        "competition_types",
        "rating_class IN ('main','junior','other')",
    )
    op.execute(
        "UPDATE competition_types SET rating_class = 'main' "
        "WHERE name IN ('Чемпионат', 'Кубок')"
    )
    op.execute(
        "UPDATE competition_types SET rating_class = 'junior' WHERE name = 'Первенство'"
    )
    # seed used to insert explicit ids, leaving the sequence behind
    op.execute(
        "SELECT setval(pg_get_serial_sequence('competition_types', 'id'), "
        "COALESCE(MAX(id), 0) + 1, false) FROM competition_types"
    )

    op.drop_constraint("competitions_level_check", "competitions", type_="check")
    op.alter_column("competitions", "level", new_column_name="rating_level")
    op.add_column("competitions", sa.Column("status", sa.String(length=20)))
    # Existing rating levels already recorded points, so they are kept as is.
    op.execute(
        "UPDATE competitions SET status = CASE "
        "WHEN rating_level IN ('regional', 'interregional') THEN rating_level "
        "ELSE 'national' END"
    )
    op.alter_column("competitions", "status", nullable=False)
    op.create_check_constraint(
        "ck_competitions_status",
        "competitions",
        "status IN ('regional','interregional','national')",
    )
    op.create_check_constraint(
        "ck_competitions_rating_level",
        "competitions",
        "rating_level IN ('regional','interregional','russian_championship','russian_junior')",
    )


def downgrade():
    op.drop_constraint("ck_competitions_rating_level", "competitions", type_="check")
    op.drop_constraint("ck_competitions_status", "competitions", type_="check")
    op.drop_column("competitions", "status")
    op.alter_column("competitions", "rating_level", new_column_name="level")
    op.create_check_constraint(
        "competitions_level_check",
        "competitions",
        "level IN ('regional','interregional','russian_championship','russian_junior')",
    )
    op.drop_constraint(
        "ck_competition_types_rating_class", "competition_types", type_="check"
    )
    op.drop_column("competition_types", "rating_class")
