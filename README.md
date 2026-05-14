# Finora Server

A self-hosted, AI-powered personal finance backend built with FastAPI, PostgreSQL, and SQLAlchemy. Finora manages accounts, transactions, budgets, subscriptions, and net-worth tracking with multi-user household support.

**Features:**
- 🔐 JWT-based authentication with household sharing
- 💰 Multi-account tracking (checking, savings, credit cards, investments, cash)
- 📊 Net-worth snapshots and history charts
- 📱 Budget envelopes with real-time spend tracking
- 🔗 Subscription tracking and auto-linking
- 🌐 SimpleFIN API integration for transaction imports
- 👥 Multi-user household support (spouse/partner accounts)
- 📁 Admin tools: database export/import, reset, backup
- 🔄 Automatic migrations and schema management
- 🐳 Docker & Docker Compose ready

---

## Quick Start

### Option 1: Docker Compose (Recommended)

Clone the repo and run:

```bash
git clone https://github.com/jconvey/finora-server.git
cd finora-server
cp .env.example .env
docker compose up -d
```

Server runs at `http://localhost:8080`

### Option 2: Docker Directly

Pull and run the image:

```bash
docker run -d \
  --name finora-server \
  -p 8080:8080 \
  -e DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/finora_db \
  -e SECRET_KEY=your-secret-key \
  -e POSTGRES_USER=finora \
  -e POSTGRES_PASSWORD=your-db-password \
  jconvey/finora-server:latest
```

> **Note:** You still need a PostgreSQL database. Use `docker-compose.yml` from the repo for a complete stack.

---

## Requirements

- **Docker** and **Docker Compose** (v2.0+)
- **PostgreSQL** 16+ (included in compose)
- **Python** 3.12+ (if running locally without Docker)

---

## Configuration

All configuration via environment variables (in `.env`):

```env
# Database
DATABASE_URL=postgresql+asyncpg://finora:password@db:5432/finora_db
POSTGRES_USER=finora
POSTGRES_PASSWORD=change_me
POSTGRES_DB=finora_db

# App
SECRET_KEY=your-very-long-random-secret-key-here
ENVIRONMENT=production

# Optional: LLM integration (for future features)
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

---

## API Overview

### Authentication
- `POST /api/auth/register` — First-user bootstrap (locks after first account)
- `POST /api/auth/login` — Email + password login
- `POST /api/auth/refresh` — Rotate access token
- `POST /api/auth/logout` — Invalidate session

### Users
- `GET /api/users/me` — Current user profile
- `GET /api/users` — List household members
- `POST /api/users` — Add household member
- `POST /api/users/me/avatar` — Upload profile picture

### Finance
- `GET /api/accounts` — List all accounts
- `GET /api/accounts/net-worth-history` — Net worth trends
- `GET /api/transactions` — Transaction list with filtering
- `PATCH /api/transactions/{id}` — Update transaction
- `GET /api/budgets` — Budget envelopes
- `POST /api/budgets` — Create budget
- `GET /api/subscriptions` — Active subscriptions
- `POST /api/subscriptions` — Create subscription
- `POST /api/subscriptions/{id}/link/{tx_id}` — Link transaction to subscription

### Admin
- `POST /api/admin/reset-database` — Clear all data
- `GET /api/admin/export-database` — Full DB backup as JSON
- `POST /api/admin/import-database` — Restore from JSON
- `GET /api/admin/subscriptions/suggestions` — AI-suggest subscriptions
- `POST /api/admin/subscriptions/backfill` — Auto-link historical transactions

### Integrations
- `POST /api/simplefin/set-credentials` — Configure SimpleFIN access
- `GET /api/simplefin/accounts` — Fetch linked accounts
- `POST /api/simplefin/import-transactions` — Import transactions from SimpleFIN

Full API docs: `http://localhost:8080/docs` (Swagger UI)

---

## Client Setup

See [CLIENT_AUTH_MIGRATION.md](./docs/CLIENT_AUTH_MIGRATION.md) for detailed Flutter client integration guide covering:
- Token storage and rotation
- HTTP interceptor setup
- Breaking API changes
- Complete endpoint reference

---

## Architecture

- **Framework:** FastAPI 0.111.0
- **ORM:** SQLAlchemy 2.0.30 with async support
- **Database:** PostgreSQL 16 + asyncpg
- **Migrations:** Alembic 1.13.1 (auto-run on startup)
- **Auth:** JWT (HS256) + refresh token rotation
- **Security:** bcrypt password hashing, encrypted secret storage
- **Deployment:** Docker + GitHub Actions CI/CD

For detailed architecture: see [ARCHITECTURE.md](./docs/ARCHITECTURE.md)

---

## Development

### Local Setup (without Docker)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env with DATABASE_URL pointing to local PostgreSQL
export $(cat .env | xargs)

# Run migrations
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload
```

### Run Tests

```bash
pytest tests/
```

---

## Docker Hub

This image is automatically built and pushed to Docker Hub on every push to `main`:

```bash
docker pull jconvey/finora-server:latest
```

Or with a specific commit SHA:
```bash
docker pull jconvey/finora-server:sha-abc123def
```

---

## Roadmap

- [ ] OIDC/SSO support (Pocket ID)
- [ ] Mobile app authentication
- [ ] AI-powered expense categorization
- [ ] Receipt OCR and parsing
- [ ] Multi-currency support
- [ ] Recurring transaction templates
- [ ] Data sync to mobile

---

## License

Apache License 2.0 — See [LICENSE](./LICENSE) for details.

---

## Support

- 📖 **Docs:** [BACKEND_IMPLEMENTATION.md](./docs/BACKEND_IMPLEMENTATION.md)
- 🐛 **Issues:** [GitHub Issues](https://github.com/jconvey/finora-server/issues)
- 💬 **Discussions:** [GitHub Discussions](https://github.com/jconvey/finora-server/discussions)

---

