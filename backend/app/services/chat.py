from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.db import db_session, now_iso, rows_to_dicts, row_to_dict
from app.services import metrics as metrics_service


def _message_timestamp() -> str:
    """Wall-clock stamp so chat bubbles show distinct send times (classroom_now is frozen)."""
    return datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds")


def list_threads(driver_id: str | None = None, status: str | None = None, facility_id: str | None = None) -> list[dict[str, Any]]:
    with db_session() as conn:
        sql = """
            SELECT
                t.*,
                s.destination_facility_id,
                s.priority_code,
                s.customer_name,
                d.driver_name,
                (
                    SELECT MAX(m.message_ts)
                    FROM chat_messages m
                    WHERE m.thread_id = t.thread_id
                ) AS last_message_ts,
                (
                    SELECT m.message_text
                    FROM chat_messages m
                    WHERE m.thread_id = t.thread_id
                    ORDER BY m.message_ts DESC, m.rowid DESC
                    LIMIT 1
                ) AS last_message_preview,
                (
                    SELECT COUNT(*)
                    FROM chat_messages m
                    WHERE m.thread_id = t.thread_id
                ) AS message_count
            FROM chat_threads t
            LEFT JOIN shipments s ON s.shipment_id = t.shipment_id
            JOIN drivers d ON d.driver_id = t.driver_id
            WHERE 1=1
        """
        params: list[Any] = []
        if driver_id:
            sql += " AND t.driver_id = ?"
            params.append(driver_id)
        if status:
            sql += " AND t.thread_status = ?"
            params.append(status)
        else:
            sql += " AND t.thread_status NOT IN ('CLOSED','RESOLVED')"
        if facility_id:
            sql += " AND s.destination_facility_id = ?"
            params.append(facility_id)
        sql += """
            ORDER BY
                COALESCE(
                    (SELECT MAX(m.message_ts) FROM chat_messages m WHERE m.thread_id = t.thread_id),
                    t.opened_at
                ) DESC,
                t.rowid DESC
        """
        return rows_to_dicts(conn.execute(sql, params).fetchall())


def get_thread(thread_id: str) -> dict[str, Any] | None:
    with db_session() as conn:
        return row_to_dict(conn.execute("SELECT * FROM chat_threads WHERE thread_id=?", (thread_id,)).fetchone())


def get_thread_messages(thread_id: str) -> list[dict[str, Any]]:
    with db_session() as conn:
        return rows_to_dicts(
            conn.execute(
                "SELECT * FROM chat_messages WHERE thread_id=? ORDER BY message_ts, rowid",
                (thread_id,),
            ).fetchall()
        )


def create_thread(driver_id: str, shipment_id: str | None = None, intent: str = "GENERAL_QUESTION") -> dict[str, Any]:
    """Always open a brand-new chat session (session id = thread_id)."""
    thread_id = f"THR-{uuid4().hex[:8].upper()}"
    ts = _message_timestamp()
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO chat_threads(thread_id, driver_id, shipment_id, opened_at, closed_at, thread_status, thread_intent)
            VALUES (?, ?, ?, ?, NULL, 'OPEN', ?)
            """,
            (thread_id, driver_id, shipment_id, ts, intent),
        )
        carrier_id = None
        facility_id = None
        if shipment_id:
            shipment = conn.execute(
                "SELECT destination_facility_id, carrier_id FROM shipments WHERE shipment_id=?",
                (shipment_id,),
            ).fetchone()
            if shipment:
                facility_id = shipment["destination_facility_id"]
                carrier_id = shipment["carrier_id"]
        metrics_service.ensure_case_metric(
            thread_id, shipment_id, driver_id, facility_id, carrier_id, conn=conn
        )
    return {
        "thread_id": thread_id,
        "driver_id": driver_id,
        "shipment_id": shipment_id,
        "opened_at": ts,
        "thread_status": "OPEN",
        "thread_intent": intent,
    }


def ensure_thread(driver_id: str, shipment_id: str | None, intent: str = "REPORT_DELAY") -> dict[str, Any]:
    with db_session() as conn:
        if shipment_id:
            existing = conn.execute(
                """
                SELECT * FROM chat_threads
                WHERE driver_id=? AND shipment_id=? AND thread_status NOT IN ('CLOSED','RESOLVED','ESCALATED')
                ORDER BY opened_at DESC LIMIT 1
                """,
                (driver_id, shipment_id),
            ).fetchone()
            if existing:
                return row_to_dict(existing)  # type: ignore[return-value]
    return create_thread(driver_id, shipment_id, intent=intent)


def is_delay_retry_candidate(message_text: str) -> bool:
    """True for delay-report text that messaging retries would repeat — not greetings/acks/actions."""
    t = (message_text or "").strip().lower()
    if len(t) < 10:
        return False
    # Never treat option selections, holds, bookings, confirmations as duplicate retry candidates
    if any(k in t for k in ("option", "take option", "hold", "book", "confirm", "select", "slot", "cancel", "yes", "no")):
        return False
    # Must look like a delay or ETA report
    delay_keys = ("late", "delay", "behind", "traffic", "breakdown", "stuck", "flat tire", "weather", "accident")
    return any(k in t for k in delay_keys)


def add_message(
    thread_id: str,
    sender_type: str,
    message_text: str,
    sender_reference: str | None = None,
    parsed_intent: str | None = None,
    extracted_eta_ts: str | None = None,
    requires_human_review: int = 0,
) -> dict[str, Any]:
    msg_id = f"MSG-{uuid4().hex[:8].upper()}"
    ts = _message_timestamp()
    is_duplicate = 0
    with db_session() as conn:
        if sender_type == "DRIVER" and is_delay_retry_candidate(message_text):
            prior = conn.execute(
                """
                SELECT m.chat_message_id, m.message_ts FROM chat_messages m
                WHERE m.thread_id = ?
                  AND m.sender_type = 'DRIVER'
                  AND m.message_text = ?
                  AND m.is_duplicate = 0
                ORDER BY m.message_ts DESC LIMIT 1
                """,
                (thread_id, message_text.strip()),
            ).fetchone()
            if prior and prior["message_ts"]:
                try:
                    p_dt = datetime.fromisoformat(str(prior["message_ts"]).replace("Z", "+00:00"))
                    c_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    if abs((c_dt - p_dt).total_seconds()) < 15:
                        is_duplicate = 1
                except Exception:
                    pass
        conn.execute(
            """
            INSERT INTO chat_messages(
                chat_message_id, thread_id, sender_type, sender_reference, message_text,
                message_ts, external_message_id, is_duplicate, parsed_intent, extracted_eta_ts, requires_human_review
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
            """,
            (
                msg_id,
                thread_id,
                sender_type,
                sender_reference,
                message_text,
                ts,
                is_duplicate,
                parsed_intent,
                extracted_eta_ts,
                requires_human_review,
            ),
        )
    return {
        "chat_message_id": msg_id,
        "thread_id": thread_id,
        "sender_type": sender_type,
        "message_text": message_text,
        "message_ts": ts,
        "is_duplicate": is_duplicate,
    }


def set_thread_status(thread_id: str, status: str) -> None:
    with db_session() as conn:
        closed = now_iso() if status in ("CLOSED", "RESOLVED") else None
        conn.execute(
            "UPDATE chat_threads SET thread_status=?, closed_at=COALESCE(?, closed_at) WHERE thread_id=?",
            (status, closed, thread_id),
        )


def escalate_thread(thread_id: str, reason: str) -> dict[str, Any]:
    set_thread_status(thread_id, "ESCALATED")
    metrics_service.mark_human_help(thread_id)
    msg = add_message(thread_id, "SYSTEM", f"Escalated to operations: {reason}", "system", "ESCALATE")
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO guardrail_events(event_id, thread_id, user_id, guardrail_name, action, detail, created_at)
            VALUES (?, ?, NULL, 'ESCALATION', 'ESCALATE', ?, ?)
            """,
            (f"GR-{uuid4().hex[:8].upper()}", thread_id, reason, now_iso()),
        )
    return {"ok": True, "thread_status": "ESCALATED", "message": msg}
