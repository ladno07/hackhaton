import importlib.util
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


def test_approval_migration_preserves_existing_applications():
    path = Path(__file__).parents[1] / "alembic/versions/0009_application_approval_time.py"
    spec = importlib.util.spec_from_file_location("approval_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE competition_applications (id INTEGER PRIMARY KEY, status TEXT, created_at DATETIME)"))
        connection.execute(text("CREATE TABLE audit_logs (entity TEXT, entity_id TEXT, details JSON, created_at DATETIME)"))
        connection.execute(text("INSERT INTO competition_applications VALUES (1, 'approved', '2026-10-01 10:00:00'), (2, 'approved', '2026-10-02 10:00:00'), (3, 'pending', '2026-10-03 10:00:00')"))
        connection.execute(text("INSERT INTO audit_logs VALUES ('competition_applications', '1', :details, '2026-10-04 12:00:00')"), {"details": '{"status":"approved"}'})
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            rows = connection.execute(text("SELECT id, approved_at FROM competition_applications ORDER BY id")).all()
            assert rows[0][1].startswith("2026-10-04")
            assert rows[1][1].startswith("2026-10-02")
            assert rows[2][1] is None
            migration.downgrade()
            assert connection.scalar(text("SELECT count(*) FROM competition_applications")) == 3
    engine.dispose()
