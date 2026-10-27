"""Read-only ministry of sport role."""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            "INSERT INTO roles (id, name) SELECT 'ministry', 'Минспорт' WHERE NOT EXISTS (SELECT 1 FROM roles WHERE id = 'ministry')"
        )
    )


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM user_roles WHERE role_id = 'ministry'"))
    bind.execute(sa.text("DELETE FROM roles WHERE id = 'ministry'"))
