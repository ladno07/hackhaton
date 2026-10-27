from alembic import context
from app.db import Base, engine
from app import models
from sqlalchemy import inspect, text

if context.is_offline_mode():
    from app.config import settings

    context.configure(
        url=settings.database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        with connection.begin():
            tables = set(inspect(connection).get_table_names())
            # Bot databases used the same numeric revisions as main. Identify
            # that historical branch by its tables before resolving revisions.
            if "alembic_version" in tables and "telegram_links" in tables:
                for legacy, renamed in (
                    ("0007", "0007_telegram"),
                    ("0008", "0008_telegram"),
                    ("0009", "0009_telegram"),
                ):
                    if "athlete_organizations" not in tables and "competition_teams" not in tables:
                        connection.execute(
                            text("UPDATE alembic_version SET version_num = :renamed WHERE version_num = :legacy"),
                            {"legacy": legacy, "renamed": renamed},
                        )
            if (
                "alembic_version" in tables
                and "competition_teams" in tables
                and "athlete_organizations" not in tables
            ):
                connection.execute(
                    text(
                        "UPDATE alembic_version SET version_num = '0007_teams' WHERE version_num = '0007'"
                    )
                )
            if "alembic_version" in tables and "passport_publications" in tables:
                versions = set(
                    connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).scalars()
                )
                if versions == {"0008"}:
                    connection.execute(
                        text(
                            "UPDATE alembic_version SET version_num = '0008_passports' WHERE version_num = '0008'"
                        )
                    )
        context.configure(
            connection=connection, target_metadata=Base.metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()
