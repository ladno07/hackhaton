"""Age groups directory, competition groups and athlete sex."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("sex", sa.String(length=10), nullable=True))
    op.create_check_constraint(
        "ck_users_sex", "users", "sex IS NULL OR sex IN ('male','female')"
    )
    op.create_table(
        "age_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("discipline_id", sa.Integer(), nullable=True),
        sa.Column("sex", sa.String(length=10), nullable=True),
        sa.Column("min_age", sa.Integer(), nullable=False),
        sa.Column("max_age", sa.Integer(), nullable=False),
        sa.Column("age_rule", sa.String(length=10), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("min_age <= max_age"),
        sa.CheckConstraint("sex IS NULL OR sex IN ('male','female')"),
        sa.CheckConstraint("age_rule IN ('year','start')"),
        sa.ForeignKeyConstraint(["discipline_id"], ["disciplines.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "competition_age_groups",
        sa.Column("competition_id", sa.Integer(), nullable=False),
        sa.Column("age_group_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["competition_id"], ["competitions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["age_group_id"], ["age_groups.id"]),
        sa.PrimaryKeyConstraint("competition_id", "age_group_id"),
    )
    op.add_column(
        "competition_applications",
        sa.Column("age_group_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_competition_applications_age_group",
        "competition_applications",
        "age_groups",
        ["age_group_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint(
        "fk_competition_applications_age_group",
        "competition_applications",
        type_="foreignkey",
    )
    op.drop_column("competition_applications", "age_group_id")
    op.drop_table("competition_age_groups")
    op.drop_table("age_groups")
    op.drop_constraint("ck_users_sex", "users", type_="check")
    op.drop_column("users", "sex")
