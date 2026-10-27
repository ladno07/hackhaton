"""Authenticated athlete profiles; permanently retire old public links."""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008_passports"
branch_labels = None
depends_on = None
FLAGS = {
    "show_ranks": True,
    "show_disciplines": True,
    "show_organization": True,
    "show_municipality": True,
    "show_training_stage": False,
    "show_training_years": False,
}


def upgrade():
    for name, default in FLAGS.items():
        op.add_column(
            "passport_publications",
            sa.Column(
                name,
                sa.Boolean(),
                nullable=False,
                server_default=sa.true() if default else sa.false(),
            ),
        )
    op.execute(sa.text("UPDATE passport_publications SET enabled = false, slug = NULL"))


def downgrade():
    for name in reversed(FLAGS):
        op.drop_column("passport_publications", name)
    # Deliberately do not reactivate old public links on downgrade.
