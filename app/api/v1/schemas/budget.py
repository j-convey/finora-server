from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class BudgetBase(BaseModel):
    category: str
    allocated: Decimal = Field(..., gt=0, description="Monthly allocation in dollars")
    color: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$", description="Hex color e.g. #66BB6A")


class BudgetCreate(BudgetBase):
    pass


class BudgetUpdate(BaseModel):
    allocated: Optional[Decimal] = Field(None, gt=0)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class Budget(BudgetBase):
    id: str
    spent: Decimal = Field(description="Sum of expense transactions this calendar month")

    model_config = {"from_attributes": True, "json_encoders": {Decimal: float}}
