import importlib.util
from pathlib import Path
from sqlalchemy import MetaData, create_engine, inspect, text
from alembic.operations import Operations
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from app.db import Base


def test_training_migration_preserves_organization():
    previous = MetaData()
    added = {"training_groups", "group_enrollments", "training_lessons", "lesson_attendance", "training_materials"}
    for table in Base.metadata.tables.values():
        if table.name not in added:
            table.to_metadata(previous)
    for name in ("license_number", "license_valid_until", "programs"):
        previous.tables["organizations"]._columns.remove(previous.tables["organizations"].c[name])
    engine = create_engine("sqlite://")
    previous.create_all(engine)
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0020_training_groups.py"
    spec = importlib.util.spec_from_file_location("migration_0020", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    schedule_path = path.with_name("0021_training_schedule.py")
    schedule_spec = importlib.util.spec_from_file_location("migration_0021", schedule_path)
    schedule = importlib.util.module_from_spec(schedule_spec)
    schedule_spec.loader.exec_module(schedule)
    materials_spec = importlib.util.spec_from_file_location("migration_0022", path.with_name("0022_training_materials.py"))
    materials = importlib.util.module_from_spec(materials_spec)
    materials_spec.loader.exec_module(materials)
    at_0021 = MetaData()
    for table in Base.metadata.tables.values():
        if table.name != "training_materials":
            table.to_metadata(at_0021)
    at_0021.tables["training_lessons"]._columns.remove(at_0021.tables["training_lessons"].c.due_on)
    at_0020 = MetaData()
    for table in at_0021.tables.values():
        table.to_metadata(at_0020)
    for name in ("start_time", "timezone", "format", "location", "meeting_url", "instructions", "status", "cancellation_reason", "revision"):
        at_0020.tables["training_lessons"]._columns.remove(at_0020.tables["training_lessons"].c[name])
    at_0020.tables["lesson_attendance"]._columns.remove(at_0020.tables["lesson_attendance"].c.dispute_reason)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO organizations (id,name,kind,municipality) VALUES (1,'Test','Club','Test')"))
        module.op = Operations(MigrationContext.configure(conn))
        module.upgrade()
        assert conn.execute(text("SELECT programs FROM organizations WHERE id=1")).scalar_one() == "[]"
        assert not compare_metadata(MigrationContext.configure(conn), at_0020)
        schedule.op = Operations(MigrationContext.configure(conn))
        conn.execute(text("INSERT INTO users (id,email,password_hash,full_name,birth_date,consent_at,consent_version,created_at) VALUES (987,'history@example.test','hash','Historical coach','2000-01-01',CURRENT_TIMESTAMP,'test',CURRENT_TIMESTAMP)"))
        conn.execute(text("INSERT INTO coaches (id,user_id,organization_id,municipality) VALUES (987,987,1,'Test')"))
        conn.execute(text("INSERT INTO disciplines (id,name,short_name) VALUES (987,'History','History')"))
        conn.execute(text("INSERT INTO training_groups (id,organization_id,discipline_id,coach_id,name,stage,program,capacity,archived) VALUES (987,1,987,987,'Historical group','np','Historical program',20,false)"))
        conn.execute(text("INSERT INTO training_lessons (id,group_id,held_on,topic,duration_minutes,created_by) VALUES (987,987,'2026-01-01','Historical lesson',60,987)"))
        schedule.upgrade()
        assert not compare_metadata(MigrationContext.configure(conn), at_0021)
        materials.op = Operations(MigrationContext.configure(conn))
        materials.upgrade()
        assert not compare_metadata(MigrationContext.configure(conn), Base.metadata)
        historical = conn.execute(text("SELECT topic,status,start_time FROM training_lessons WHERE id=987")).one()
        assert tuple(historical) == ("Historical lesson", "completed", None)
        materials.downgrade()
        assert not compare_metadata(MigrationContext.configure(conn), at_0021)
        schedule.downgrade()
        assert not compare_metadata(MigrationContext.configure(conn), at_0020)
        module.downgrade()
        assert "training_groups" not in inspect(conn).get_table_names()
        assert conn.execute(text("SELECT name FROM organizations WHERE id=1")).scalar_one() == "Test"
        assert not compare_metadata(MigrationContext.configure(conn), previous)
        module.upgrade()
        schedule.upgrade()
        materials.upgrade()
        assert not compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
