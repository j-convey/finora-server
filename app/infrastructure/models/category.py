from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Category(Base):
    """Canonical list of transaction categories.

    System categories (is_system=True, household_id=NULL) are seeded on startup 
    and shared across all households. Custom categories have a specific household_id.
    """

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("household_id", "name", name="uq_categories_household_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Top-level group this category belongs to (e.g. "Food & Dining", "Housing").
    # NULL only on legacy rows created before migration 011.
    group_name: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Inherited from the group: "income" | "expense" | "transfer".
    # NULL only on legacy rows created before migration 011.
    type: Mapped[str | None] = mapped_column(String, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
