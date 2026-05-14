from pydantic import BaseModel


class Category(BaseModel):
    name: str
    is_system: bool = False
    sort_order: int = 0
