import importlib.util
from pathlib import Path
from sqlalchemy import MetaData, create_engine, inspect
from alembic.operations import Operations
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from app.db import Base


def test_login_session_upgrade_downgrade():
    previous = MetaData()
    for table in Base.metadata.tables.values():
        if table.name != "login_sessions":
            table.to_metadata(previous)
    engine = create_engine("sqlite://")
    previous.create_all(engine)
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0010_login_sessions.py"
    spec = importlib.util.spec_from_file_location("migration_0010", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as conn:
        module.op = Operations(MigrationContext.configure(conn))
        module.upgrade()
        assert "login_sessions" in inspect(conn).get_table_names()
        assert not compare_metadata(MigrationContext.configure(conn), Base.metadata)
        module.downgrade()
        assert "login_sessions" not in inspect(conn).get_table_names()
        assert not compare_metadata(MigrationContext.configure(conn), previous)
    engine.dispose()
