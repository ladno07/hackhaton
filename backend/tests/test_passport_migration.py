import importlib.util
from pathlib import Path
from sqlalchemy import MetaData, create_engine, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.autogenerate import compare_metadata
from app.db import Base


def test_passport_migration_upgrade_defaults_schema_and_downgrade():
    previous = MetaData()
    added = {
        "passport_publications",
        "passport_guardian_consents",
        "public_protocol_proofs",
    }
    for name, table in Base.metadata.tables.items():
        if name not in added:
            table.to_metadata(previous)
    engine = create_engine("sqlite://")
    previous.create_all(engine)
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/0008_digital_passports.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0008", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as conn:
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        assert added <= set(inspect(conn).get_table_names())
        expected = MetaData()
        for table in Base.metadata.tables.values():
            table.to_metadata(expected)
        for name in [
            "show_ranks",
            "show_disciplines",
            "show_organization",
            "show_municipality",
            "show_training_stage",
            "show_training_years",
        ]:
            expected.tables["passport_publications"]._columns.remove(
                expected.tables["passport_publications"].c[name]
            )
        assert not compare_metadata(MigrationContext.configure(conn), expected)
        defaults = {
            c["name"]: c["default"]
            for c in inspect(conn).get_columns("passport_publications")
        }
        assert defaults["enabled"] in {"0", "false", "FALSE"}
        migration.downgrade()
        assert not added & set(inspect(conn).get_table_names())
        assert not compare_metadata(MigrationContext.configure(conn), previous)
    engine.dispose()
