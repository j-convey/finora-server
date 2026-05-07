# Finora Backend — Architecture & Development Reference

## What This Is

Finora is a self-hosted, AI-powered personal finance app. This document covers the backend server only. The backend is a FastAPI application running in Docker, backed by PostgreSQL, with optional real bank data via the SimpleFIN Bridge protocol.

---

## Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI 0.111 (async) |
| Runtime | Python 3.12 |
| Database | PostgreSQL 16 (via Docker) |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic (not yet initialised — tables are auto-created on startup) |
| Validation | Pydantic v2 + pydantic-settings |
| HTTP client | httpx (async, used for SimpleFIN bridge calls) |
| Encryption | cryptography (Fernet — used to encrypt the SimpleFIN access URL at rest) |
| Container | Docker + Docker Compose |

---

## Running the App

```bash
cd server/
cp .env.example .env     # then edit .env — set POSTGRES_PASSWORD and SECRET_KEY
docker compose up --build
```

| URL | Purpose |
|---|---|
| `http://localhost:8080` | API root |
| `http://localhost:8080/docs` | Swagger UI (interactive docs, all endpoints) |
| `http://localhost:8080/redoc` | ReDoc |
| `http://localhost:8080/openapi.json` | OpenAPI schema (use this to auto-generate client code) |

---

## Environment Variables

Defined in `.env` (copy from `.env.example`). Required vars:

| Variable | Description |
|---|---|
| `POSTGRES_USER` | PostgreSQL username |
| `POSTGRES_PASSWORD` | PostgreSQL password — **change this** |
| `POSTGRES_DB` | Database name |
| `DATABASE_URL` | Full async connection string (`postgresql+asyncpg://...`) |
| `SECRET_KEY` | Long random string — used to sign JWTs (future) and to encrypt the SimpleFIN access URL at rest. **Change this. Never commit it.** |
| `ENVIRONMENT` | `development` or `production`. Controls SQLAlchemy echo logging. |
| `OLLAMA_BASE_URL` | Base URL for the local Ollama instance — for future AI features. Default: `http://host.docker.internal:11434` |

---

## Project Structure

```
server/
├── app/
│   ├── main.py                  # FastAPI app, middleware, error handlers, router wiring
│   ├── core/
│   │   ├── config.py            # Reads all env vars via pydantic-settings → settings object
│   │   ├── database.py          # Async SQLAlchemy engine, session factory, get_db() dependency
│   │   └── crypto.py            # Fernet encrypt/decrypt helpers (keyed from SECRET_KEY)
│   ├── models/                  # SQLAlchemy ORM table definitions
│   │   ├── user.py              # users table
│   │   ├── account.py           # accounts table
│   │   ├── transaction.py       # transactions table
│   │   ├── budget.py            # budgets table
│   │   └── simplefin_config.py  # simplefin_config table (singleton row)
│   ├── schemas/                 # Pydantic request/response models
│   │   ├── health.py
│   │   ├── account.py
│   │   ├── transaction.py
│   │   ├── budget.py            # BudgetCreate, BudgetUpdate, Budget (response)
│   │   └── simplefin.py
│   ├── services/                # Business logic — routers stay thin
│   │   ├── budget.py            # list/get/create/update/delete + spent computation
│   │   ├── simplefin.py         # SimpleFIN bridge HTTP calls (claim token, fetch data)
│   │   └── seeder.py            # Inserts default data on first startup
│   └── routers/
│       ├── health.py
│       ├── accounts.py
│       ├── transactions.py
│       ├── budgets.py           # Full CRUD — delegates to services/budget.py
│       └── simplefin.py
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Database Tables

Tables are **auto-created on startup** via `Base.metadata.create_all`. No Alembic migration has been run yet — when the schema starts changing regularly, initialise Alembic and stop using auto-create.

### `users`
Placeholder for future auth. Columns: `id`, `email`, `hashed_password`, `full_name`, `is_active`, `created_at`, `updated_at`.

### `accounts`
Financial accounts. Columns: `id` (string PK), `name`, `type`, `balance`, `institution_name`, `color`.

- `type` values: `checking | savings | credit_card | investment | cash`
- Credit card debt is a **negative balance**
- `color` is a hex string e.g. `#2196F3`

### `transactions`
Financial transactions. Columns: `id` (string PK), `title`, `amount`, `type`, `category`, `date`, `account_id`, `notes`.

- `amount` is always **positive**
- `type` determines direction: `income | expense | transfer`
- `category` is a free string; the Flutter app maps known values to icons

### `budgets`
Monthly budget envelopes. Columns: `id` (UUID string PK), `category` (unique), `allocated`, `color`.

- `spent` is **not stored** — it is computed at query time as `SUM(transactions.amount WHERE type='expense' AND category=? AND date >= start of current month)`
- `category` must be unique — one envelope per category
- `color` is a validated hex string (`#RRGGBB`)
- Default rows are seeded on first startup; re-runs are safe (idempotent)

Singleton table (always one row, `id=1`). Holds the SimpleFIN connection state.

- `access_url_encrypted` — the SimpleFIN access URL encrypted with Fernet using `SECRET_KEY`. **Never log or return this.**
- `institutions` — JSON array of institution names (e.g. `["Chase Bank", "Ally Bank"]`)
- `last_synced_at` — timestamp of last successful sync

---

## API Endpoints

### Health

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/health` | Liveness check — no DB hit |
| GET | `/api/v1/health/db` | Readiness check — runs `SELECT 1` |

### Finance Data

| Method | Path | Description |
|---|---|---|
| GET | `/api/accounts` | All accounts sorted by name. Returns DB data; falls back to seed data if DB is empty. |
| GET | `/api/transactions` | All transactions newest first. Returns DB data; falls back to seed data if DB is empty. |
| GET | `/api/budgets` | All budgets with `spent` computed live from this month's expense transactions. |
| POST | `/api/budgets` | Create a new budget envelope. Body: `{category, allocated, color}`. Returns `201`. |
| PATCH | `/api/budgets/{id}` | Update `allocated` and/or `color`. Partial — only send fields you want to change. |
| DELETE | `/api/budgets/{id}` | Delete a budget envelope. Returns `204 No Content`. |

### SimpleFIN

| Method | Path | Description |
|---|---|---|
| GET | `/api/simplefin/status` | Whether a SimpleFIN access URL is stored. |
| POST | `/api/simplefin/connect` | Body: `{"setup_token": "..."}`. Claims the token, fetches data, stores encrypted URL. |
| POST | `/api/simplefin/fetch` | Pulls fresh data from SimpleFIN, upserts accounts + transactions. |
| DELETE | `/api/simplefin/disconnect` | Deletes the stored credential. Existing data is kept. |

### Error format

All errors return JSON with an `error` key:

```json
{ "error": "description of what went wrong" }
```

---

## SimpleFIN Integration

SimpleFIN is a privacy-first bank data protocol. The flow is:

1. User visits `https://app.simplefin.org/simplefin/claim`, connects their bank, gets a **setup token** (a base64-encoded one-time URL).
2. The Flutter app sends that token to `POST /api/simplefin/connect`.
3. The server base64-decodes it to get a claim URL, POSTs to that URL (empty body, no auth), and receives back a permanent **access URL** containing HTTP Basic Auth credentials.
4. The access URL is Fernet-encrypted and stored in `simplefin_config`. It is never sent to the client.
5. From then on, `POST /api/simplefin/fetch` uses the stored URL to call `GET {access_url}/accounts?start-date=<30d ago>` and upsert the results.

**Mapping from SimpleFIN → DB:**

| SimpleFIN field | DB field | Notes |
|---|---|---|
| `account.id` | `accounts.id` | Stable upsert key |
| `account.org.name` | `accounts.institution_name` | |
| `account.name` | `accounts.name` | |
| `account.balance` | `accounts.balance` | String → float |
| `txn.id` | `transactions.id` | Stable upsert key |
| `txn.posted` | `transactions.date` | Unix timestamp → UTC datetime |
| `txn.amount` | `transactions.amount` + `type` | Negative → expense; positive → income |
| `txn.description` | `transactions.title` | Raw bank description |
| — | `transactions.category` | Defaults to `"Uncategorized"` until AI categorisation lands |

---

## CORS

Currently set to `allow_origins=["*"]` for Flutter web compatibility during development. **Lock this down before any public deployment** — set it to the specific origin of the Flutter app.

---

## Authentication

**Not yet implemented.** The `SECRET_KEY` env var and `users` table are already in place. The planned approach is standard JWT Bearer tokens:

```
Authorization: Bearer <token>
```

When auth lands, every finance data endpoint will require a valid token.

---

## What's Not Done Yet (in priority order)

1. **Auth** — register, login, JWT issue/verify, protect all data routes
2. **Alembic migrations** — run `alembic init alembic`, configure `env.py` to use the async engine and import `Base`, then generate and apply migrations instead of relying on auto-create
3. **AI categorisation** — use Ollama (already wired via `OLLAMA_BASE_URL`) to classify raw transaction descriptions into category strings
4. **POST/PUT/DELETE on transactions and accounts** — currently read-only; the Flutter app adds transactions locally only
5. **Production CORS** — replace `*` with the actual client origin
6. **Scheduled sync** — periodic background task to call the SimpleFIN fetch automatically (e.g. via APScheduler or a cron job hitting the fetch endpoint)

---

## Seed Data

When the DB is empty (before any SimpleFIN sync), the accounts and transactions endpoints return hardcoded seed data so the Flutter app has something to display immediately. Once a SimpleFIN sync has run, real data takes over.

Seed accounts: Main Checking, Emergency Fund, Visa Platinum, Investment Portfolio, Cash Wallet.
Seed transactions: 15 entries spanning the last 20 days across categories: Income, Groceries, Subscriptions, Transport, Dining, Rent, Health, Utilities, Shopping, Entertainment.
Seed budgets: 7 envelopes (Groceries, Dining, Transport, Entertainment, Subscriptions, Health, Shopping) inserted on first startup by `services/seeder.py`. Safe to re-run.

---

## Client-Side Integration — Budgets

This section is for the Flutter developer.

### What changed

The budgets endpoint was previously returning hardcoded static data. It now:
- Reads budgets from the database
- Computes `spent` **live** at request time — it is the sum of all `expense` transactions for that category in the current calendar month
- Supports create, update, and delete so users can manage their own envelopes

The response shape of `GET /api/budgets` **has not changed** — the Flutter app does not need to update its model.

### New requests the client can make

#### Create a budget
```
POST /api/budgets
Content-Type: application/json

{
  "category": "Coffee",
  "allocated": 60.00,
  "color": "#8D6E63"
}
```
Response: `201 Created` with the full budget object (including `spent: 0.0` if no transactions yet).

#### Update a budget (allocated amount or color)
```
PATCH /api/budgets/{id}
Content-Type: application/json

{ "allocated": 500.00 }
```
Only send the fields you want to change. Response: `200` with the updated budget.

#### Delete a budget
```
DELETE /api/budgets/{id}
```
Response: `204 No Content`.

### Important behavior notes for the UI

- **`spent` is always live.** Every call to `GET /api/budgets` recomputes it. There is no caching — the number reflects the actual DB state at that moment.
- **`spent` counts only the current calendar month** (UTC). If today is May 15, only expense transactions dated May 1–May 15 (UTC) are summed. On June 1, `spent` resets to 0 automatically.
- **Category matching is case-sensitive and exact.** A transaction with `category: "groceries"` will not count toward a budget with `category: "Groceries"`. Ensure the Flutter app uses consistent casing when creating local transactions.
- **One envelope per category** is enforced by a unique constraint on the `category` column. Attempting to create a duplicate will return a `500` error (will become a proper `409` when error handling is expanded).
- **`color` must be `#RRGGBB` format.** The API validates this — sending `#FFF` or `blue` will return a `422`.
