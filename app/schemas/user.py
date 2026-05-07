from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    id: int
    household_id: int
    email: str
    full_name: str | None
    # Constructed from profile_picture_path by the router — clients use this URL directly.
    profile_picture_url: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
