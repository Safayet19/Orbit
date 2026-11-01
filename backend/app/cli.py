import argparse
import getpass
import logging
import sys

from alembic import command
from alembic.config import Config
from pwdlib import PasswordHash

from backend.app.agents.orchestrator import CollectionOrchestrator
from backend.app.collectors.worldbank import WorldBankInflationCollector
from backend.app.core.config import PROJECT_ROOT
from backend.app.core.logging import configure_logging
from backend.app.db.session import (
    create_database_engine,
    create_session_factory,
    verify_database,
)
from backend.app.schemas.records import WORLD_BANK_SOURCE_ID

LOGGER = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orbit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="Run a registered source collector.")
    collect.add_argument("--source", required=True)
    subparsers.add_parser("migrate", help="Apply pending database migrations.")
    subparsers.add_parser(
        "hash-password",
        help="Create an Argon2id password hash for ADMIN_PASSWORD_HASH.",
    )
    return parser


def _run_migrations() -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(PROJECT_ROOT / "backend" / "migrations"),
    )
    command.upgrade(config, "head")


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = _parser().parse_args(argv)
    engine = None

    try:
        if args.command == "migrate":
            _run_migrations()
            print("Migrations applied successfully.")
            return 0
        if args.command == "hash-password":
            first = getpass.getpass("Administrator password: ")
            second = getpass.getpass("Confirm password: ")
            if not first or first != second:
                print("Password is empty or confirmation did not match.")
                return 1
            print(PasswordHash.recommended().hash(first))
            return 0

        if args.source != WORLD_BANK_SOURCE_ID:
            raise ValueError("Source is not registered.")

        engine = create_database_engine()
        verify_database(engine)
        orchestrator = CollectionOrchestrator(create_session_factory(engine))
        summary = orchestrator.run(
            args.source,
            WorldBankInflationCollector(),
        )
        print(
            f"Collection {summary.status}: source={summary.source_id} "
            f"fetched={summary.records_fetched} new={summary.records_new} "
            f"changed={summary.records_changed} "
            f"unchanged={summary.records_unchanged} "
            f"invalid={summary.records_invalid} "
            f"duration={summary.duration_seconds:.2f}s"
        )
        return 0
    except Exception as error:
        LOGGER.error("command_failed command=%s error_type=%s", args.command, type(error).__name__)
        print(f"Execution failed ({type(error).__name__}); details suppressed.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
