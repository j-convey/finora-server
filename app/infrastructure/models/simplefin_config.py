from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SimplefinConfig(Base):
    """SimpleFIN connection state per household.
    
    One row per household (household_id is primary key). Stores encrypted
    access URL and sync metadata for that household's SimpleFIN integration.
    """

    __tablename__ = "simplefin_config"

    household_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("households.id", ondelete="CASCADE"), primary_key=True
    )
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
