"""Alembic environment: connects with the application's own connection
settings (DATABASE_* or DATABASE_URL, Secrets Manager rotation) and holds a
PostgreSQL advisory lock so two tasks never migrate at the same time."""
from alembic import context
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from backend.app.db import database

MIGRATION_LOCK_ID = 7_301_201_901  # arbitrary constant shared by every migrator


def run_migrations_online() -> None:
    engine = create_engine("postgresql+psycopg://", creator=database.raw_connect, poolclass=NullPool)
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:id)"), {"id": MIGRATION_LOCK_ID})
        connection.commit()
        try:
            context.configure(connection=connection, target_metadata=None, transaction_per_migration=True)
            with context.begin_transaction():
                context.run_migrations()
            connection.commit()
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": MIGRATION_LOCK_ID})
            connection.commit()


if context.is_offline_mode():
    context.configure(url="postgresql+psycopg://", literal_binds=True, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()
else:
    run_migrations_online()
