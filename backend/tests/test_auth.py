import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import AuditLog, Role
from tests.conftest import PASSWORD


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_login_rejects_wrong_password(client, make_user):
    make_user("ravi")
    r = client.post("/api/auth/login", json={"username": "ravi", "password": "nope"})
    assert r.status_code == 401


def test_login_sets_httponly_cookie_and_me_works(client, make_user):
    make_user("ravi")
    r = client.post("/api/auth/login", json={"username": "ravi", "password": PASSWORD})
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").json()["username"] == "ravi"


def test_logout_invalidates_session(client, login):
    login()
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_requires_login(client):
    assert client.get("/api/auth/me").status_code == 401


def test_non_owner_cannot_manage_users(client, login):
    login("clerk", Role.BILLING)
    assert client.get("/api/users").status_code == 403


def test_owner_creates_user_and_duplicate_is_rejected(client, login):
    login()
    body = {
        "username": "clerk1",
        "full_name": "Clerk",
        "password": "longpassword",
        "role": "billing",
    }
    assert client.post("/api/users", json=body).status_code == 201
    assert client.post("/api/users", json=body).status_code == 409


def test_disabling_user_kills_their_sessions(client, login, make_user, db: Session):
    clerk = make_user("clerk", Role.BILLING)
    login()
    r = client.patch(f"/api/users/{clerk.id}", json={"is_active": False})
    assert r.status_code == 200
    r = client.post("/api/auth/login", json={"username": "clerk", "password": PASSWORD})
    assert r.status_code == 401


def test_owner_cannot_demote_self(client, login):
    owner = login()
    r = client.patch(f"/api/users/{owner.id}", json={"role": "billing"})
    assert r.status_code == 400


def test_audit_records_acting_user_and_hides_password(client, login, db: Session):
    owner = login()
    body = {
        "username": "acc",
        "full_name": "Accountant",
        "password": "longpassword",
        "role": "accountant",
    }
    new_id = client.post("/api/users", json=body).json()["id"]

    entry = db.scalars(
        select(AuditLog).where(AuditLog.table_name == "users", AuditLog.record_id == str(new_id))
    ).one()
    assert entry.action == "INSERT"
    assert entry.user_id == owner.id
    assert entry.new_data is not None and "password_hash" not in entry.new_data

    listed = client.get("/api/audit", params={"table": "users"}).json()
    assert any(e["record_id"] == str(new_id) for e in listed)


def test_audit_log_is_append_only(db: Session, make_user):
    make_user("someone")
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM audit_log"))
