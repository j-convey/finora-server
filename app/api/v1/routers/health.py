from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.schemas.health import DatabaseHealthResponse, HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        message="Finora API is running",
        version="0.1.0",
    )


@router.get("/health/db", response_model=DatabaseHealthResponse)
async def database_health_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return DatabaseHealthResponse(
        status="healthy",
        message="Finora API is running",
        version="0.1.0",
        database="connected",
    )
