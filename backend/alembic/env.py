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
        context.configure(
            connection=connection, target_metadata=Base.metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()
