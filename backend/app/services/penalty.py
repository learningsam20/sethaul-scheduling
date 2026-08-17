from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.db import db_session, now_iso, rows_to_dicts


def create_penalty_request(
    shipment_id: str,
    exception_id: str | None,
    penalty_type: str,
    amount: float,
    reason: str,
    requested_by: str,
) -> dict[str, Any]:
    penalty_request_id = f"PEN-{uuid4().hex[:8].upper()}"
    ts = now_iso()
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO penalty_requests(
                penalty_request_id, shipment_id, exception_id, requested_by, approved_by,
                status, penalty_type, amount, reason, created_at, decided_at
            ) VALUES (?, ?, ?, ?, NULL, 'PENDING', ?, ?, ?, ?, NULL)
            """,
            (penalty_request_id, shipment_id, exception_id, requested_by, penalty_type, amount, reason, ts),
        )
    return {
        "ok": True,
        "penalty_request_id": penalty_request_id,
        "shipment_id": shipment_id,
        "status": "PENDING",
        "penalty_type": penalty_type,
        "amount": amount,
        "reason": reason,
        "created_at": ts,
    }


def decide_penalty(penalty_request_id: str, approve: bool, decided_by: str) -> dict[str, Any]:
    ts = now_iso()
    status = "APPROVED" if approve else "REJECTED"
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM penalty_requests WHERE penalty_request_id = ?", (penalty_request_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "Penalty request not found"}
        if row["status"] != "PENDING":
            return {"ok": False, "error": f"Cannot decide status {row['status']}"}
        conn.execute(
            """
            UPDATE penalty_requests
            SET status = ?, approved_by = ?, decided_at = ?
            WHERE penalty_request_id = ?
            """,
            (status, decided_by, ts, penalty_request_id),
        )
    return {
        "ok": True,
        "penalty_request_id": penalty_request_id,
        "status": status,
        "decided_by": decided_by,
        "decided_at": ts,
    }


def list_penalty_requests(
    facility_id: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    with db_session() as conn:
        sql = """
            SELECT pr.*, s.destination_facility_id, s.customer_name, s.priority_code
            FROM penalty_requests pr
            LEFT JOIN shipments s ON s.shipment_id = pr.shipment_id
            WHERE 1=1
        """
        params: list[Any] = []
        if facility_id:
            sql += " AND s.destination_facility_id = ?"
            params.append(facility_id)
        if status:
            sql += " AND pr.status = ?"
            params.append(status)
        sql += " ORDER BY pr.created_at DESC"
        return rows_to_dicts(conn.execute(sql, params).fetchall())
