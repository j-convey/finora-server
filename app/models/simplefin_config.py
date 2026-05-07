from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SimplefinConfig(Base):
    """Singleton row (id=1) holding the SimpleFIN connection state."""

    __tablename__ = "simplefin_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    access_url_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    institutions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
