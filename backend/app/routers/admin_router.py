from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.auth import CurrentUser, ROLES, hash_password
from app.db import db_session, now_iso, rebuild_database, rows_to_dicts

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(user: dict[str, Any]) -> None:
    if user["role"] != "ADMIN":
        raise HTTPException(403, "Admin only")


class UserCreate(BaseModel):
    username: str
    password: str
    role: str
    display_name: str
    driver_id: str | None = None
    facility_id: str | None = None
    carrier_id: str | None = None
    customer_key: str | None = None


class UserUpdate(BaseModel):
    role: str | None = None
    display_name: str | None = None
    password: str | None = None
    active_flag: int | None = None
    driver_id: str | None = None
    facility_id: str | None = None
    carrier_id: str | None = None
    customer_key: str | None = None
    theme_pref: str | None = None


class SettingUpdate(BaseModel):
    setting_value: str


@router.get("/users")
def list_users(user: CurrentUser) -> dict[str, Any]:
    _require_admin(user)
    with db_session() as conn:
        rows = rows_to_dicts(
            conn.execute(
                "SELECT user_id, username, role, display_name, driver_id, facility_id, carrier_id, customer_key, active_flag, theme_pref, created_at FROM app_users ORDER BY role, username"
            ).fetchall()
        )
    return {"users": rows, "roles": list(ROLES)}


@router.post("/users")
def create_user(body: UserCreate, user: CurrentUser) -> dict[str, Any]:
    _require_admin(user)
    if body.role not in ROLES:
        raise HTTPException(400, "Invalid role")
    user_id = f"USR-{uuid4().hex[:8].upper()}"
    ts = now_iso()
    with db_session() as conn:
        try:
            conn.execute(
                """
                INSERT INTO app_users(
                    user_id, username, password_hash, role, display_name,
                    driver_id, facility_id, carrier_id, customer_key,
                    active_flag, theme_pref, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'system', ?, ?)
                """,
                (
                    user_id,
                    body.username,
                    hash_password(body.password),
                    body.role,
                    body.display_name,
                    body.driver_id,
                    body.facility_id,
                    body.carrier_id,
                    body.customer_key,
                    ts,
                    ts,
                ),
            )
            conn.execute(
                """
                INSERT INTO admin_audit_events(audit_id, actor_user_id, action, entity_type, entity_id, detail_json, created_at)
                VALUES (?, ?, 'CREATE_USER', 'app_users', ?, ?, ?)
                """,
                (f"AUD-{uuid4().hex[:8].upper()}", user["user_id"], user_id, json.dumps({"role": body.role}), ts),
            )
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "user_id": user_id}


@router.patch("/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, user: CurrentUser) -> dict[str, Any]:
    _require_admin(user)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return {"ok": True}
    if "password" in fields:
        fields["password_hash"] = hash_password(fields.pop("password"))
    if "role" in fields and fields["role"] not in ROLES:
        raise HTTPException(400, "Invalid role")
    sets = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [now_iso(), user_id]
    with db_session() as conn:
        conn.execute(f"UPDATE app_users SET {sets}, updated_at=? WHERE user_id=?", values)
        conn.execute(
            """
            INSERT INTO admin_audit_events(audit_id, actor_user_id, action, entity_type, entity_id, detail_json, created_at)
            VALUES (?, ?, 'UPDATE_USER', 'app_users', ?, ?, ?)
            """,
            (
                f"AUD-{uuid4().hex[:8].upper()}",
                user["user_id"],
                user_id,
                json.dumps({k: v for k, v in fields.items() if k != "password_hash"}),
                now_iso(),
            ),
        )
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, user: CurrentUser) -> dict[str, Any]:
    _require_admin(user)
    if user_id == user["user_id"]:
        raise HTTPException(400, "Cannot delete your own account")
    with db_session() as conn:
        row = conn.execute("SELECT username FROM app_users WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        conn.execute("DELETE FROM app_sessions WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM app_users WHERE user_id=?", (user_id,))
        conn.execute(
            """
            INSERT INTO admin_audit_events(audit_id, actor_user_id, action, entity_type, entity_id, detail_json, created_at)
            VALUES (?, ?, 'DELETE_USER', 'app_users', ?, ?, ?)
            """,
            (
                f"AUD-{uuid4().hex[:8].upper()}",
                user["user_id"],
                user_id,
                json.dumps({"username": row["username"]}),
                now_iso(),
            ),
        )
    return {"ok": True}


@router.get("/settings")
def get_settings_admin(user: CurrentUser) -> dict[str, Any]:
    _require_admin(user)
    with db_session() as conn:
        rows = rows_to_dicts(conn.execute("SELECT * FROM app_settings ORDER BY setting_key").fetchall())
    return {"settings": rows}


@router.get("/baseline")
def get_baseline(user: CurrentUser) -> dict[str, Any]:
    _require_admin(user)
    with db_session() as conn:
        row = conn.execute("SELECT setting_value FROM app_settings WHERE setting_key = ?", ("manual_baseline",)).fetchone()
    return {"baseline": json.loads(row["setting_value"]) if row and row["setting_value"] else {}}


@router.put("/baseline")
def put_baseline(body: dict[str, Any], user: CurrentUser) -> dict[str, Any]:
    _require_admin(user)
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO app_settings(setting_key, setting_value, description, updated_at, updated_by)
            VALUES (?, ?, COALESCE((SELECT description FROM app_settings WHERE setting_key=?), ''), ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
              setting_value=excluded.setting_value,
              updated_at=excluded.updated_at,
              updated_by=excluded.updated_by
            """,
            ("manual_baseline", json.dumps(body), "manual_baseline", now_iso(), user["user_id"]),
        )
    return {"ok": True}


@router.put("/settings/{key}")
def put_setting(key: str, body: SettingUpdate, user: CurrentUser) -> dict[str, Any]:
    _require_admin(user)
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO app_settings(setting_key, setting_value, description, updated_at, updated_by)
            VALUES (?, ?, COALESCE((SELECT description FROM app_settings WHERE setting_key=?), ''), ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
              setting_value=excluded.setting_value,
              updated_at=excluded.updated_at,
              updated_by=excluded.updated_by
            """,
            (key, body.setting_value, key, now_iso(), user["user_id"]),
        )
    return {"ok": True}


@router.post("/rebuild-db")
def rebuild_db(user: CurrentUser) -> dict[str, Any]:
    """Dev/script helper — not exposed in the Settings UI."""
    _require_admin(user)
    rebuild_database(force=True)
    return {"ok": True, "message": "Database rebuilt from seed + migrations"}


@router.get("/audit")
def audit(user: CurrentUser) -> dict[str, Any]:
    _require_admin(user)
    with db_session() as conn:
        rows = rows_to_dicts(
            conn.execute("SELECT * FROM admin_audit_events ORDER BY created_at DESC LIMIT 200").fetchall()
        )
    return {"events": rows}


MASTER_TABLES = {
    "facilities",
    "docks",
    "facility_rules",
    "carriers",
    "drivers",
    "vehicles",
    "shipments",
    "facility_geo",
    "facility_contacts",
}


def _assert_master_table(table: str) -> None:
    if table not in MASTER_TABLES:
        raise HTTPException(400, "Table not allowed")


def _master_columns(conn: Any, table: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [
        {
            "name": r["name"],
            "type": r["type"],
            "notnull": bool(r["notnull"]),
            "pk": bool(r["pk"]),
            "dflt_value": r["dflt_value"],
        }
        for r in rows
    ]


def _coerce_value(raw: Any, col_type: str) -> Any:
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip() == "":
        return None
    t = (col_type or "").upper()
    if "INT" in t:
        return int(raw)
    if "REAL" in t or "FLOA" in t or "DOUB" in t:
        return float(raw)
    return str(raw)


def _normalize_row(values: dict[str, Any], columns: list[dict[str, Any]], *, require_all: bool) -> dict[str, Any]:
    allowed = {c["name"]: c for c in columns}
    unknown = set(values) - set(allowed)
    if unknown:
        raise HTTPException(400, f"Unknown columns: {', '.join(sorted(unknown))}")
    out: dict[str, Any] = {}
    for name, col in allowed.items():
        if name not in values:
            if require_all and col["notnull"] and col["dflt_value"] is None and not col["pk"]:
                # PK still required on create when provided; skip optional defaults
                pass
            continue
        try:
            out[name] = _coerce_value(values[name], col["type"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, f"Invalid value for {name}") from exc
        if out[name] is None and col["notnull"] and col["dflt_value"] is None:
            raise HTTPException(400, f"{name} is required")
    if require_all:
        missing = [
            c["name"]
            for c in columns
            if c["name"] not in out and c["notnull"] and c["dflt_value"] is None
        ]
        if missing:
            raise HTTPException(400, f"Missing required fields: {', '.join(missing)}")
    return out


def _audit(conn: Any, actor_user_id: str, action: str, entity_type: str, entity_id: str, detail: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO admin_audit_events(audit_id, actor_user_id, action, entity_type, entity_id, detail_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"AUD-{uuid4().hex[:8].upper()}",
            actor_user_id,
            action,
            entity_type,
            entity_id,
            json.dumps(detail),
            now_iso(),
        ),
    )


class MasterRowBody(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class MasterUpdateBody(BaseModel):
    key: dict[str, Any]
    values: dict[str, Any] = Field(default_factory=dict)


@router.get("/master/{table}")
def master_table(table: str, user: CurrentUser) -> dict[str, Any]:
    _require_admin(user)
    _assert_master_table(table)
    with db_session() as conn:
        columns = _master_columns(conn, table)
        rows = rows_to_dicts(conn.execute(f"SELECT * FROM {table} LIMIT 500").fetchall())
    return {
        "table": table,
        "rows": rows,
        "columns": columns,
        "primary_key": [c["name"] for c in columns if c["pk"]],
    }


@router.post("/master/{table}")
def create_master_row(table: str, body: MasterRowBody, user: CurrentUser) -> dict[str, Any]:
    _require_admin(user)
    _assert_master_table(table)
    with db_session() as conn:
        columns = _master_columns(conn, table)
        row = _normalize_row(body.values, columns, require_all=True)
        cols = list(row.keys())
        placeholders = ", ".join("?" for _ in cols)
        try:
            conn.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
                [row[c] for c in cols],
            )
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        pk_cols = [c["name"] for c in columns if c["pk"]]
        entity_id = "|".join(str(row.get(k, "")) for k in pk_cols) or table
        _audit(conn, user["user_id"], "CREATE_MASTER", table, entity_id, {"values": row})
    return {"ok": True}


@router.put("/master/{table}")
def update_master_row(table: str, body: MasterUpdateBody, user: CurrentUser) -> dict[str, Any]:
    _require_admin(user)
    _assert_master_table(table)
    with db_session() as conn:
        columns = _master_columns(conn, table)
        pk_cols = [c["name"] for c in columns if c["pk"]]
        if not pk_cols:
            raise HTTPException(400, "Table has no primary key")
        key = _normalize_row(body.key, [c for c in columns if c["pk"]], require_all=True)
        if set(key) != set(pk_cols):
            raise HTTPException(400, f"Key must include: {', '.join(pk_cols)}")
        updates = _normalize_row(body.values, columns, require_all=False)
        for pk in pk_cols:
            updates.pop(pk, None)
        if not updates:
            return {"ok": True}
        set_sql = ", ".join(f"{c}=?" for c in updates)
        where_sql = " AND ".join(f"{c}=?" for c in pk_cols)
        try:
            cur = conn.execute(
                f"UPDATE {table} SET {set_sql} WHERE {where_sql}",
                [*updates.values(), *[key[c] for c in pk_cols]],
            )
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        if cur.rowcount == 0:
            raise HTTPException(404, "Row not found")
        entity_id = "|".join(str(key[c]) for c in pk_cols)
        _audit(conn, user["user_id"], "UPDATE_MASTER", table, entity_id, {"values": updates})
    return {"ok": True}


@router.delete("/master/{table}")
def delete_master_row(table: str, body: MasterRowBody, user: CurrentUser) -> dict[str, Any]:
    _require_admin(user)
    _assert_master_table(table)
    with db_session() as conn:
        columns = _master_columns(conn, table)
        pk_cols = [c["name"] for c in columns if c["pk"]]
        if not pk_cols:
            raise HTTPException(400, "Table has no primary key")
        key = _normalize_row(body.values, [c for c in columns if c["pk"]], require_all=True)
        if set(key) != set(pk_cols):
            raise HTTPException(400, f"Key must include: {', '.join(pk_cols)}")
        where_sql = " AND ".join(f"{c}=?" for c in pk_cols)
        try:
            cur = conn.execute(
                f"DELETE FROM {table} WHERE {where_sql}",
                [key[c] for c in pk_cols],
            )
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        if cur.rowcount == 0:
            raise HTTPException(404, "Row not found")
        entity_id = "|".join(str(key[c]) for c in pk_cols)
        _audit(conn, user["user_id"], "DELETE_MASTER", table, entity_id, {"key": key})
    return {"ok": True}
