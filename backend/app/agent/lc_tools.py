from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agent import tools as tool_impl


_CLOCK = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")
_DEADLINE_CLOCK = re.compile(
    r"(?:(?<!not )before|by|until|till|no later than|latest)\s+(\d{1,2})[:.](\d{2})",
    re.I,
)
_EARLIEST_CLOCK = re.compile(
    r"(?:after|not before|earliest)\s+(\d{1,2})[:.](\d{2})",
    re.I,
)


def _clock_to_ts(hh: int, mm: int) -> str | None:
    if hh > 23 or mm > 59:
        return None
    return f"2026-08-04T{hh:02d}:{mm:02d}:00+05:30"


@dataclass
class TurnContext:
    """Mutable per-turn context shared by LLM tools and post-processors."""

    driver_id: str
    thread_id: str
    user_id: str | None = None
    shipment_id: str | None = None
    tools_used: list[str] = field(default_factory=list)
    allowed_slot_ids: set[str] = field(default_factory=set)
    last_options: list[dict[str, Any]] = field(default_factory=list)
    last_rank: dict[str, Any] | None = None
    hold: dict[str, Any] | None = None
    booking: dict[str, Any] | None = None
    feasibility: dict[str, Any] | None = None
    inbound_state: list[dict[str, Any]] | None = None


def _loads(raw: str) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _track_options(ctx: TurnContext, options: list[dict[str, Any]]) -> None:
    for o in options or []:
        sid = o.get("slot_id")
        if sid:
            ctx.allowed_slot_ids.add(sid)
    if options:
        ctx.last_options = list(options)


class ResolveDriverContextArgs(BaseModel):
    """No args — uses the session driver_id."""


class GetInboundStateArgs(BaseModel):
    shipment_id: str = Field(default="", description="Shipment id, e.g. SHP1006")
    facility_id: str = Field(default="", description="Optional facility filter")


class CheckFeasibilityArgs(BaseModel):
    shipment_id: str = Field(description="Shipment to check")


class FindSlotsArgs(BaseModel):
    shipment_id: str = Field(description="Shipment id, e.g. SHP1006")
    after_ts: str = Field(default="", description="Only slots at/after this ISO timestamp")


class RecordEtaArgs(BaseModel):
    shipment_id: str = Field(description="Shipment id")
    declared_eta_ts: str = Field(description="ISO timestamp, e.g. 2026-08-04T11:30:00+05:30")
    confidence: str = Field(default="MEDIUM")
    delay_min: int = Field(default=0, description="Reported delay in minutes if the driver gave a duration")
    earliest_acceptable_ts: str = Field(default="", description="Earliest acceptable timestamp")
    latest_acceptable_ts: str = Field(default="", description="Latest acceptable timestamp")


class SoftHoldArgs(BaseModel):
    slot_id: str
    shipment_id: str


class ConfirmChoiceArgs(BaseModel):
    shipment_id: str
    slot_id: str


class RankSlotsArgs(BaseModel):
    shipment_id: str = Field(description="Shipment id")
    declared_eta_ts: str = Field(default="", description="Driver declared ETA timestamp")
    route_eta_ts: str = Field(default="", description="Route calculated ETA timestamp")


class EscalateArgs(BaseModel):
    reason: str


class RequestLocationArgs(BaseModel):
    """No args — uses session thread_id."""


def _deny_if_foreign(ctx: TurnContext, shipment_id: str) -> str | None:
    """Return JSON error string when shipment is not owned by this driver."""
    from app.services import booking

    check = booking.assert_driver_owns_shipment(ctx.driver_id, shipment_id)
    if check.get("ok"):
        return None
    return json.dumps(check)


def build_langchain_tools(ctx: TurnContext) -> list[StructuredTool]:
    """Build LangChain tools closed over this turn's context."""

    def resolve_driver_context() -> str:
        raw = tool_impl.tool_resolve_driver_context(ctx.driver_id)
        ctx.tools_used.append("resolve_driver_context")
        data = _loads(raw)
        if not ctx.shipment_id:
            ships = data.get("active_shipments") or []
            if len(ships) == 1:
                ctx.shipment_id = ships[0].get("shipment_id")
        return raw

    def get_inbound_state(shipment_id: str = "", facility_id: str = "") -> str:
        sid = shipment_id.strip() if shipment_id else ""
        sid = sid or ctx.shipment_id
        if sid:
            denied = _deny_if_foreign(ctx, sid)
            if denied:
                return denied
        # Drivers only see their own inbound rows even without shipment_id
        from app.services import booking

        fac = facility_id.strip() if facility_id else None
        raw = json.dumps(
            booking.get_inbound_state(facility_id=fac, shipment_id=sid or None, driver_id=ctx.driver_id)
        )
        ctx.tools_used.append("get_inbound_state")
        rows = _loads(raw) or []
        if isinstance(rows, list):
            ctx.inbound_state = rows
            if sid:
                ctx.shipment_id = sid
        return raw

    def check_appointment_feasibility(shipment_id: str) -> str:
        denied = _deny_if_foreign(ctx, shipment_id)
        if denied:
            return denied
        raw = tool_impl.tool_check_feasibility(shipment_id)
        ctx.tools_used.append("check_appointment_feasibility")
        ctx.shipment_id = shipment_id
        payload = _loads(raw)
        ctx.feasibility = payload if isinstance(payload, dict) else None
        return raw

    def find_feasible_slots(shipment_id: str, after_ts: str = "") -> str:
        denied = _deny_if_foreign(ctx, shipment_id)
        if denied:
            return denied
        ts = after_ts.strip() if after_ts else None
        raw = tool_impl.tool_find_feasible_slots(shipment_id, after_ts=ts)
        ctx.tools_used.append("find_feasible_slots")
        ctx.shipment_id = shipment_id
        payload = _loads(raw) or {}
        _track_options(ctx, payload.get("options") or [])
        return raw

    def record_exception_and_eta(
        shipment_id: str,
        declared_eta_ts: str,
        confidence: str = "MEDIUM",
        delay_min: int = 0,
        earliest_acceptable_ts: str = "",
        latest_acceptable_ts: str = "",
    ) -> str:
        denied = _deny_if_foreign(ctx, shipment_id)
        if denied:
            return denied
        d_min = delay_min if delay_min > 0 else None
        e_ts = earliest_acceptable_ts.strip() if earliest_acceptable_ts else None
        l_ts = latest_acceptable_ts.strip() if latest_acceptable_ts else None
        raw = tool_impl.tool_record_eta(
            shipment_id,
            ctx.driver_id,
            declared_eta_ts,
            confidence,
            delay_min=d_min,
            thread_id=ctx.thread_id,
            earliest_acceptable_ts=e_ts,
            latest_acceptable_ts=l_ts,
        )
        ctx.tools_used.append("record_exception_and_eta")
        ctx.shipment_id = shipment_id
        return raw

    def _resolve_slot_id(slot_id: str, shipment_id: str) -> str:
        s = (slot_id or "").strip()
        m = re.search(r"(?:option\s*)?(\d+)", s, re.I)
        if m:
            idx = int(m.group(1)) - 1
            if ctx.last_options and 0 <= idx < len(ctx.last_options):
                resolved = ctx.last_options[idx].get("slot_id")
                if resolved:
                    return resolved
            from app.services import metrics as metrics_service
            displayed = metrics_service.get_displayed_slot_ids(ctx.thread_id)
            if 0 <= idx < len(displayed):
                return displayed[idx]
        from app.services import booking
        feasible = booking.find_feasible_slots(shipment_id, limit=20)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(feasible):
                return feasible[idx]["slot_id"]
        for f in feasible:
            if f["slot_id"] == s or (f.get("dock_code") and f["dock_code"] in s.upper()):
                return f["slot_id"]
        return s

    def soft_hold_slot(slot_id: str, shipment_id: str) -> str:
        denied = _deny_if_foreign(ctx, shipment_id)
        if denied:
            return denied
        real_slot_id = _resolve_slot_id(slot_id, shipment_id)
        raw = tool_impl.tool_soft_hold(real_slot_id, shipment_id, ctx.thread_id, ctx.user_id)
        ctx.tools_used.append("soft_hold_slot")
        ctx.shipment_id = shipment_id
        payload = _loads(raw)
        ctx.hold = payload if isinstance(payload, dict) else None
        return raw

    def confirm_driver_choice(shipment_id: str, slot_id: str) -> str:
        denied = _deny_if_foreign(ctx, shipment_id)
        if denied:
            return denied
        real_slot_id = _resolve_slot_id(slot_id, shipment_id)
        raw = tool_impl.tool_confirm_choice(shipment_id, real_slot_id)
        ctx.tools_used.append("confirm_driver_choice")
        ctx.shipment_id = shipment_id
        payload = _loads(raw)
        ctx.booking = payload if isinstance(payload, dict) else None
        return raw

    def rank_slots_with_eta_buffers(
        shipment_id: str,
        declared_eta_ts: str = "",
        route_eta_ts: str = "",
    ) -> str:
        denied = _deny_if_foreign(ctx, shipment_id)
        if denied:
            return denied
        d_ts = declared_eta_ts.strip() if declared_eta_ts else None
        r_ts = route_eta_ts.strip() if route_eta_ts else None
        raw = tool_impl.tool_rank_with_buffers(shipment_id, r_ts, d_ts)
        ctx.tools_used.append("rank_slots_with_eta_buffers")
        ctx.shipment_id = shipment_id
        payload = _loads(raw) or {}
        _track_options(ctx, payload.get("options") or [])
        ctx.last_rank = payload if isinstance(payload, dict) else None
        return raw

    def request_browser_location() -> str:
        raw = tool_impl.tool_request_browser_location(ctx.thread_id)
        ctx.tools_used.append("request_browser_location")
        return raw

    def escalate_to_ops(reason: str) -> str:
        raw = tool_impl.tool_escalate(ctx.thread_id, reason)
        ctx.tools_used.append("escalate_to_ops")
        return raw

    return [
        StructuredTool.from_function(
            name="resolve_driver_context",
            description="List this driver's active shipments and whether disambiguation is needed.",
            func=resolve_driver_context,
            args_schema=ResolveDriverContextArgs,
        ),
        StructuredTool.from_function(
            name="get_inbound_state",
            description=(
                "Get inbound appointment/dock state for THIS driver's shipment (or list). "
                "Returns JSON for you to read — paraphrase into a Field | Value markdown table, never echo JSON."
            ),
            func=get_inbound_state,
            args_schema=GetInboundStateArgs,
        ),
        StructuredTool.from_function(
            name="check_appointment_feasibility",
            description="Check whether the current appointment still works for the shipment ETA.",
            func=check_appointment_feasibility,
            args_schema=CheckFeasibilityArgs,
        ),
        StructuredTool.from_function(
            name="find_feasible_slots",
            description="Find tool-verified alternate dock slots for a shipment owned by this driver.",
            func=find_feasible_slots,
            args_schema=FindSlotsArgs,
        ),
        StructuredTool.from_function(
            name="record_exception_and_eta",
            description="Record a driver-declared ETA / delay exception for an owned shipment.",
            func=record_exception_and_eta,
            args_schema=RecordEtaArgs,
        ),
        StructuredTool.from_function(
            name="soft_hold_slot",
            description="Soft-hold a tool-verified slot (TTL). Soft-hold is NOT confirmation.",
            func=soft_hold_slot,
            args_schema=SoftHoldArgs,
        ),
        StructuredTool.from_function(
            name="confirm_driver_choice",
            description="Submit driver choice for warehouse PENDING_CONFIRMATION (not CONFIRMED).",
            func=confirm_driver_choice,
            args_schema=ConfirmChoiceArgs,
        ),
        StructuredTool.from_function(
            name="rank_slots_with_eta_buffers",
            description="Rank feasible slots using declared/route ETA buffers; preferred when offering options.",
            func=rank_slots_with_eta_buffers,
            args_schema=RankSlotsArgs,
        ),
        StructuredTool.from_function(
            name="request_browser_location",
            description="Ask the UI for a one-time browser location share to compare route ETA.",
            func=request_browser_location,
            args_schema=RequestLocationArgs,
        ),
        StructuredTool.from_function(
            name="escalate_to_ops",
            description="Escalate this thread to warehouse operations with a short reason.",
            func=escalate_to_ops,
            args_schema=EscalateArgs,
        ),
    ]


_CLOCK_12H = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
_CLOCK_24H = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")


def extract_eta_from_text(text: str) -> str | None:
    """Declared arrival clock time — handles both 24-hour HH:MM and 12-hour AM/PM."""
    t = text or ""
    deadline_spans = [m.span() for m in _DEADLINE_CLOCK.finditer(t)]
    earliest_spans = [m.span() for m in _EARLIEST_CLOCK.finditer(t)]
    skip = deadline_spans + earliest_spans

    # 1. Try 12-hour AM/PM (e.g. "2 am", "2:30 pm", "11 PM")
    for m in _CLOCK_12H.finditer(t):
        if any(m.start() >= a and m.end() <= b for a, b in skip):
            continue
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        ampm = m.group(3).lower()
        if ampm == "pm" and hh < 12:
            hh += 12
        elif ampm == "am" and hh == 12:
            hh = 0
        return _clock_to_ts(hh, mm)

    # 2. Try standard 24-hour HH:MM
    for m in _CLOCK_24H.finditer(t):
        if any(m.start() >= a and m.end() <= b for a, b in skip):
            continue
        return _clock_to_ts(int(m.group(1)), int(m.group(2)))
    return None


def extract_delay_min(text: str) -> int | None:
    t = text or ""
    m_hr = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:hours|hour|hrs|hr)\b", t, re.I)
    if m_hr:
        return int(float(m_hr.group(1)) * 60)
    m = re.search(r"\b(\d{1,3})\s*(?:min|mins|minutes|minute)\b", t, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"\blate by\s+(\d{1,3})\b", t, re.I)
    if m:
        return int(m.group(1))
    return None


def extract_constraint_ts(text: str, kind: str) -> str | None:
    """Parse 'leave by 13:30' / 'after 12:00' into a classroom-day timestamp."""
    if kind == "latest":
        m = _DEADLINE_CLOCK.search(text or "")
        return _clock_to_ts(int(m.group(1)), int(m.group(2))) if m else None
    if kind == "earliest":
        m = _EARLIEST_CLOCK.search(text or "")
        return _clock_to_ts(int(m.group(1)), int(m.group(2))) if m else None
    return None


def extract_shipment_id(text: str) -> str | None:
    m = re.search(r"\b(SHP\d+)\b", text or "", re.I)
    return m.group(1).upper() if m else None
