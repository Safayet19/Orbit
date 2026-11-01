from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import EXPECTED_DATABASE, get_database_url


def create_database_engine() -> Engine:
    return create_engine(
        get_database_url(),
        pool_pre_ping=True,
        hide_parameters=True,
    )


def verify_database(engine: Engine) -> None:
    with engine.connect() as connection:
        database_name = connection.scalar(text("SELECT current_database()"))
    if database_name != EXPECTED_DATABASE:
        raise RuntimeError("Connected database does not match orbit_db.")


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
