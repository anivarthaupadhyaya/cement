# Cement Wholesaler Management System

A locally hosted, offline-first system for a cement wholesaler. It replaces paper registers with brand-wise stock, GST billing, customer credit and daily cash closing, and takes nightly encrypted cloud backups.

**Stack:** FastAPI · PostgreSQL · SQLAlchemy 2 · Alembic · React + TypeScript · pytest + Hypothesis · Bash

> Work in progress.

## Development

```bash
cp .env.example .env
docker compose up -d db        # Postgres on localhost:5433
```

See `backend/README.md` and `frontend/README.md` for running each part.
