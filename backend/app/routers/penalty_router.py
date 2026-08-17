from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.auth import CurrentUser
from app.db import db_session, rows_to_dicts
from app.services import penalty as penalty_service

router = APIRouter(prefix="/penalty", tags=["penalty"])


@router.post("/requests")
def create_request(
    shipment_id: str,
    exception_id: str | None = None,
    penalty_type: str = "LATE_DELIVERY",
    amount: float = 0.0,
    reason: str = "",
    user: CurrentUser = None,
) -> dict[str, Any]:
    if user["role"] not in ("OPERATIONS", "ADMIN", "WAREHOUSE"):
        raise HTTPException(403, "Not allowed")
    if not reason:
        raise HTTPException(400, "Reason is required")
    return penalty_service.create_penalty_request(
        shipment_id, exception_id, penalty_type, amount, reason, user.get("username") or "system"
    )


@router.post("/requests/{penalty_request_id}/decide")
def decide_request(penalty_request_id: str, approve: bool, user: CurrentUser = None) -> dict[str, Any]:
    if user["role"] not in ("OPERATIONS", "ADMIN", "WAREHOUSE"):
        raise HTTPException(403, "Not allowed")
    return penalty_service.decide_penalty(penalty_request_id, approve, user.get("username") or "system")


@router.get("/requests")
def list_requests(
    facility_id: str | None = None,
    status: str | None = None,
    user: CurrentUser = None,
) -> dict[str, Any]:
    if user["role"] not in ("OPERATIONS", "ADMIN", "WAREHOUSE"):
        raise HTTPException(403, "Not allowed")
    rows = penalty_service.list_penalty_requests(facility_id, status)
    return {"rows": rows}
