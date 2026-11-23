# Backend

FastAPI + SQLAlchemy 2 + Alembic on PostgreSQL.

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate     # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"

docker compose up -d db                            # from repo root
alembic upgrade head
python -m app.cli create-owner owner "Shop Owner"  # first login
uvicorn app.main:app --reload                      # http://localhost:8000/docs
```

## Checks

```bash
ruff check . && ruff format --check .
mypy app
pytest                                            # uses the cement_test database
```

## Design notes

- **Money:** `NUMERIC` columns and Python `Decimal` only, never floats.
- **Audit log:** a Postgres trigger (`app/core/audit.py`) records every insert/update/delete on audited tables with the acting user, taken from the transaction-local `app.user_id`. The table is append-only: updates and deletes raise an error.
- **Sessions:** a random token in an httpOnly cookie. Only its SHA-256 hash is stored, and sessions are revoked when a user is disabled or their password changes.
