from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import get_settings
from app.db import models  # noqa: F401  (registers models on Base.metadata)
from app.db.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Czytamy DATABASE_URL z ustawień aplikacji (.env), nie ze statycznego
# alembic.ini - migracje muszą działać z tym samym adresem bazy co sama
# aplikacja (SQLite lokalnie, PostgreSQL przez zmianę DATABASE_URL).
config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # SQLite nie obsługuje większości ALTER TABLE wprost (np. dodania kolumny z
        # ograniczeniami, zmiany typu) - tryb "batch" odtwarza tabelę w tle zamiast
        # tego. Na PostgreSQL batch mode jest zbędny (ALTER działa natywnie), ale
        # nieszkodliwy - włączamy go tylko dla SQLite, żeby migracje na Postgresie
        # pozostały idiomatyczne.
        render_as_batch = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=render_as_batch,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
