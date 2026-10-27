"""Migration 0007 preserves existing competitions and has a working downgrade."""

import importlib.util
from pathlib import Path
from datetime import date
from sqlalchemy import MetaData, create_engine, inspect, select
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.autogenerate import compare_metadata
from app.db import Base


def test_team_migration_preserves_existing_competition():
    previous = MetaData()
    for name, table in Base.metadata.tables.items():
        if name not in {"competition_teams", "competition_team_members"}:
            table.to_metadata(previous)
    comp = previous.tables["competitions"]
    for constraint in list(comp.constraints):
        if constraint.name in {"ck_comp_entry_mode", "ck_comp_team_size"}:
            comp.constraints.remove(constraint)
    for name in ["entry_mode", "team_min", "team_max", "team_rating"]:
        comp._columns.remove(comp.c[name])
    engine = create_engine("sqlite://")
    previous.create_all(engine)
    module_path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/0007_competition_teams.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0007", module_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as conn:
        conn.execute(
            previous.tables["disciplines"]
            .insert()
            .values(id=1, name="Алгоритмы", short_name="Алгоритмы")
        )
        conn.execute(
            previous.tables["competition_types"]
            .insert()
            .values(id=1, name="Турнир", rating_class="other")
        )
        conn.execute(
            comp.insert().values(
                id=1,
                title="Существующее соревнование",
                discipline_id=1,
                type_id=1,
                start_date=date.today(),
                end_date=date.today(),
                deadline=date.today(),
                location="Оренбург",
                format="onsite",
                status="regional",
                rating_level="regional",
                calendar_plan="Оренбургская область",
                calendar_number="1",
                state="published",
            )
        )
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        row = (
            conn.execute(select(Base.metadata.tables["competitions"])).mappings().one()
        )
        assert (
            row["title"] == "Существующее соревнование" and row["state"] == "published"
        )
        assert row["entry_mode"] == "individual" and not row["team_rating"]
        assert not compare_metadata(MigrationContext.configure(conn), Base.metadata)
        migration.downgrade()
        assert "competition_teams" not in inspect(conn).get_table_names()
        assert "entry_mode" not in {
            c["name"] for c in inspect(conn).get_columns("competitions")
        }
        assert (
            conn.execute(select(comp.c.title)).scalar_one()
            == "Существующее соревнование"
        )
    engine.dispose()
