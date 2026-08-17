from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.auth import CurrentUser
from app.db import db_session, row_to_dict
from app.services import operational_messages as opmsg_service

router = APIRouter(prefix="/messages", tags=["operational-messages"])


class SendMessageBody(BaseModel):
    shipment_id: str
    appointment_id: str | None = None
    channel: str = "INTERNAL"
    sender_address: str
    recipient_address: str
    subject: str | None = None
    body: str


class ReplyBody(BaseModel):
    body: str


@router.post("/send")
def send_message(body: SendMessageBody, user: CurrentUser) -> dict[str, Any]:
    if user["role"] not in ("OPERATIONS", "ADMIN", "WAREHOUSE"):
        raise HTTPException(403, "Not allowed")
    return opmsg_service.send_message(
        body.shipment_id,
        body.appointment_id,
        body.channel,
        body.sender_address,
        body.recipient_address,
        body.subject,
        body.body,
    )


@router.get("/shipment/{shipment_id}")
def list_for_shipment(shipment_id: str, user: CurrentUser) -> dict[str, Any]:
    rows = opmsg_service.list_for_shipment(shipment_id)
    if user["role"] == "DRIVER":
        shipment = None
        with db_session() as conn:
            shipment = row_to_dict(
                conn.execute("SELECT carrier_id, driver_id FROM shipments WHERE shipment_id=?", (shipment_id,)).fetchone()
            )
        if not shipment:
            raise HTTPException(404, "Shipment not found")
        if user.get("carrier_id") and shipment.get("carrier_id") != user.get("carrier_id"):
            raise HTTPException(403, "Not your shipment")
    return {"messages": rows}


@router.post("/{operational_message_id}/reply")
def reply_to_message(operational_message_id: str, body: ReplyBody, user: CurrentUser) -> dict[str, Any]:
    if user["role"] not in ("OPERATIONS", "ADMIN", "WAREHOUSE"):
        raise HTTPException(403, "Not allowed")
    return opmsg_service.reply_to_message(operational_message_id, body.body)
