"""Read-only ministry of sport role."""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not bind.execute(sa.text("SELECT 1 FROM roles WHERE id = 'ministry'")).first():
        bind.execute(sa.text("INSERT INTO roles (id, name) VALUES ('ministry', 'Минспорт')"))


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM user_roles WHERE role_id = 'ministry'"))
    bind.execute(sa.text("DELETE FROM roles WHERE id = 'ministry'"))
