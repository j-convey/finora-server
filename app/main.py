from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import Base, engine
from app.routers import health, accounts, transactions, budgets, simplefin, categories, admin, subscriptions, auth, users
from app.services.seeder import seed_budgets, seed_account_snapshots, seed_categories
import app.models  # noqa: F401 — registers all models with Base.metadata


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is managed by Alembic (startup.sh runs `alembic upgrade head`
    # before uvicorn starts). Seed default data only.
    await seed_categories()
    await seed_budgets()
    await seed_account_snapshots()
    print("🚀 Starting Finora Backend...")
    yield
    # Shutdown
    await engine.dispose()
    print("👋 Shutting down Finora Backend...")


app = FastAPI(
    title="Finora API",
    description="Self-hosted AI-powered personal finance backend",
    version="0.1.0",
    lifespan=lifespan,
)

# Error handlers — return { "error": "..." } format
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": str(exc)})

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": str(exc)})

# CORS - adjust for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(users.router, prefix="/api", tags=["Users"])
app.include_router(accounts.router, prefix="/api", tags=["Accounts"])
app.include_router(transactions.router, prefix="/api", tags=["Transactions"])
app.include_router(budgets.router, prefix="/api", tags=["Budgets"])
app.include_router(categories.router, prefix="/api", tags=["Categories"])
app.include_router(subscriptions.router, prefix="/api", tags=["Subscriptions"])
app.include_router(admin.router, prefix="/api", tags=["Admin"])
app.include_router(simplefin.router, prefix="/api/simplefin", tags=["SimpleFIN"])


@app.get("/")
async def root():
    return {"message": "Welcome to Finora API", "docs": "/docs"}
