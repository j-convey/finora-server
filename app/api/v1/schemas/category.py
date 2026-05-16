from pydantic import BaseModel


class CategoryItem(BaseModel):
    """A single category with its stable canonical ID."""
    id: int
    name: str


class CategoryGroupResponse(BaseModel):
    """A category group with its ordered subcategory items (id + name)."""
    group: str
    type: str  # income | expense | transfer
    categories: list[CategoryItem]


class Category(BaseModel):
    name: str
    group_name: str | None = None
    type: str | None = None
    is_system: bool = False
    sort_order: int = 0
