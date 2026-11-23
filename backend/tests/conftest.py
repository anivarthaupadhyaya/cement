import os
from collections.abc import Callable, Iterator

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://cement:cement@localhost:5433/cement_test"
)
os.environ["DATABASE_URL"] = TEST_DB  # must happen before the app is imported

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.db import engine, get_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402

PASSWORD = "secret-pass-123"


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    """Fresh schema per test run, built by the real migrations (so they get tested too)."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = TEST_DB
    command.upgrade(cfg, "head")


@pytest.fixture
def db() -> Iterator[Session]:
    """Each test runs inside a transaction that is rolled back afterwards."""
    conn = engine.connect()
    outer = conn.begin()
    session = Session(
        bind=conn, join_transaction_mode="create_savepoint", autoflush=False, expire_on_commit=False
    )
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        conn.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db: Session) -> Callable[..., User]:
    def _make(username: str = "owner", role: Role = Role.OWNER) -> User:
        user = User(
            username=username,
            full_name=username.title(),
            password_hash=hash_password(PASSWORD),
            role=role.value,
        )
        db.add(user)
        db.commit()
        return user

    return _make


@pytest.fixture
def login(client: TestClient, make_user: Callable[..., User]) -> Callable[..., User]:
    def _login(username: str = "owner", role: Role = Role.OWNER) -> User:
        user = make_user(username, role)
        r = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return user

    return _login
