finora_backend/
├── alembic/                          # unchanged (migrations stay exactly where they are)
│   ├── env.py
│   └── versions/
├── app/
│   ├── __init__.py
│   ├── main.py                       # ← moved from services/ + now wires logging middleware
│   ├── core/                         # cross-cutting concerns (enhanced)
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── auth.py
│   │   ├── crypto.py
│   │   ├── deps.py                   # common FastAPI dependencies
│   │   ├── exceptions.py             # centralized error handling
│   │   ├── logging.py                # ✨ **NEW** – single source of truth for structured logging
│   │   └── logging_middleware.py     # ✨ **NEW** – auto-injects request/household/transaction context
│   ├── domain/                       # pure business entities & value objects (Pydantic)
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── household.py
│   │   ├── account.py
│   │   ├── transaction.py
│   │   ├── reimbursement.py
│   │   ├── budget.py
│   │   ├── category.py
│   │   └── ...                       # more domains added here over time
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── database/
│   │   │   ├── base.py
│   │   │   └── session.py
│   │   ├── models/                   # SQLAlchemy models (moved from app/models/)
│   │   │   ├── __init__.py
│   │   │   ├── account_snapshot.py
│   │   │   ├── account.py
│   │   │   ├── ...                   # all existing model files
│   │   ├── repositories/             # ← NEW: pure data access layer
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── user_repository.py
│   │   │   ├── transaction_repository.py
│   │   │   └── ...
│   │   └── integrations/
│   │       └── simplefin/
│   │           ├── client.py
│   │           ├── service.py
│   │           ├── config.py
│   │           └── schemas.py
│   ├── application/                  # business logic / services (renamed for clarity)
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   ├── transaction_service.py
│   │   ├── budget_service.py
│   │   ├── net_worth_service.py
│   │   ├── reimbursement_service.py
│   │   ├── simplefin_sync_service.py
│   │   └── ...
│   ├── api/
│   │   ├── v1/                       # versioned API surface
│   │   │   ├── __init__.py
│   │   │   ├── deps.py               # endpoint-specific dependencies (now uses logger)
│   │   │   ├── routers/
│   │   │   │   ├── auth.py
│   │   │   │   ├── users.py
│   │   │   │   ├── transactions.py
│   │   │   │   ├── budgets.py
│   │   │   │   └── ...
│   │   │   └── schemas/              # request/response DTOs (moved from app/schemas/)
│   │   └── exceptions.py
│   └── tasks/                        # future Celery/background jobs
│       └── __init__.py
├── tests/                            # moved to root (best practice)
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   ├── api/
│   └── fixtures/
│       └── data/
│           └── transactions.csv      # ← moved from app/data/
├── data/                             # production seed files (optional)
├── scripts/                          # utility scripts
│   └── seeder.py                     # moved from services/
├── docs/                             # ← all .md files moved here (clean root!)
│   ├── ARCHITECTURE.md
│   ├── BACKEND_IMPLEMENTATION.md
│   ├── REIMBURSEMENTS_API.md
│   ├── REPORTS_BACKEND.md
│   └── ...                           # all existing docs
├── .github/
├── docker-compose*.yml
├── Dockerfile
├── requirements.txt                  # + structlog added
├── .env.example
├── startup.sh
├── README.md
└── ... (clean root – no more scattered .md files)