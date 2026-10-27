"""Remember admission time so reminders never predate an accepted application."""
from alembic import op
import sqlalchemy as sa

revision = "0009_telegram"
down_revision = "0008_telegram"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("competition_applications", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    applications = sa.table("competition_applications", sa.column("id", sa.Integer),
                            sa.column("status", sa.String), sa.column("created_at", sa.DateTime(timezone=True)),
                            sa.column("approved_at", sa.DateTime(timezone=True)))
    logs = sa.table("audit_logs", sa.column("entity", sa.String), sa.column("entity_id", sa.String),
                    sa.column("details", sa.JSON), sa.column("created_at", sa.DateTime(timezone=True)))
    approval = sa.select(sa.func.min(logs.c.created_at)).where(
        logs.c.entity == "competition_applications",
        logs.c.entity_id == sa.cast(applications.c.id, sa.String),
        logs.c.details["status"].as_string() == "approved").scalar_subquery()
    op.execute(applications.update().where(applications.c.status == "approved").values(
        approved_at=sa.func.coalesce(approval, applications.c.created_at)))


def downgrade():
    op.drop_column("competition_applications", "approved_at")
