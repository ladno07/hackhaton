"""Logins on testing systems entered by athletes wait for the federation."""

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "athlete_platform_logins",
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # logins saved before the rule were accepted as they are
    op.execute("UPDATE athlete_platform_logins SET confirmed = true")


def downgrade():
    op.drop_column("athlete_platform_logins", "confirmed")
