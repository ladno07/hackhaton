"""Cards of coaches and judges: contacts, disciplines and archive."""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TABLES = ["coaches", "judges"]


def upgrade():
    op.add_column(
        "judges",
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
    )
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "municipality",
                sa.String(length=120),
                nullable=False,
                server_default="Оренбург",
            ),
        )
        op.add_column(table, sa.Column("phone", sa.String(length=30)))
        op.add_column(table, sa.Column("contact_email", sa.String(length=254)))
        op.add_column(table, sa.Column("qualification", sa.String(length=200)))
        op.add_column(table, sa.Column("experience_since", sa.Integer()))
        op.add_column(table, sa.Column("about", sa.Text()))
        op.add_column(table, sa.Column("archived_at", sa.DateTime(timezone=True)))
        op.add_column(table, sa.Column("archive_reason", sa.Text()))
    for owner, table in [("coach", "coaches"), ("judge", "judges")]:
        op.create_table(
            f"{owner}_disciplines",
            sa.Column(f"{owner}_id", sa.Integer(), nullable=False),
            sa.Column("discipline_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint([f"{owner}_id"], [f"{table}.id"]),
            sa.ForeignKeyConstraint(["discipline_id"], ["disciplines.id"]),
            sa.PrimaryKeyConstraint(f"{owner}_id", "discipline_id"),
        )


def downgrade():
    op.drop_table("judge_disciplines")
    op.drop_table("coach_disciplines")
    for table in TABLES:
        for column in [
            "archive_reason",
            "archived_at",
            "about",
            "experience_since",
            "qualification",
            "contact_email",
            "phone",
            "municipality",
        ]:
            op.drop_column(table, column)
    op.drop_column("judges", "organization_id")
