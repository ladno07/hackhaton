"""Run explicitly against disposable databases; never migrate the application DB."""
import os
from pathlib import Path
import subprocess
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.db import Base
import app.models  # register metadata


def main():
    original = make_url(os.environ["DATABASE_URL"])
    migration_url = original.set(database="orencode_d3_migration_test")
    migration_env = {**os.environ, "DATABASE_URL": migration_url.render_as_string(hide_password=False), "NOTIFICATIONS_WORKER": "false"}
    cwd = Path(__file__).resolve().parents[1]

    def migrate(revision, downgrade=False):
        action = "downgrade" if downgrade else "upgrade"
        subprocess.run([sys.executable, "-m", "alembic", action, revision], cwd=cwd, env=migration_env, check=True)

    migrate("base", True)
    migrate("0019")
    engine = create_engine(migration_url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO organizations (id,name,kind,municipality) VALUES (987654,'D3 migration sentinel','Club','Test')"))
    migrate("head")
    with engine.connect() as db:
        assert not compare_metadata(MigrationContext.configure(db), Base.metadata)
        assert db.execute(text("SELECT programs FROM organizations WHERE id=987654")).scalar_one() == []
    migrate("0019", True)
    migrate("head")
    with engine.connect() as db:
        assert not compare_metadata(MigrationContext.configure(db), Base.metadata)
        assert db.execute(text("SELECT name FROM organizations WHERE id=987654")).scalar_one() == "D3 migration sentinel"
    engine.dispose()
    test_env = {**os.environ, "TEST_DATABASE_URL": original.set(database="orencode_test").render_as_string(hide_password=False), "NOTIFICATIONS_WORKER": "false"}
    subprocess.run([sys.executable, "-m", "pytest", "tests/test_training.py", "tests/test_training_schedule.py", "tests/test_training_materials.py", "tests/test_training_demo.py", "tests/test_memberships.py", "-q", "-p", "no:cacheprovider"], cwd=cwd, env=test_env, check=True)


if __name__ == "__main__":
    main()
