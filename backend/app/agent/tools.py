from __future__ import annotations

import json
from functools import wraps
from typing import Any, Callable

from langsmith import traceable

from app.db import db_session, now_iso
from app.services import booking, chat, eta, scheduling
from app.tracing import configure_langsmith


def traced_tool(name: str) -> Callable:
    """LangSmith tool span — nests under the active agent parent run."""

    def decorator(fn: Callable) -> Callable:
        traced = traceable(name=name, run_type="tool", tags=["setuhaul", "tool"])(fn)

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            configure_langsmith()
            return traced(*args, **kwargs)

        return wrapper

    return decorator


@traced_tool("resolve_driver_context")
def tool_resolve_driver_context(driver_id: str) -> str:
    return json.dumps(booking.resolve_driver_context(driver_id))


@traced_tool("get_inbound_state")
def tool_get_inbound_state(facility_id: str | None = None, shipment_id: str | None = None) -> str:
    return json.dumps(booking.get_inbound_state(facility_id, shipment_id))


@traced_tool("check_appointment_feasibility")
def tool_check_feasibility(shipment_id: str) -> str:
    return json.dumps(booking.check_appointment_feasibility(shipment_id))


@traced_tool("find_feasible_slots")
def tool_find_feasible_slots(shipment_id: str, after_ts: str | None = None) -> str:
    slots = booking.find_feasible_slots(shipment_id, after_ts=after_ts)
    return json.dumps({"shipment_id": shipment_id, "options": slots, "count": len(slots)})


@traced_tool("record_exception_and_eta")
def tool_record_eta(
    shipment_id: str,
    driver_id: str,
    declared_eta_ts: str,
    confidence: str = "MEDIUM",
    delay_min: int | None = None,
    thread_id: str | None = None,
    earliest_acceptable_ts: str | None = None,
    latest_acceptable_ts: str | None = None,
) -> str:
    return json.dumps(
        eta.record_driver_eta(
            shipment_id,
            driver_id,
            declared_eta_ts,
            confidence,
            delay_min=delay_min,
            thread_id=thread_id,
            earliest_acceptable_ts=earliest_acceptable_ts,
            latest_acceptable_ts=latest_acceptable_ts,
        )
    )


@traced_tool("soft_hold_slot")
def tool_soft_hold(slot_id: str, shipment_id: str, thread_id: str, user_id: str | None = None) -> str:
    return json.dumps(booking.soft_hold_slot(slot_id, shipment_id, thread_id, user_id))


@traced_tool("confirm_driver_choice")
def tool_confirm_choice(shipment_id: str, slot_id: str) -> str:
    return json.dumps(booking.confirm_driver_choice(shipment_id, slot_id))


@traced_tool("run_facility_schedule")
def tool_run_schedule(facility_id: str, shipment_id: str | None = None) -> str:
    return json.dumps(scheduling.run_facility_schedule(facility_id, shipment_id))


@traced_tool("request_browser_location")
def tool_request_browser_location(thread_id: str) -> str:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO agent_pending_actions(pending_id, thread_id, action_type, payload_json, status, created_at, updated_at)
            VALUES (?, ?, 'REQUEST_BROWSER_LOCATION', '{}', 'WAITING', ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
              action_type='REQUEST_BROWSER_LOCATION', status='WAITING', updated_at=excluded.updated_at
            """,
            (f"PEND-{thread_id}", thread_id, now_iso(), now_iso()),
        )
    return json.dumps(
        {
            "client_action": "REQUEST_BROWSER_LOCATION",
            "thread_id": thread_id,
            "message": "Ask the driver to share a one-time browser location.",
        }
    )


@traced_tool("escalate_to_ops")
def tool_escalate(thread_id: str, reason: str) -> str:
    return json.dumps(chat.escalate_thread(thread_id, reason))


@traced_tool("rank_slots_with_eta_buffers")
def tool_rank_with_buffers(
    shipment_id: str, route_eta_ts: str | None = None, declared_eta_ts: str | None = None
) -> str:
    return json.dumps(eta.rank_slots_with_eta_buffers(shipment_id, route_eta_ts, declared_eta_ts))


TOOL_REGISTRY = {
    "resolve_driver_context": tool_resolve_driver_context,
    "get_inbound_state": tool_get_inbound_state,
    "check_appointment_feasibility": tool_check_feasibility,
    "find_feasible_slots": tool_find_feasible_slots,
    "record_exception_and_eta": tool_record_eta,
    "soft_hold_slot": tool_soft_hold,
    "confirm_driver_choice": tool_confirm_choice,
    "run_facility_schedule": tool_run_schedule,
    "request_browser_location": tool_request_browser_location,
    "escalate_to_ops": tool_escalate,
    "rank_slots_with_eta_buffers": tool_rank_with_buffers,
}


def validate_options_grounding(options: list[dict[str, Any]], allowed_slot_ids: set[str]) -> dict[str, Any]:
    invented = [o.get("slot_id") for o in options if o.get("slot_id") not in allowed_slot_ids]
    return {
        "invented_slot": 1 if invented else 0,
        "invented_ids": invented,
        "tool_grounding_score": 0.0 if invented else 1.0,
    }
