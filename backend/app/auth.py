from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings
from app.db import db_session, row_to_dict

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

ROLES = ("DRIVER", "OPERATIONS", "WAREHOUSE", "ADMIN", "CARRIER", "CUSTOMER")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user: dict[str, Any]) -> str:
    settings = get_settings()
    jti = str(uuid4())
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "driver_id": user.get("driver_id"),
        "facility_id": user.get("facility_id"),
        "carrier_id": user.get("carrier_id"),
        "customer_key": user.get("customer_key"),
        "display_name": user.get("display_name"),
        "jti": jti,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO app_sessions(session_id, user_id, jti, expires_at, revoked_flag, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (str(uuid4()), user["user_id"], jti, expire.isoformat(), datetime.now(timezone.utc).isoformat()),
        )
    return token


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict[str, Any]:
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(creds.credentials)
    with db_session() as conn:
        session = conn.execute(
            "SELECT * FROM app_sessions WHERE jti = ? AND revoked_flag = 0",
            (payload.get("jti"),),
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked")
        user = conn.execute(
            "SELECT * FROM app_users WHERE user_id = ? AND active_flag = 1",
            (payload["sub"],),
        ).fetchone()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
        return row_to_dict(user)  # type: ignore[return-value]


def require_roles(*roles: str):
    def _dep(user: Annotated[dict[str, Any], Depends(get_current_user)]) -> dict[str, Any]:
        if user["role"] not in roles and user["role"] != "ADMIN":
            # ADMIN bypasses for manageability except when explicitly excluding
            if "ADMIN" in roles or user["role"] == "ADMIN":
                if user["role"] == "ADMIN":
                    return user
            if user["role"] not in roles:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return _dep


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
