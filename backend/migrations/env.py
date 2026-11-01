from alembic import context
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from backend.app.core.config import EXPECTED_DATABASE, get_database_url
from backend.app.db.models import Base

target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = create_engine(
        get_database_url(),
        poolclass=NullPool,
        hide_parameters=True,
    )
    try:
        with engine.connect() as connection:
            database_name = connection.scalar(text("SELECT current_database()"))
            if database_name != EXPECTED_DATABASE:
                raise RuntimeError("Migration target does not match orbit_db.")
            connection.commit()
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline migrations are disabled for credential safety.")
run_migrations_online()
