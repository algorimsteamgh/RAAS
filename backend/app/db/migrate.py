"""Schema migrations (Alembic). Entry point of the one-off `migrate` ECS task.

    python -m backend.app.db.migrate            # upgrade to the latest revision
    python -m backend.app.db.migrate current    # show the current revision
    python -m backend.app.db.migrate history
    python -m backend.app.db.migrate downgrade <revision>

Connection settings are the application's (DATABASE_* or DATABASE_URL).
"""
import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

logger = logging.getLogger("raas.migrate")


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return cfg


def upgrade(revision: str = "head") -> None:
    command.upgrade(alembic_config(), revision)


def main(argv: list) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    action = argv[0] if argv else "upgrade"
    cfg = alembic_config()
    if action == "upgrade":
        target = argv[1] if len(argv) > 1 else "head"
        logger.info("Upgrading database schema to %s", target)
        command.upgrade(cfg, target)
        command.current(cfg)
    elif action == "current":
        command.current(cfg, verbose=True)
    elif action == "history":
        command.history(cfg)
    elif action == "downgrade" and len(argv) > 1:
        command.downgrade(cfg, argv[1])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
