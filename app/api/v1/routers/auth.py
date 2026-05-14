"""
Authentication endpoints.

POST /api/auth/register  — First-user bootstrap only (locks after first account exists).
POST /api/auth/login     — Email + password → access token + refresh token.
POST /api/auth/refresh   — Rotate refresh token → new access token + new refresh token.
POST /api/auth/logout    — Invalidate a refresh token (client must discard the JWT too).

Token strategy:
  Access token:  15-minute HS256 JWT — stateless, no DB lookup per request.
  Refresh token: 7-day opaque random string — stored as SHA-256 hash in DB,
                 rotated on every use so a stolen token has a narrow replay window.

TODO (OIDC — Pocket ID):
  Add the following endpoints in a follow-up PR once OIDC config table exists:

    GET  /api/auth/oidc/login
        Redirect the browser/app to Pocket ID's authorization URL.
        Append state + PKCE code_challenge for CSRF/replay protection.

    GET  /api/auth/oidc/callback
        Exchange the authorization code for tokens at Pocket ID's token endpoint.
        Call the userinfo endpoint to get email + name + picture.
        Match the returning user by oidc_subject (preferred) or email (fallback).
        If no matching Finora account → return 401 (owner must create accounts first).
        On success → issue Finora JWT + refresh token and redirect to the app.

    POST /api/auth/oidc/mobile-redirect
        Thin endpoint that Flutter's deep-link handler calls after receiving the
        authorization code via the custom URI scheme (e.g. finora://auth/callback).
        Exchanges the code and returns tokens as JSON (same as /callback but JSON).

    GET  /api/auth/oidc/config
        Return the current OIDC configuration (redact client_secret).

    POST /api/auth/oidc/config  { issuer_url, client_id, client_secret, ... }
        Save OIDC settings (encrypt client_secret at rest using the same
        cryptography lib used for SimpleFIN access URLs).

    POST /api/auth/oidc/discover  { issuer_url }
        Fetch /.well-known/openid-configuration and auto-populate all endpoint URLs.
        Same UX as Audiobookshelf's "Auto Populate" button.

  Redirect URIs to register in Pocket ID:
    https://<your-domain>/api/auth/oidc/callback
    <flutter-scheme>://auth/callback   (e.g. finora://auth/callback)
"""
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
)
from app.core.database import get_db
from app.infrastructure.models.household import Household
from app.infrastructure.models.refresh_token import RefreshToken
from app.infrastructure.models.user import User
from app.api.v1.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def _issue_tokens(db: AsyncSession, user: User) -> TokenResponse:
    """Mint an access token + refresh token, persist the refresh token hash."""
    access_token = create_access_token(user.id, user.household_id)
    raw_refresh, token_hash = create_refresh_token()
    expires_at = datetime.now(tz=timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    db.add(RefreshToken(
        token_hash=token_hash,
        user_id=user.id,
        expires_at=expires_at,
    ))
    await db.commit()
    return TokenResponse(access_token=access_token, refresh_token=raw_refresh)


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Bootstrap endpoint — creates the very first user and a default household.

    Returns 409 if any user already exists; registration is intentionally closed
    after the initial setup. To add a spouse or household member, log in and call
    POST /api/users instead.
    """
    count_result = await db.execute(select(func.count()).select_from(User))
    if count_result.scalar_one() > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Registration is closed. "
                "Ask the household owner to create an account for you via POST /api/users."
            ),
        )

    # Create the default household for this installation.
    household = Household(name="My Household")
    db.add(household)
    await db.flush()  # populate household.id before referencing it

    user = User(
        household_id=household.id,
        email=body.email,
        hashed_password=_hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.flush()  # populate user.id before _issue_tokens

    return await _issue_tokens(db, user)


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Email + password login. Returns a JWT access token and a refresh token."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalars().first()

    if not user or not user.hashed_password or not _verify_password(body.password, user.hashed_password):
        # Deliberate vague message — don't hint whether the email exists.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    return await _issue_tokens(db, user)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Exchange a valid refresh token for a new access token + new refresh token.

    The old refresh token is invalidated immediately (rotation). If the same
    refresh token is presented twice, the second call will return 401.
    """
    token_hash = _hash_refresh_token(body.refresh_token)
    now = datetime.now(tz=timezone.utc)

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalars().first()

    if not stored or stored.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or expired",
        )

    # Rotate: delete old token before issuing a new one.
    await db.delete(stored)
    await db.flush()

    user_result = await db.execute(select(User).where(User.id == stored.user_id))
    user = user_result.scalars().first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return await _issue_tokens(db, user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Invalidate the provided refresh token on the server.

    The client is responsible for discarding the access token locally — the server
    cannot revoke JWTs before they expire (15 min window is acceptable).
    """
    token_hash = _hash_refresh_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalars().first()
    if stored:
        await db.delete(stored)
        await db.commit()
