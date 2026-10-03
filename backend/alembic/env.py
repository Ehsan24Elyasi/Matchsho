from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models  # noqa: F401,E402
import pilot.domain_models  # noqa: F401,E402
import pilot.security_models  # noqa: F401,E402
from database import Base, engine  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if config.attributes.get("connection") is not None:
        context.configure(connection=config.attributes["connection"], target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
