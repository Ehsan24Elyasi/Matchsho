import os
import sys
import tempfile
from pathlib import Path

import pytest

_db_file = Path(tempfile.gettempdir()) / f"matchsho-pytest-{os.getpid()}.sqlite3"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file.as_posix()}"
os.environ["ENVIRONMENT"] = "test"
os.environ["AUTO_CREATE_DB"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-with-more-than-thirty-two-characters"
os.environ["ALLOWED_HOSTS"] = "testserver,localhost"
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_PASSWORD"] = "Admin-Password-For-Tests-123"

from database import Base, engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def isolated_database():
    Base.metadata.drop_all(bind=engine)
    yield
    engine.dispose()
    _db_file.unlink(missing_ok=True)
