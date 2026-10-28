"""Athlete logins on testing systems and the source of an imported protocol."""

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "athlete_platform_logins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("login", sa.String(length=100), nullable=False),
        sa.Column("login_key", sa.String(length=100), nullable=False),
        sa.CheckConstraint(
            "platform IN ('codeforces','yandex_contest','ctfd')", name="ck_platform_login"
        ),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("athlete_id", "platform"),
        sa.UniqueConstraint("platform", "login_key"),
    )
    op.create_index(
        "ix_athlete_platform_logins_athlete_id", "athlete_platform_logins", ["athlete_id"]
    )
    op.add_column("competitions", sa.Column("results_source", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("competitions", "results_source")
    op.drop_index("ix_athlete_platform_logins_athlete_id", "athlete_platform_logins")
    op.drop_table("athlete_platform_logins")
