"""One-shot advisory-locked migrations; never run from API startup."""
from pathlib import Path

from alembic.config import Config
from sqlalchemy import text

from alembic import command
from database import engine


def main():
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    with engine.connect() as connection:
        postgres = engine.dialect.name == "postgresql"
        if postgres:
            connection.execute(text("SELECT pg_advisory_lock(7364202609)"))
            connection.commit()
        try:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            connection.commit()
        finally:
            if postgres:
                connection.rollback()
                connection.execute(text("SELECT pg_advisory_unlock(7364202609)"))
                connection.commit()


if __name__ == "__main__":
    main()
