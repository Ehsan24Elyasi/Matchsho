"""Independent-connection PostgreSQL race harness used by transactional regression tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker


def race(session_factory: sessionmaker, *actions: Callable[[Session], object]) -> list[object]:
    """Begin each contender on a distinct checked-out PG connection before release.

    Each action owns its transaction. Return exceptions to permit explicit assertions on
    the expected conflict; an unexpected error must fail the caller's assertions.
    """
    if len(actions) < 2:
        raise ValueError("A race requires at least two independent contenders")
    barrier = Barrier(len(actions), timeout=15)

    def contender(action: Callable[[Session], object]) -> object:
        with session_factory() as session:
            if session.bind.dialect.name != "postgresql":
                raise RuntimeError("SQLite is not evidence of PostgreSQL locking correctness")
            session.connection()  # Check out a separate real connection before overlap.
            barrier.wait()
            try:
                result = action(session)
                session.commit()
                return result
            except Exception as error:
                session.rollback()
                return error

    with ThreadPoolExecutor(max_workers=len(actions)) as executor:
        futures = [executor.submit(contender, action) for action in actions]
        return [future.result(timeout=60) for future in futures]
