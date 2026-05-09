"""
User management endpoints.

GET    /api/users              — List all users in the same household.
POST   /api/users              — Create a new household member (must be logged in).
GET    /api/users/me           — Current user's profile.
PATCH  /api/users/me           — Update name / email.
POST   /api/users/me/avatar    — Upload a profile picture (JPEG / PNG / WebP).
GET    /api/users/{id}/avatar  — Serve a user's avatar (no auth required — URL is opaque).
DELETE /api/users/{id}         — Remove a user from the household (cannot delete yourself).

Avatar storage:
  Files are saved to /app/uploads/avatars/ which is mounted as a Docker volume
  (finoraserver_uploads) so avatars survive container rebuilds.
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Mounted from the Docker volume — persists across container rebuilds.
AVATAR_DIR = Path("/app/uploads/avatars")

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_EXT_MAP = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _user_to_response(user: User) -> UserResponse:
    pic_url = f"/api/users/{user.id}/avatar" if user.profile_picture_path else None
    return UserResponse(
        id=user.id,
        household_id=user.household_id,
        email=user.email,
        full_name=user.full_name,
        profile_picture_url=pic_url,
        is_active=user.is_active,
        created_at=user.created_at,
    )


# ── Household member list ─────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all users in the same household as the caller."""
    result = await db.execute(
        select(User).where(User.household_id == current_user.household_id)
    )
    return [_user_to_response(u) for u in result.scalars().all()]


# ── Current user ──────────────────────────────────────────────────────────────

@router.get("/users/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return _user_to_response(current_user)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/users/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify the current password then hash and store the new one."""
    if not pwd_context.verify(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    current_user.hashed_password = pwd_context.hash(body.new_password)
    await db.commit()


@router.patch("/users/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    updates = body.model_dump(exclude_unset=True)
    if "email" in updates:
        conflict = await db.execute(select(User).where(User.email == updates["email"]))
        conflicting_user = conflict.scalars().first()
        if conflicting_user and conflicting_user.id != current_user.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
    for key, val in updates.items():
        setattr(current_user, key, val)
    await db.commit()
    await db.refresh(current_user)
    return _user_to_response(current_user)


# ── Avatar ─────────────────────────────────────────────────────────────────────

@router.post("/users/me/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a profile picture. Accepted formats: JPEG, PNG, WebP.
    Stored at /app/uploads/avatars/ on the Docker volume so it survives rebuilds.
    """
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, and WebP images are accepted",
        )

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)

    # Remove the old avatar file if one exists.
    if current_user.profile_picture_path:
        old = Path(current_user.profile_picture_path)
        if old.exists():
            old.unlink()

    ext = _EXT_MAP[file.content_type]
    dest = AVATAR_DIR / f"{uuid.uuid4()}.{ext}"
    dest.write_bytes(await file.read())

    current_user.profile_picture_path = str(dest)
    await db.commit()
    await db.refresh(current_user)
    return _user_to_response(current_user)


@router.get("/users/{user_id}/avatar")
async def get_avatar(user_id: int, db: AsyncSession = Depends(get_db)):
    """
    Serve a user's avatar image. No auth required — the URL path already
    obscures the resource (no guessable IDs beyond integer user IDs).
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user or not user.profile_picture_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No avatar set")
    path = Path(user.profile_picture_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar file not found")
    return FileResponse(str(path))


# ── Create / delete household member ─────────────────────────────────────────

class CreateUserRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_household_member(
    body: CreateUserRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new user in the same household as the caller.
    Both users are equal — no roles or permission hierarchy.
    """
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalars().first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    new_user = User(
        household_id=current_user.household_id,
        email=body.email,
        hashed_password=pwd_context.hash(body.password),
        full_name=body.full_name,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return _user_to_response(new_user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a user from the household. You cannot delete your own account."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )
    result = await db.execute(
        select(User).where(User.id == user_id, User.household_id == current_user.household_id)
    )
    target = result.scalars().first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in your household",
        )
    await db.delete(target)
    await db.commit()
