"""
Alembic environment configuration.

Design decision: DATABASE_URL is read from app.core.config.settings (which
itself reads the environment) rather than being hardcoded in alembic.ini —
so `alembic upgrade head` targets whatever database the app itself is
configured to use, in every environment, with a single source of truth.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models

# Import Base + every model module so target_metadata reflects the FULL
# schema — see app/models/__init__.py's docstring for why every model is
# imported there.
from app.core.config import settings
from app.core.database import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL scripts without a live DB connection (`alembic upgrade head --sql`)."""
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
    """Run migrations against a live DB connection — the normal `alembic upgrade head` path."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
