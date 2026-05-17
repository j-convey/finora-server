from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.database import Base, engine, AsyncSessionLocal
from app.core.logging import get_logger, setup_logging
from app.core.logging_middleware import LoggingMiddleware
from app.api.v1.routers import health, accounts, transactions, budgets, simplefin, categories, admin, subscriptions, auth, users, demo
import app.infrastructure.models  # noqa: F401 — registers all models with Base.metadata

setup_logging()
logger = get_logger(__name__)


async def _auto_sync_simplefin() -> None:
    """Background task: fetch latest SimpleFIN data on a schedule."""
    from app.infrastructure.models.simplefin_config import SimplefinConfig
    from app.api.v1.routers.simplefin import _do_fetch
    from app.core.crypto import decrypt

    async with AsyncSessionLocal() as db:
        try:
            config = await db.get(SimplefinConfig, 1)
            if config is None:
                return  # Not connected yet — skip silently

            access_url = decrypt(config.access_url_encrypted, settings.SECRET_KEY)
            result = await _do_fetch(access_url, db)

            # Update last_synced_at
            config.institutions = result["institutions"]
            config.last_synced_at = result["last_synced_at"]
            await db.commit()

            if result["transactions_added"] > 0:
                logger.info(
                    "auto-sync completed",
                    transactions_added=result["transactions_added"],
                    accounts_updated=result["accounts_updated"],
                )
        except Exception:
            logger.exception("auto-sync failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is managed by Alembic (startup.sh runs `alembic upgrade head`
    # before uvicorn starts).

    # Start background scheduler — sync SimpleFIN every 2 hours
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _auto_sync_simplefin,
        trigger=IntervalTrigger(hours=2),
        id="simplefin_auto_sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("starting Finora backend")
    yield
    # Shutdown
    scheduler.shutdown(wait=False)
    await engine.dispose()
    logger.info("shutting down Finora backend")


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
    return JSONResponse(status_code=500, content={"error": "An internal server error occurred"})

# CORS — wildcard origins cannot be combined with allow_credentials=True (CORS spec
# §3.2.5 forbids it; browsers will reject such responses). Specify your frontend
# origin(s) via the ALLOWED_ORIGINS env var in production, e.g.:
#   ALLOWED_ORIGINS=https://app.yourdomain.com
# Wildcard is acceptable only for fully public, unauthenticated APIs.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to known frontend origins in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

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
app.include_router(demo.router)


@app.get("/")
async def root():
    return {"message": "Welcome to Finora API", "docs": "/docs"}
