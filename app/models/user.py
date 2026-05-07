from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    household_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("households.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    # nullable=True so future OIDC-only users don't need a local password
    hashed_password: Mapped[str | None] = mapped_column(String, nullable=True)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    profile_picture_path: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # TODO (OIDC): Uncomment when implementing Pocket ID SSO
    # oidc_subject: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # oidc_provider: Mapped[str | None] = mapped_column(String, nullable=True)
