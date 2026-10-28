"""Historical organization/team/passport/ministry schemas reach the same head."""

import os
from pathlib import Path
import subprocess
import sys
import pytest
from datetime import date
from sqlalchemy import MetaData, create_engine, inspect, text
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.db import Base


@pytest.mark.parametrize(
    "source", ["0006", "0007", "0007_teams", "0008", "0008_passports", "0010", "0011", "0014", "0007_telegram", "0008_telegram", "0009_telegram", "0020", "0021", "0020_training", "0021_training", "0022"]
)
def test_merged_migration_upgrade(tmp_path, source):
    url = "sqlite:///" + (tmp_path / "migration.db").as_posix()
    env = {**os.environ, "DATABASE_URL": url}
    cwd = Path(__file__).resolve().parents[1]

    def upgrade(revision):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", revision],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    # Historical revisions 0003/0005 use PostgreSQL-only constraint DDL.
    # Reconstruct their completed 0006 schema to test the merged branches on SQLite.
    previous = MetaData()
    added = {
        "training_groups", "group_enrollments", "training_lessons", "lesson_attendance", "training_materials",
        "coach_chat_messages",
        "violations",
        "appeals",
        "training_standards",
        "standard_results",
        "stage_transfers",
        "athlete_organizations",
        "competition_teams",
        "competition_team_members",
        "passport_publications",
        "passport_guardian_consents",
        "public_protocol_proofs",
        "login_sessions",
        "development_indicators",
        "indicator_documents",
        "governor_award_rules",
        "governor_awards",
        "telegram_links",
        "telegram_link_tokens",
        "telegram_deliveries",
        "telegram_cursor",
        "telegram_code_attempts",
        "api_tokens",
        "webhooks",
        "webhook_deliveries",
        "athlete_platform_logins",
    }
    for name, table in Base.metadata.tables.items():
        if name not in added:
            table.to_metadata(previous)
    comp = previous.tables["competitions"]
    for constraint in list(comp.constraints):
        if constraint.name in {"ck_comp_entry_mode", "ck_comp_team_size"}:
            comp.constraints.remove(constraint)
    for name in ["entry_mode", "team_min", "team_max", "team_rating", "start_time", "timezone", "results_source"]:
        comp._columns.remove(comp.c[name])
    previous.tables["notifications"]._columns.remove(previous.tables["notifications"].c.telegram_context)
    previous.tables["competition_applications"]._columns.remove(previous.tables["competition_applications"].c.approved_at)
    for name in ("license_number", "license_valid_until", "programs"):
        previous.tables["organizations"]._columns.remove(previous.tables["organizations"].c[name])
    engine = create_engine(url)
    previous.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        )
        conn.execute(text("INSERT INTO alembic_version VALUES ('0006')"))
        conn.execute(
            previous.tables["organizations"]
            .insert()
            .values(id=1, name="Migration sentinel", kind="club", municipality="Test")
        )
        conn.execute(
            previous.tables["users"]
            .insert()
            .values(
                id=1,
                email="migration@example.com",
                full_name="Migration test",
                password_hash="hash",
                birth_date=date(2000, 1, 1),
            )
        )
        conn.execute(
            previous.tables["athletes"]
            .insert()
            .values(id=1, user_id=1, organization_id=1)
        )
        conn.execute(
            previous.tables["disciplines"]
            .insert()
            .values(id=1, name="Test", short_name="Test")
        )
        conn.execute(
            previous.tables["athlete_disciplines"]
            .insert()
            .values(athlete_id=1, discipline_id=1, start_year=2022)
        )
    engine.dispose()
    if source != "0006":
        upgrade(source)
    if source in {"0007_teams", "0008_passports"}:
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE alembic_version SET version_num = :legacy"),
                {"legacy": "0007" if source == "0007_teams" else "0008"},
            )
        engine.dispose()
    if source.endswith("_telegram"):
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE alembic_version SET version_num = :legacy"),
                {"legacy": source.split("_")[0]},
            )
        engine.dispose()
    if source in {"0020_training", "0021_training"}:
        # Standalone D3 used numeric IDs before joining the platform-import branch.
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = :legacy"), {"legacy": source.split("_")[0]})
        engine.dispose()
    upgrade("head")
    engine = create_engine(url)
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars().all() == ["0023"]
        tables = set(inspect(conn).get_table_names())
        assert {
            "athlete_organizations",
            "competition_teams",
            "passport_publications",
            "login_sessions",
            "development_indicators",
            "indicator_documents",
            "governor_award_rules",
            "governor_awards",
        } <= tables
        assert not compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert (
            conn.execute(text("SELECT name FROM organizations WHERE id=1")).scalar_one()
            == "Migration sentinel"
        )
        assert (
            str(
                conn.execute(
                    text(
                        "SELECT start_date FROM athlete_organizations WHERE athlete_id=1"
                    )
                ).scalar_one()
            )
            == "2022-01-01"
        )
    engine.dispose()
