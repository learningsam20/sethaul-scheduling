from __future__ import annotations

import json
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.auth import CurrentUser
from app.db import db_session, now_iso, row_to_dict, rows_to_dicts
from app.services import booking, scheduling

router = APIRouter(prefix="/ops", tags=["ops"])


class DecideBody(BaseModel):
    approve: bool


class CancelBody(BaseModel):
    reason: str = "Cancelled by operations"


class DockEventBody(BaseModel):
    dock_id: str
    event_type: str
    reason: str
    event_start_ts: str | None = None
    event_end_ts: str | None = None


@router.get("/inbound")
def inbound(user: CurrentUser, facility_id: str | None = None) -> dict[str, Any]:
    if user["role"] == "WAREHOUSE":
        facility_id = user.get("facility_id")
    driver_id = user.get("driver_id") if user["role"] == "DRIVER" else None
    if user["role"] == "DRIVER" and not driver_id:
        return {"rows": []}
    return {"rows": booking.get_inbound_state(facility_id=facility_id, driver_id=driver_id)}


@router.get("/queue")
def queue(user: CurrentUser, facility_id: str) -> dict[str, Any]:
    if user["role"] == "WAREHOUSE" and user.get("facility_id") != facility_id:
        raise HTTPException(403, "Wrong facility")
    with db_session() as conn:
        rows = rows_to_dicts(
            conn.execute(
                "SELECT * FROM v_current_facility_queue WHERE facility_id=? ORDER BY queue_position",
                (facility_id,),
            ).fetchall()
        )
    return {"rows": rows}


@router.get("/pending")
def pending(user: CurrentUser, facility_id: str | None = None) -> dict[str, Any]:
    if user["role"] == "WAREHOUSE":
        facility_id = user.get("facility_id")
    return {"rows": booking.list_pending_confirmations(facility_id)}


@router.post("/pending/{appointment_id}/decide")
def decide(appointment_id: str, body: DecideBody, user: CurrentUser) -> dict[str, Any]:
    if user["role"] not in ("WAREHOUSE", "OPERATIONS", "ADMIN"):
        raise HTTPException(403, "Not allowed")
    return booking.warehouse_decide(appointment_id, body.approve, user.get("username"))


@router.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(appointment_id: str, body: CancelBody, user: CurrentUser) -> dict[str, Any]:
    if user["role"] not in ("WAREHOUSE", "OPERATIONS", "ADMIN"):
        raise HTTPException(403, "Not allowed")
    return booking.cancel_appointment(appointment_id, body.reason, user.get("username"))


@router.post("/docks/events")
def dock_event(body: DockEventBody, user: CurrentUser) -> dict[str, Any]:
    if user["role"] not in ("WAREHOUSE", "OPERATIONS", "ADMIN"):
        raise HTTPException(403, "Not allowed")
    return booking.record_dock_event(
        body.dock_id, body.event_type, body.reason, body.event_start_ts, body.event_end_ts
    )


@router.get("/facilities")
def facilities(user: CurrentUser) -> dict[str, Any]:
    with db_session() as conn:
        rows = rows_to_dicts(conn.execute("SELECT * FROM facilities ORDER BY facility_id").fetchall())
    return {"facilities": rows}


@router.post("/schedule/{facility_id}")
def schedule(facility_id: str, user: CurrentUser, shipment_id: str | None = None) -> dict[str, Any]:
    if user["role"] not in ("OPERATIONS", "ADMIN", "WAREHOUSE"):
        raise HTTPException(403, "Not allowed")
    return scheduling.run_facility_schedule(facility_id, shipment_id)


@router.get("/exceptions")
def exceptions(user: CurrentUser, facility_id: str | None = None) -> dict[str, Any]:
    with db_session() as conn:
        sql = """
            SELECT e.*, s.destination_facility_id, s.priority_code, s.customer_name
            FROM driver_exceptions e
            LEFT JOIN shipments s ON s.shipment_id = e.shipment_id
            WHERE e.exception_status IN ('OPEN','NEEDS_INFORMATION','SLOT_OPTIONS_SHARED','WAITING_CONFIRMATION','ESCALATED')
        """
        params: list[Any] = []
        if user["role"] == "DRIVER":
            sql += " AND e.driver_id = ?"
            params.append(user.get("driver_id"))
        elif user["role"] == "WAREHOUSE":
            sql += " AND s.destination_facility_id = ?"
            params.append(user.get("facility_id"))
        elif facility_id:
            sql += " AND s.destination_facility_id = ?"
            params.append(facility_id)
        sql += " ORDER BY e.reported_at DESC"
        rows = rows_to_dicts(conn.execute(sql, params).fetchall())
    return {"rows": rows}


@router.get("/allocation-policy")
def get_allocation_policy(facility_id: str, user: CurrentUser) -> dict[str, Any]:
    if user["role"] not in ("OPERATIONS", "ADMIN", "WAREHOUSE"):
        raise HTTPException(403, "Not allowed")
    with db_session() as conn:
        policy = row_to_dict(
            conn.execute(
                "SELECT * FROM allocation_policy WHERE facility_id = ? AND active_flag = 1",
                (facility_id,),
            ).fetchone()
        )
    if not policy:
        return {"policy": None}
    return {"policy": policy}


@router.put("/allocation-policy")
def update_allocation_policy(facility_id: str, body: dict[str, Any], user: CurrentUser) -> dict[str, Any]:
    if user["role"] not in ("OPERATIONS", "ADMIN"):
        raise HTTPException(403, "Not allowed")
    weights = body.get("priority_weights_json")
    protection = body.get("in_progress_protection", 1)
    objective = body.get("objective_summary")
    ts = now_iso()
    with db_session() as conn:
        existing = conn.execute(
            "SELECT policy_id FROM allocation_policy WHERE facility_id = ?", (facility_id,)
        ).fetchone()
        if existing:
            sets = ["priority_weights_json = ?", "in_progress_protection = ?", "updated_at = ?"]
            params: list[Any] = [weights, int(protection), ts]
            if objective is not None:
                sets.append("objective_summary = ?")
                params.append(objective)
            params.append(facility_id)
            conn.execute(f"UPDATE allocation_policy SET {', '.join(sets)} WHERE facility_id = ?", params)
        else:
            policy_id = f"POL-{uuid4().hex[:8].upper()}"
            conn.execute(
                """
                INSERT INTO allocation_policy(policy_id, facility_id, priority_weights_json, in_progress_protection, objective_summary, active_flag, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (policy_id, facility_id, weights, int(protection), objective or "", ts),
            )
    return {"ok": True}
