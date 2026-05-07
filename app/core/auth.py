"""
JWT authentication utilities.

Access tokens:  short-lived (15 min), HS256-signed JWTs carrying user_id + household_id.
Refresh tokens: opaque random strings — only the SHA-256 hash is stored in the DB
                so a compromised DB doesn't expose live sessions.

Token rotation: every /api/auth/refresh call issues a brand-new refresh token and
                invalidates the old one, limiting the window of a stolen token.

TODO (OIDC — Pocket ID):
  Add OIDC token validation here when implementing SSO:
  - Verify id_token JWTs against the provider's JWKS endpoint
  - Extract the "sub" claim to identify/match users
  - Use httpx (already installed) to call the userinfo endpoint
  - Store client_secret encrypted (same cryptography lib as SimpleFIN)
  See app/routers/auth.py for the TODO list of OIDC endpoints to add.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# tokenUrl must match the login endpoint path so Swagger UI works.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def create_access_token(user_id: int, household_id: int) -> str:
    """Create a signed JWT access token valid for ACCESS_TOKEN_EXPIRE_MINUTES."""
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "household_id": household_id,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token() -> tuple[str, str]:
    """Generate an opaque refresh token.

    Returns:
        (raw_token, token_hash) — send raw_token to the client, store token_hash in DB.
    """
    raw = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency — decode the Bearer JWT and return the authenticated User.

    Raises HTTP 401 if the token is missing, expired, malformed, or the user
    no longer exists / is deactivated.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")
        if user_id_str is None or token_type != "access":
            raise credentials_exception
        user_id = int(user_id_str)
    except (JWTError, ValueError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user
