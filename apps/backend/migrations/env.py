from logging.config import fileConfig
from typing import cast

from alembic import context
from alembic.util import CommandError
from sqlalchemy import Connection, text

from idea_board.database import create_database_engine
from idea_board.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

MIGRATION_LOCK_ID = 611338


def run_with_connection(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID}
        )
        context.run_migrations()


def run_migrations() -> None:
    if context.is_offline_mode():
        raise CommandError("SQL generation is not supported. Run 'alembic upgrade head'.")

    provided_connection = config.attributes.get("connection")
    if provided_connection is not None:
        run_with_connection(cast(Connection, provided_connection))
        return

    engine = create_database_engine()
    try:
        with engine.connect() as connection:
            run_with_connection(connection)
    finally:
        engine.dispose()


run_migrations()
