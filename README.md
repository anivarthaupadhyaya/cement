# Cement Wholesaler Management System

A locally hosted, offline-first system for a cement wholesaler. It replaces handwritten registers with:

- **brand-wise stock** across godowns, with the real cost per bag,
- **purchase entry** from supplier bills (freight, unloading, damaged and short bags),
- **GST billing** with printed tax invoices and delivery challans,
- **customer credit**: payments, cheques, statements and an ageing (outstanding) report,
- **daily cash closing** and expenses,
- a full **audit trail** of who changed what.

It runs on one PC in the shop and is used from any browser on the shop's network. It needs no internet connection.

> **Status:** Milestones 1–5 are complete, and Milestone 6 is partly done (see [Project status](#project-status)).
> **Milestone 7 (automated cloud backups, Windows installer, remote access) is dropped for now** because of technical issues, and because almost all of it has to be installed and configured on the shop owner's own computer. [Running it at the shop](#running-it-at-the-shop-manual-setup) describes the manual setup that replaces it.

---

## Contents

1. [Project status](#project-status)
2. [Using the system (for the shop)](#using-the-system-for-the-shop)
3. [Running it on your machine (for developers)](#running-it-on-your-machine-for-developers)
4. [Running it at the shop (manual setup)](#running-it-at-the-shop-manual-setup)
5. [Tech stack: what, how and why](#tech-stack-what-how-and-why)
6. [Architecture and design decisions](#architecture-and-design-decisions)
7. [Project structure](#project-structure)
8. [Data model](#data-model)
9. [Testing and CI](#testing-and-ci)
10. [Configuration reference](#configuration-reference)
11. [API overview](#api-overview)
12. [Troubleshooting](#troubleshooting)

---

## Project status

| # | Milestone | Status |
|---|---|---|
| 1 | Foundation: repo, database, migrations, CI, login and roles, audit log | ✅ Done |
| 2 | Masters: brands, products, customers/suppliers (GSTIN check), godowns, GST rates, daily rate card | ✅ Done |
| 3 | Purchases and stock: supplier bills, landed cost, damaged/short bags, live stock, adjustments | ✅ Done |
| 4 | Sales billing: billing screen, GST invoice and challan print, credit limits, cancel, returns | ✅ Done |
| 5 | Receipts and credit: payments, matching against bills, cheques and bounces, statements, ageing | ✅ Done |
| 6 | Expenses, cash closing, dashboard, reports, Excel exports for the CA | 🟡 Partly done: expenses and daily cash closing work in the **backend** (API and tests). Their screens, the dashboard, reports and Excel exports are still to do. |
| 7 | Automated encrypted backups to Google Drive, Windows installer, Tailscale remote access | ⛔ **Dropped for now**: technical issues, and most of it must be installed and set up on the owner's system |

**Tests:** 116 automated backend tests, including property-based tests. They run on every push through GitHub Actions.

---

## Using the system (for the shop)

### Who can do what

There are four roles. Every rule is enforced by the server, so hiding a button is never the only protection.

| Action | Owner | Accountant | Billing clerk | Godown keeper |
|---|:-:|:-:|:-:|:-:|
| Make bills, take cash/UPI payments | ✅ | ✅ | ✅ | – |
| See cost price, margin, stock value | ✅ | ✅ | ❌ | ❌ |
| Sell below cost, back-date a bill, go over a credit limit | ✅ | ❌ | ❌ | ❌ |
| Give a customer credit (limit/days) | ✅ | ❌ | ❌ | – |
| Set today's rates | ✅ | ❌ | ❌ | ❌ |
| Enter purchases, stock damage/corrections | ✅ | ✅ | ❌ | ✅ |
| Cheques, bank receipts, old dues, sales returns | ✅ | ✅ | ❌ | ❌ |
| Cancel a bill, purchase or receipt | ✅ | ❌ | ❌ | ❌ |
| Manage users, view the audit log | ✅ | ❌ | ❌ | ❌ |

### First-time setup (do once, in this order)

1. **Create the owner login** (on the server PC, in the `backend` folder):
   `python -m app.cli create-owner owner "Owner Name"`. It asks for a password.
2. **Users** (sidebar → Users): add a login for each staff member, with the right role.
3. **Settings**: "Main Godown" and the cement GST rate already exist (28% until 21 Sep 2025, 18% from 22 Sep 2025). Add more godowns here if needed.
4. **Products**: add each brand (UltraTech, ACC, …), then each grade (OPC 53, PPC, PSC…), bag size and reorder level.
5. **Customers & suppliers**: add parties.
   - The GSTIN is checked as you type (including its check digit), and the state is filled in from it.
   - Only the owner can give credit limits.
6. **Today's rates**: enter the selling rate per bag, **including GST**. Press Enter to move down the list.
7. **Opening stock and old dues.** Bags already in the godown and money customers already owe on day one:
   - These have no screen yet. Enter them through the built-in API page at `http://<server>:8010/docs`:
     - `POST /api/stock/opening` for opening stock,
     - `POST /api/parties/{id}/opening-dues` for each old unpaid bill.
   - A bulk Excel import was planned for Milestone 7.

### Daily work

**Selling (+ New bill)**
1. Start typing the customer's name and press ↓ then Enter. Leave it empty for a walk-in cash sale.
2. Choose **Cash** or **Credit**. Credit is only allowed for a customer with a credit limit.
3. Pick a product. The rate fills in from today's rates, or the customer's special rate. Type the bags, press Enter, check the rate, and press Enter for the next line.
4. The right-hand panel updates live from the server: total, CGST/SGST (or IGST for other states), bags left in stock, and margin (owner and accountant only).
5. Warnings appear for low stock, selling below cost, going over the credit limit, and a customer whose cheques bounced before.
6. Press **Ctrl+Enter** or **F9** to save. Then print the **GST invoice** or **delivery challan** (the challan has no prices), and click **Next bill**.

Bills are **never edited**. To fix one, the owner **cancels** it with a reason (the bags go back into stock and the bill number stays on record as cancelled), and a new bill is made. Bags that come back are entered as a **return**, which creates a credit note (`CN/2026-27/0001`).

**Buying (Purchases → New purchase)**
1. Enter the supplier's bill exactly as printed: bill number, date, truck number, and the rate per bag **before GST**.
2. For each product, enter the bags billed, damaged and short. Only the good bags go into stock.
3. Enter the freight, unloading and other charges *you* paid.
4. Save. The system shows the **real cost per good bag**: the supplier rate plus your charges (split by weight), spread over the good bags only. Damaged and short bags are highlighted so you can claim them from the supplier.

**Taking payment (+ Receive payment)**
1. Pick the customer. Their unpaid bills appear, oldest first, with their age in days.
2. Enter the amount and the mode (Cash, UPI, Bank or Cheque).
3. By default the payment **pays the oldest bills first**. Tick "Split across bills myself" to choose instead.
4. Paying more than is due is kept as an **advance**, which automatically pays the customer's next bill.
5. Press Ctrl+Enter to save, then print the receipt.

**Cheques (sidebar → Cheques)**
- Every cheque starts as *Received*. Mark it **Deposited**, then **Cleared**.
- **Bounced** (on the receipt page) re-opens the bills it had paid and can add a bounce charge. After that, the billing screen warns whenever this customer is billed.

**Who owes what (sidebar → Outstanding)**
- Each customer's dues are split into 0–30, 31–60, 61–90 and 90+ days, with **overdue** (past their credit days) in red.
- You can filter by area to plan a collection route. **Collect** jumps straight to taking payment.
- Click a customer for their **statement**: every bill, payment and return with a running balance. You can print it, or press **Share on WhatsApp**, which opens WhatsApp with the balance and pending bills already typed.

**Stock (sidebar → Stock)**
- Live bags in each godown, with low-stock badges. The owner and accountant also see cost and value.
- Click a product to see every movement. Record burst/wet bags or count corrections, always with a reason.

**Audit log (owner)**
- Every change to important records is listed: who made it, when, and the old and new values. Nobody can edit or delete these entries.

**Forgot a password?** On the server PC, in the `backend` folder, run `python -m app.cli reset-password <username>`.

---

## Running it on your machine (for developers)

### Prerequisites

| Tool | Version | Used for |
|---|---|---|
| Python | 3.11+ | Backend |
| Node.js | 20+ (developed on 24) | Building and running the frontend |
| Docker Desktop | any recent | Runs PostgreSQL for development (no local Postgres install needed) |
| Git | any | Version control |

### Start everything

```powershell
# 1. Database (from the repo root)
cd C:\path\to\cement-erp
copy .env.example .env
docker compose up -d db              # Postgres 16 on localhost:5433 (dbs: cement, cement_test)

# 2. Backend (new terminal)
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head                 # create/upgrade all tables
python -m app.cli create-owner owner "Shop Owner"
python -m app.dev_seed               # optional: demo brands, rates, customers and a purchase
uvicorn app.main:app --reload --port 8010

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev                          # http://localhost:5173 (calls the API on :8010)
```

Then open **http://localhost:5173**. The interactive API docs are at **http://localhost:8010/docs**.

> Port **8010** is used because 8000 is often taken by other local projects. `frontend/vite.config.ts` points its `/api` proxy there.

### Everyday developer commands

```powershell
# Backend (in backend/, venv active)
pytest                                  # all tests (uses the cement_test database)
pytest tests/test_sales.py -k credit    # a subset
ruff check . ; ruff format .            # lint + format
mypy app                                # type check
alembic revision --autogenerate -m "describe change"   # new migration after editing models
alembic upgrade head ; alembic downgrade -1            # apply / undo one migration

# Frontend (in frontend/)
npm run lint
npm run build                           # type-checks (tsc) and builds into frontend/dist
```

---

## Running it at the shop (manual setup)

Milestone 7 was going to automate this with an installer, nightly encrypted backups to Google Drive and Tailscale remote access. Since that's dropped for now, these are the manual steps.

1. **On the shop PC**, install PostgreSQL 16 (official Windows installer) and Python 3.11. Create a database `cement` and a user for it.
2. Copy the project to the PC. Create `.env` from `.env.example`:
   - set `DATABASE_URL` to the local database,
   - set a long random `SECRET_KEY`,
   - fill in the real `SHOP_NAME`, `SHOP_ADDRESS`, `SHOP_GSTIN`, `SHOP_PHONE` and `SHOP_BANK`, which are printed on every invoice.
3. **Build the frontend once** on your laptop (`npm run build`) and copy `frontend/dist` to the same place on the shop PC. FastAPI serves it automatically, so the shop PC doesn't need Node.js.
4. In `backend`: `pip install .`, then `alembic upgrade head`, then `python -m app.cli create-owner …`.
5. Start the server so other PCs can reach it:
   `uvicorn app.main:app --host 0.0.0.0 --port 8010`
   Allow port 8010 through Windows Firewall when Windows asks.
6. On every other PC or phone on the shop Wi-Fi/LAN, open `http://<shop-PC-IP>:8010`. Find the IP with `ipconfig`.
7. **Backups (manual, important):** at the end of each day, run
   `pg_dump -Fc -U <user> cement > D:\backups\cement-YYYY-MM-DD.dump`
   and copy the file to a USB drive or Google Drive.
   - Restore with `pg_restore -d cement --clean <file>`.
   - Test a restore once, so you know it works before you need it.

---

## Tech stack: what, how and why

### Backend

| Tech | How it's used here | Why it and not something else |
|---|---|---|
| **Python 3.11** | The whole backend | Readable, and good for business rules and money maths (built-in `Decimal`). It's also what the developer knows best, so the client gets a maintainable system. |
| **FastAPI** | HTTP API (`app/api/*`), dependency injection for the DB session, current user and role checks | Type hints become validation and automatic docs at `/docs`. **vs Django:** Django's admin and ORM conventions add weight we don't need, and a React front end wants a plain JSON API. **vs Flask:** we'd have to add validation, docs and dependency injection by hand. |
| **Pydantic v2** | Request and response schemas (`app/schemas/*`), settings from `.env` (`pydantic-settings`) | Bad input is rejected before it reaches business logic (e.g. negative bags, wrong GSTIN, a rate with 3 decimal places), and the messages are readable. |
| **PostgreSQL 16** | The only data store | Real transactions, row locking (`SELECT … FOR UPDATE`), CHECK constraints, triggers, JSONB and partial unique indexes, all used below. **vs SQLite:** only one writer at a time for the whole database, no `SELECT … FOR UPDATE` row locks, and loose typing; a poor fit for several counters billing at once. **vs MySQL:** fewer of these features (no partial indexes; weaker CHECK history). |
| **SQLAlchemy 2.0** | ORM models (`app/models/*`), typed `Mapped[...]` columns, explicit transactions | The most mature Python ORM. It still lets us drop to SQL for locks, upserts (`ON CONFLICT`) and aggregates, which an accounting system needs. |
| **Alembic** | Database migrations (`backend/alembic/versions/0001…0006`) | Every schema change is a versioned script that can also be undone, so the shop's live database can be upgraded safely. Each migration is tested up → down → up. |
| **psycopg 3** | Postgres driver | The modern, maintained driver; binary wheels install cleanly on Windows. |
| **argon2-cffi** | Password hashing | Argon2 is the current recommended password hash (memory-hard), stronger than bcrypt or SHA. |
| **uvicorn** | ASGI server | The standard server for FastAPI; one process is plenty for one shop. |
| **openpyxl** | Excel exports for the CA (installed; used in the remaining part of Milestone 6) | Writes real `.xlsx` files with formatting, with no Excel installed. |

### Frontend

| Tech | How it's used here | Why |
|---|---|---|
| **React 19 + TypeScript** | All screens (`frontend/src/pages/*`) | Types catch mistakes such as treating a money string as a number. React is the most widely known UI library, which helps anyone who maintains this later. |
| **Vite** | Dev server with hot reload; production build into `frontend/dist` | Fast and simple. **vs Next.js:** we don't need server rendering or SEO; this is an internal app served by FastAPI. |
| **TanStack Query** | All server data (fetching, caching, refetching after saves) | No hand-written loading and error state, and screens stay in sync after each save. |
| **React Router** | Page routes and role-protected routes (`RequireAuth`) | The standard router. |
| **React Hook Form + Zod** | Login and user forms | Validation rules sit next to the form, with no re-render on every keystroke. |
| **Tailwind CSS v4** | All styling, including print styles (`print:hidden`, A4 `@page`) | Fast to build a clean, consistent UI. Print layouts for invoices are plain CSS, so they work with **any printer** and "Save as PDF" in the browser. |

### Tooling and quality

| Tech | Used for | Why |
|---|---|---|
| **pytest** | 116 backend tests against a real Postgres database | Tests run against the real database (constraints, triggers, locks), not a fake one. |
| **Hypothesis** | Property-based tests | It generates thousands of random cases to *prove* rules such as "the customer always pays exactly bags × rate", "stock never goes negative" and "the ledger always equals the unpaid bills". |
| **ruff** | Linting and formatting (Python) | One very fast tool replacing flake8, isort and black. |
| **mypy** | Static type checking (Python) | Catches wrong types (e.g. `int | None` passed where `int` is needed) before runtime. |
| **ESLint** | Linting (TypeScript) | Catches React hook mistakes and unused code. |
| **Docker Compose** | Postgres for development only | No local Postgres install; everyone gets the same version. Production doesn't need Docker. |
| **GitHub Actions** | CI on every push (`.github/workflows/ci.yml`) | Runs lint, type checks, all tests against a Postgres service, and the frontend build. Broken code can't slip in unnoticed. |

### Deliberately *not* used (and why)

- **Microservices, Redis, Celery, Kubernetes:** one shop, a handful of users, one PC. These would add failure points with no benefit.
- **Tally integration:** the client's CA keeps the books, so the plan is clean Excel exports instead.
- **WeasyPrint or other PDF libraries:** browser print CSS does the job, and these libraries need awkward native dependencies on Windows.
- **A cloud-hosted database:** the shop must keep billing when the internet is down.

---

## Architecture and design decisions

```
 Shop PC (server)                                      Other PCs / phones on shop Wi-Fi
 ┌───────────────────────────────────────────┐         ┌──────────────────────────┐
 │ uvicorn + FastAPI  (:8010)                │◀──HTTP──│ Browser                  │
 │   ├─ /api/*   JSON API (role-checked)     │         └──────────────────────────┘
 │   └─ /*       built React app (dist/)     │
 │ PostgreSQL 16                             │
 │   ├─ constraints, triggers, row locks     │
 │   └─ audit_log (append-only)              │
 └───────────────────────────────────────────┘
```

Request flow: **route** (`app/api`) → validates with a **schema** (`app/schemas`) → calls a **service** (`app/services`, where the business rules live) → works with **models** (`app/models`) inside **one database transaction**, which is committed or rolled back as a whole.

The key decisions, each of which is also a good interview talking point:

1. **Money is `Decimal` / `NUMERIC(12,2)`, never float.** All rounding goes through `services/money.py` (half-up to the paisa). Splitting freight across lines uses a largest-remainder method, so no paisa is lost or invented.
2. **Rates are quoted including GST**, the way cement is sold. For each line, `taxable = gross × 100 / (100 + GST%)` and `GST = gross − taxable`, so the customer pays *exactly* bags × rate. CGST+SGST or IGST is chosen from the customer's state versus the shop's state.
3. **GST rates and selling rates are effective-dated.** A rate change is a new row from a date, never an edit, so old bills keep their old rate and the 28% → 18% cut on 22 Sep 2025 is just data.
4. **Nothing financial is ever deleted or edited.** Bills, purchases and receipts are *cancelled* with a reason. Stock movements, the customer ledger and the audit log are append-only. **Postgres triggers enforce this**, so even a bug or a manual SQL command can't delete a bill.
5. **Stock is a list of movements.** Every bag in or out is a row, and a cached balance per product and godown makes reads fast. `GET /api/stock/verify` checks the cache against the movements. A CHECK constraint stops stock going negative.
6. **Weighted-average cost with row locks.** The balance row is locked (`SELECT … FOR UPDATE`) during an update, so two clerks saving at the same instant can't corrupt quantity or cost.
7. **Gap-free invoice numbers per financial year** (`INV/2026-27/0001`). They come from a locked counter row inside the same transaction as the bill, so a failed save uses no number.
8. **Idempotent saves.** The browser sends a random `client_ref` with each bill or receipt. A double-click or a retry after a network blip returns the *same* saved document instead of a duplicate.
9. **The customer ledger and open items always agree.** The ledger (debits and credits) and the per-bill unpaid balances are two views of the same money. `/api/reports/ledger-check` verifies `ledger balance = unpaid bills − advance` for every customer, and a property test proves it holds for any random mix of bills, payments, bounces, returns and cancellations.
10. **Money is counted on the day it moves (cash closing).** A cash bill counts on its bill date; a refund for a cancelled or returned bill counts on the refund date. Once a day is closed, its figures never change, and nothing dated on a closed day can be added.
11. **The audit log is written by the database.** A trigger records the old and new values of every change, along with the user, who is passed in per transaction via `SET LOCAL app.user_id`. The application has no code path that can skip it.
12. **Security:**
    - Sessions use a random token in an `httpOnly` cookie, and only its SHA-256 hash is stored.
    - Passwords are hashed with Argon2.
    - Disabling a user or resetting a password logs them out everywhere.
    - Role checks happen on the server.
    - Cost and margin are stripped from responses for roles that shouldn't see them.

---

## Project structure

```
cement-erp/
├── docker-compose.yml          Dev Postgres (port 5433) + creates cement_test
├── .env.example                All settings (copy to .env)
├── .github/workflows/ci.yml    CI: ruff, mypy, pytest (+Postgres), eslint, build
├── backend/
│   ├── pyproject.toml          Dependencies + ruff/mypy/pytest config
│   ├── alembic/versions/       0001 auth+audit · 0002 masters · 0003 purchases+stock
│   │                           0004 sales · 0005 receipts+ledger · 0006 expenses+cash
│   ├── app/
│   │   ├── main.py             FastAPI app, routers, serves frontend/dist
│   │   ├── cli.py              create-owner, reset-password
│   │   ├── dev_seed.py         Demo data for development
│   │   ├── core/               config, db session (+audit user hook), security, audit SQL
│   │   ├── models/             SQLAlchemy tables (user, masters, inventory, sales, credit, cash)
│   │   ├── schemas/            Pydantic request/response shapes
│   │   ├── api/                Routes: auth, users, masters, prices, purchases, stock,
│   │   │                       sales, receipts, cash
│   │   └── services/           Business rules:
│   │       ├── money.py        Decimal rounding, GST split, exact allocation
│   │       ├── gst.py          GSTIN check digit, state codes
│   │       ├── pricing.py      Effective-dated rates and GST lookups
│   │       ├── stock.py        Stock engine (weighted average, locks)
│   │       ├── purchases.py    Landed cost, purchase cancel
│   │       ├── billing.py      Bill maths, credit control, cancel, returns
│   │       ├── numbering.py    Gap-free numbers per financial year
│   │       ├── words.py        Amount in words (lakh/crore)
│   │       ├── ledger.py       Customer ledger, FIFO allocation, statements, ageing
│   │       ├── receipts.py     Payments, cheques, bounces, opening dues
│   │       └── cash.py         Expenses, cash day summary, closing, day lock
│   └── tests/                  pytest + Hypothesis (one file per area)
└── frontend/
    ├── vite.config.ts          Tailwind plugin, /api proxy → :8010
    └── src/
        ├── api/                fetch client (+error handling), shared TypeScript types
        ├── components/         Layout (role-aware sidebar), UI kit, CustomerPicker
        ├── lib/                auth (RequireAuth), formatting (₹, dates, paise), ids, roles
        └── pages/              One file per screen (NewBill, ReceivePayment, Statement, …)
```

---

## Data model

| Area | Tables |
|---|---|
| Access | `users` (role check), `user_sessions` (hashed tokens), `audit_log` (append-only, trigger-written) |
| Masters | `brands`, `products` (brand × grade × bag kg, HSN), `godowns`, `parties` (customer/supplier, GSTIN, state, credit limit/days, area), `gst_rates` (effective-dated), `prices` (effective-dated; optional per-party) |
| Stock | `stock_movements` (append-only), `stock_balances` (cached qty + average cost, never negative) |
| Purchases | `purchases`, `purchase_lines` (billed/good/damaged, landed cost) |
| Sales | `sales_invoices` (customer snapshot, tax split, client_ref), `sales_lines` (cost at sale), `sales_returns` + `sales_return_lines` (credit notes), `doc_series` (numbering) |
| Credit | `party_ledger` (append-only), `receipts` (cheque status), `receipt_allocations` (which bill a payment settled; released, never deleted), `other_dues` (old dues, bounce charges) |
| Cash | `expenses`, `cash_closings` (with denomination counts) |

---

## Testing and CI

```powershell
cd backend ; pytest            # 116 tests, ~35 s
```

- **Integration tests** call the real API (`TestClient`) against a real Postgres test database, built by running every Alembic migration, so the migrations are tested too. Each test runs inside a transaction that is rolled back, so tests can't affect each other.
- **Property-based tests (Hypothesis)** cover:
  - GSTIN check digits catch every single-character typo.
  - Charge allocation never loses a paisa.
  - CGST + SGST always equals GST.
  - Bill totals equal bags × rate.
  - Stock invariants hold over random in/out sequences.
  - The customer ledger always equals the unpaid bills after any random mix of operations.
- **CI** (`.github/workflows/ci.yml`) runs on every push and pull request: ruff, `ruff format --check`, mypy and pytest (with a Postgres service) for the backend, and ESLint plus the TypeScript build for the frontend.

---

## Configuration reference

All settings live in `.env` (see `.env.example`):

| Variable | Meaning | Example |
|---|---|---|
| `DATABASE_URL` | Main database | `postgresql+psycopg://cement:cement@localhost:5433/cement` |
| `TEST_DATABASE_URL` | Database the tests use (wiped on each run) | `…/cement_test` |
| `SECRET_KEY` | Long random secret | – |
| `SESSION_HOURS` | How long a login lasts | `12` |
| `COOKIE_SECURE` | `true` only when served over HTTPS | `false` |
| `SHOP_STATE_CODE` | Shop's GST state (decides CGST+SGST vs IGST) | `29` (Karnataka) |
| `SHOP_NAME`, `SHOP_ADDRESS`, `SHOP_GSTIN`, `SHOP_PHONE`, `SHOP_BANK` | Printed on invoices and receipts | – |

---

## API overview

Full, interactive documentation is at `http://localhost:8010/docs`. Main groups:

| Group | Endpoints |
|---|---|
| Auth & admin | `POST /api/auth/login`, `/logout`, `GET /api/auth/me`, `/api/users`, `GET /api/audit` |
| Masters | `/api/brands`, `/api/products`, `/api/godowns`, `/api/parties`, `/api/gst-rates` |
| Rates | `GET /api/prices/card`, `GET /api/prices/quote`, `POST /api/prices`, `/history`, `/special` |
| Purchases | `GET/POST /api/purchases`, `POST /api/purchases/{id}/cancel` |
| Stock | `GET /api/stock`, `/movements`, `POST /adjustments`, `POST /opening`, `GET /verify` |
| Sales | `POST /api/sales/preview`, `POST /api/sales`, `GET /api/sales[/{id}]`, `/cancel`, `/returns`, `GET /api/shop` |
| Receipts & credit | `POST /api/receipts/preview`, `POST /api/receipts`, `/cancel`, `/cheque`, `GET /api/cheques`, `GET /api/parties/{id}/open-bills`, `/ledger`, `POST /opening-dues`, `GET /api/reports/outstanding`, `/ledger-check` |
| Cash | `GET/POST /api/expenses`, `/cancel`, `GET /api/cash/day`, `POST /api/cash/close`, `GET /api/cash/closings` |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `docker compose up` says *no configuration file provided* | Run it from the repo root (where `docker-compose.yml` is), not from your home folder. |
| Docker: *Docker Engine stopped unexpectedly* | Usually a full C: drive. Free space, then quit Docker, run `wsl --shutdown`, and start Docker again. |
| Every API call returns 404 | Something else is using the port. Check with `Get-NetTCPConnection -LocalPort 8010`, or run on another port and update `vite.config.ts`. |
| "Wrong username or password" but you're sure | Type the password instead of pasting it (pasting can change `-` characters), or run `python -m app.cli reset-password <user>`. |
| A cash bill or expense is rejected as "already closed" | That day's cash was closed. Date it today instead; closed days are final by design. |
| Tests fail to connect | Start the database first: `docker compose up -d db`. |
