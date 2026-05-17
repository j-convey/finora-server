from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


from fastapi import Header

async def get_db(x_demo_mode: str = Header(None, alias="X-Demo-Mode", description="Set to 'true' to use the demo database schema.")) -> AsyncSession:
    async with AsyncSessionLocal() as session:
        is_demo = str(x_demo_mode).lower() == "true" if x_demo_mode else False
        schema_name = settings.DEMO_SCHEMA if is_demo else "public"

        try:
            # Safely parameterize search_path by using schema translate map.
            # Using raw text("SET search_path TO ...") is also possible if we reset it,
            # but setting execution options is cleaner for SQLAlchemy per-session.
            # However, since we're not defining schema in __table_args__ for all models,
            # we must explicitly use `SET search_path TO <schema>` and ensure we reset it.
            if is_demo:
                await session.execute(text(f"SET search_path TO {schema_name}"))

            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            if is_demo:
                try:
                    # Always reset back to public to prevent connection pool leakage
                    await session.execute(text("SET search_path TO public"))
                    await session.commit() # commit the search_path reset
                except Exception:
                    # If this fails (e.g. connection already closed/broken), rollback
                    # but don't mask the original exception if we were already unwinding.
                    await session.rollback()
