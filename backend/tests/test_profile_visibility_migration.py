import importlib.util
from pathlib import Path
from datetime import date, datetime, timezone
from sqlalchemy import MetaData, create_engine, select, inspect
from alembic.operations import Operations
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from app.db import Base


def test_private_profile_migration_revokes_legacy_links_and_keeps_documents():
    previous = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(previous)
    flags = [
        "show_ranks",
        "show_disciplines",
        "show_organization",
        "show_municipality",
        "show_training_stage",
        "show_training_years",
    ]
    pub = previous.tables["passport_publications"]
    for name in flags:
        pub._columns.remove(pub.c[name])
    engine = create_engine("sqlite://")
    previous.create_all(engine)
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/0009_private_profiles.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0009", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as conn:
        conn.execute(
            previous.tables["users"]
            .insert()
            .values(
                id=1,
                email="test@example.com",
                password_hash="not-a-real-password",
                full_name="Тестовый спортсмен",
                birth_date=date(1990, 1, 1),
            )
        )
        conn.execute(previous.tables["athletes"].insert().values(id=1, user_id=1))
        conn.execute(
            pub.insert().values(
                athlete_id=1,
                enabled=True,
                slug="p-" + "x" * 32,
                updated_at=datetime.now(timezone.utc),
            )
        )
        module.op = Operations(MigrationContext.configure(conn))
        module.upgrade()
        row = (
            conn.execute(select(Base.metadata.tables["passport_publications"]))
            .mappings()
            .one()
        )
        assert (
            not row["enabled"]
            and row["slug"] is None
            and row["show_ranks"]
            and not row["show_training_years"]
        )
        assert not compare_metadata(MigrationContext.configure(conn), Base.metadata)
        module.downgrade()
        row = conn.execute(select(pub)).mappings().one()
        assert not row["enabled"] and row["slug"] is None
        assert not compare_metadata(MigrationContext.configure(conn), previous)
    engine.dispose()
