from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.db import db_session, now_iso, rows_to_dicts


def send_message(
    shipment_id: str,
    appointment_id: str | None,
    channel: str,
    sender_address: str,
    recipient_address: str,
    subject: str | None,
    body: str,
) -> dict[str, Any]:
    message_id = f"OM-{uuid4().hex[:8].upper()}"
    ts = now_iso()
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO operational_messages(
                operational_message_id, shipment_id, appointment_id, channel,
                sender_address, recipient_address, subject, message_body,
                sent_at, delivery_status, reply_to_message_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', NULL)
            """,
            (message_id, shipment_id, appointment_id, channel, sender_address, recipient_address, subject, body, ts),
        )
    return {
        "ok": True,
        "operational_message_id": message_id,
        "shipment_id": shipment_id,
        "channel": channel,
        "sent_at": ts,
        "delivery_status": "QUEUED",
    }


def list_for_shipment(shipment_id: str) -> list[dict[str, Any]]:
    with db_session() as conn:
        return rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM operational_messages
                WHERE shipment_id = ?
                ORDER BY sent_at ASC
                """,
                (shipment_id,),
            ).fetchall()
        )


def reply_to_message(operational_message_id: str, body: str) -> dict[str, Any]:
    reply_id = f"OM-{uuid4().hex[:8].upper()}"
    ts = now_iso()
    with db_session() as conn:
        parent = conn.execute(
            "SELECT * FROM operational_messages WHERE operational_message_id = ?",
            (operational_message_id,),
        ).fetchone()
        if not parent:
            return {"ok": False, "error": "Message not found"}
        conn.execute(
            """
            INSERT INTO operational_messages(
                operational_message_id, shipment_id, appointment_id, channel,
                sender_address, recipient_address, subject, message_body,
                sent_at, delivery_status, reply_to_message_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', ?)
            """,
            (
                reply_id,
                parent["shipment_id"],
                parent["appointment_id"],
                "INTERNAL",
                parent["recipient_address"],
                parent["sender_address"],
                f"RE: {parent['subject'] or ''}",
                body,
                ts,
                operational_message_id,
            ),
        )
    return {
        "ok": True,
        "operational_message_id": reply_id,
        "reply_to_message_id": operational_message_id,
        "sent_at": ts,
    }
