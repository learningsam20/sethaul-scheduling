from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent.graph import handle_driver_message
from app.auth import CurrentUser
from app.db import db_session, row_to_dict
from app.services import chat as chat_service
from app.services import metrics as metrics_service
from app.services import operational_messages as opmsg_service

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None
    shipment_id: str | None = None


class OpsMessageRequest(BaseModel):
    message: str


@router.get("/threads")
def threads(user: CurrentUser, facility_id: str | None = None) -> dict[str, Any]:
    if user["role"] == "DRIVER":
        return {"threads": chat_service.list_threads(driver_id=user.get("driver_id"))}
    if user["role"] == "WAREHOUSE":
        return {"threads": chat_service.list_threads(facility_id=user.get("facility_id") or facility_id)}
    if user["role"] == "CARRIER":
        # filter in python by joining shipments — simplified: all then filter
        all_threads = chat_service.list_threads(facility_id=facility_id)
        with db_session() as conn:
            ship_carriers = {
                r["shipment_id"]: r["carrier_id"]
                for r in conn.execute("SELECT shipment_id, carrier_id FROM shipments").fetchall()
            }
        return {
            "threads": [
                t
                for t in all_threads
                if ship_carriers.get(t.get("shipment_id")) == user.get("carrier_id")
            ]
        }
    return {"threads": chat_service.list_threads(facility_id=facility_id)}


@router.get("/threads/{thread_id}")
def thread_detail(thread_id: str, user: CurrentUser) -> dict[str, Any]:
    thread = chat_service.get_thread(thread_id)
    if not thread:
        raise HTTPException(404, "Thread not found")
    if user["role"] == "DRIVER" and thread.get("driver_id") != user.get("driver_id"):
        raise HTTPException(403, "Not your chat session")
    return {"thread": thread, "messages": chat_service.get_thread_messages(thread_id)}


@router.post("/threads")
def create_thread(
    user: CurrentUser,
    shipment_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Start a new chat session explicitly (session id = thread_id)."""
    if user["role"] not in ("DRIVER", "ADMIN") or not user.get("driver_id"):
        raise HTTPException(403, "Only drivers can start a chat session")
    if shipment_id:
        from app.services import booking

        check = booking.assert_driver_owns_shipment(user["driver_id"], shipment_id)
        if not check.get("ok"):
            raise HTTPException(403, check.get("error") or "Shipment not assigned to you")
    thread = chat_service.create_thread(user["driver_id"], shipment_id, intent="GENERAL_QUESTION")
    return {"thread": thread, "messages": []}


def _ops_reply(thread_id: str, message: str, user: dict[str, Any]) -> dict[str, Any]:
    with db_session() as conn:
        thread = row_to_dict(conn.execute("SELECT * FROM chat_threads WHERE thread_id=?", (thread_id,)).fetchone())
    if not thread:
        raise HTTPException(404, "Thread not found")
    
    clean_cmd = message.strip().lower()
    if clean_cmd in ("close", "/close", "resolve", "/resolve", "done", "/done"):
        chat_service.set_thread_status(thread_id, "RESOLVED")
        msg = chat_service.add_message(
            thread_id,
            "SYSTEM",
            f"{user['display_name']} marked this session as RESOLVED.",
            "system",
        )
        return {
            "ok": True,
            "reply": f"Session marked as RESOLVED by {user['display_name']}.",
            "message": msg,
            "messages": chat_service.get_thread_messages(thread_id),
            "thread_id": thread_id,
            "thread_status": "RESOLVED",
            "escalated": False,
            "options": [],
            "client_actions": [],
        }

    escalated_now = False
    if thread.get("thread_status") != "ESCALATED":
        chat_service.set_thread_status(thread_id, "ESCALATED")
        metrics_service.mark_human_help(thread_id)
        chat_service.add_message(
            thread_id,
            "SYSTEM",
            f"{user['display_name']} joined the conversation.",
            "system",
        )
        escalated_now = True
    msg = chat_service.add_message(thread_id, "OPERATIONS", message, user["user_id"])
    return {
        "ok": True,
        "reply": message,
        "message": msg,
        "messages": chat_service.get_thread_messages(thread_id),
        "thread_id": thread_id,
        "thread_status": "ESCALATED",
        "escalated": escalated_now,
        "options": [],
        "client_actions": [],
    }


def _trigger_operational_message(shipment_id: str, subject: str, body: str, appointment_id: str | None = None) -> None:
    with db_session() as conn:
        shipment = row_to_dict(
            conn.execute("SELECT carrier_id, destination_facility_id FROM shipments WHERE shipment_id = ?", (shipment_id,)).fetchone()
        )
        if not shipment:
            return
        facility_id = shipment["destination_facility_id"]
        carrier_id = shipment["carrier_id"]
        carrier = row_to_dict(
            conn.execute("SELECT carrier_name, contact_email, contact_phone FROM carriers WHERE carrier_id = ?", (carrier_id,)).fetchone()
        )
        if carrier and carrier.get("contact_email"):
            opmsg_service.send_message(
                shipment_id, appointment_id, "EMAIL", "agent@setuhaul.example",
                carrier["contact_email"], subject, body
            )
        if carrier and carrier.get("contact_phone"):
            opmsg_service.send_message(
                shipment_id, appointment_id, "SMS", "agent@setuhaul.example",
                carrier["contact_phone"], subject, body
            )


@router.post("/message")
def driver_message(body: ChatRequest, user: CurrentUser) -> dict[str, Any]:
    # Ops/Admin replies go through the ops path (never the driver agent)
    if user["role"] in ("OPERATIONS", "ADMIN") and not (
        user["role"] == "ADMIN" and user.get("driver_id") and not body.thread_id
    ):
        if not body.thread_id:
            raise HTTPException(400, "Open a live thread first, then send a reply to take it over.")
        return _ops_reply(body.thread_id, body.message, user)

    if user["role"] not in ("DRIVER", "ADMIN"):
        raise HTTPException(403, "Only drivers can use agent chat endpoint")
    if user["role"] == "ADMIN" and not user.get("driver_id"):
        raise HTTPException(400, "Open a live thread first, then send a reply to take it over.")
    result = handle_driver_message(user, body.message, body.thread_id, body.shipment_id)
    if result.get("error"):
        raise HTTPException(400, result["error"])
    shipment_id = result.get("shipment_id") or body.shipment_id
    if result.get("options_stale"):
        _trigger_operational_message(
            shipment_id,
            "Revised plan — options changed",
            "Shown options changed due to a slot cancellation or dock event. Please review the updated list.",
            result.get("booking", {}).get("appointment_id") if isinstance(result.get("booking"), dict) else None,
        )
    booking = result.get("booking") if isinstance(result.get("booking"), dict) else None
    if booking and booking.get("appointment_id"):
        _trigger_operational_message(
            shipment_id,
            "Appointment revised",
            f"Driver selected new slot. Appointment {booking.get('appointment_id')} is pending confirmation.",
            booking.get("appointment_id"),
        )
    return result


@router.post("/threads/{thread_id}/takeover")
def takeover(thread_id: str, user: CurrentUser) -> dict[str, Any]:
    """Explicit takeover — prefer ops-message, which escalates on first ops reply."""
    if user["role"] not in ("OPERATIONS", "ADMIN"):
        raise HTTPException(403, "Ops only")
    with db_session() as conn:
        thread = row_to_dict(conn.execute("SELECT * FROM chat_threads WHERE thread_id=?", (thread_id,)).fetchone())
    if not thread:
        raise HTTPException(404, "Thread not found")
    if thread.get("thread_status") != "ESCALATED":
        chat_service.set_thread_status(thread_id, "ESCALATED")
        metrics_service.mark_human_help(thread_id)
        msg = chat_service.add_message(
            thread_id,
            "OPERATIONS",
            f"{user['display_name']} took over this conversation.",
            user["user_id"],
        )
        return {"ok": True, "message": msg, "thread_status": "ESCALATED", "already": False}
    return {"ok": True, "thread_status": "ESCALATED", "already": True}


@router.post("/threads/{thread_id}/ops-message")
def ops_message(thread_id: str, body: OpsMessageRequest, user: CurrentUser) -> dict[str, Any]:
    if user["role"] not in ("OPERATIONS", "ADMIN"):
        raise HTTPException(403, "Ops only")
    return _ops_reply(thread_id, body.message, user)


@router.post("/threads/{thread_id}/resolve")
@router.post("/threads/{thread_id}/close")
def resolve_thread(thread_id: str, user: CurrentUser) -> dict[str, Any]:
    if user["role"] not in ("OPERATIONS", "ADMIN"):
        raise HTTPException(403, "Ops only")
    with db_session() as conn:
        thread = row_to_dict(conn.execute("SELECT * FROM chat_threads WHERE thread_id=?", (thread_id,)).fetchone())
    if not thread:
        raise HTTPException(404, "Thread not found")
    chat_service.set_thread_status(thread_id, "RESOLVED")
    msg = chat_service.add_message(
        thread_id,
        "SYSTEM",
        f"{user['display_name']} resolved and closed this conversation.",
        "system",
    )
    return {
        "ok": True,
        "thread_status": "RESOLVED",
        "message": msg,
        "messages": chat_service.get_thread_messages(thread_id),
    }
