from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.auth import CurrentUser, create_access_token, hash_password, verify_password
from app.db import db_session, now_iso, row_to_dict, rows_to_dicts

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest) -> dict[str, Any]:
    with db_session() as conn:
        user = conn.execute(
            "SELECT * FROM app_users WHERE username = ? AND active_flag = 1",
            (body.username,),
        ).fetchone()
        if user is None or not verify_password(body.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user_d = row_to_dict(user)
    token = create_access_token(user_d)  # type: ignore[arg-type]
    return {"access_token": token, "token_type": "bearer", "user": _public_user(user_d)}  # type: ignore[arg-type]


@router.get("/me")
def me(user: CurrentUser) -> dict[str, Any]:
    return {"user": _public_user(user)}


@router.get("/demo-users")
def demo_users() -> dict[str, Any]:
    with db_session() as conn:
        users = rows_to_dicts(
            conn.execute(
                "SELECT username, role, display_name, driver_id, facility_id, carrier_id, customer_key FROM app_users WHERE active_flag=1 ORDER BY role, username"
            ).fetchall()
        )
    return {"users": users, "default_password": "pin1234"}


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "display_name": user["display_name"],
        "driver_id": user.get("driver_id"),
        "facility_id": user.get("facility_id"),
        "carrier_id": user.get("carrier_id"),
        "customer_key": user.get("customer_key"),
        "theme_pref": user.get("theme_pref"),
    }
