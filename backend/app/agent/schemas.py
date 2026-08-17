from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


Intent = Literal[
    "GENERAL",
    "GREETING",
    "DELAY",
    "EARLY_ARRIVAL",
    "BOOK_CHOICE",
    "LOCATION",
    "REEFER",
    "STATUS",
    "CANCELLED",
    "CLARIFY",
]

ClientAction = Literal["REQUEST_BROWSER_LOCATION"]


class SlotOption(BaseModel):
    """A dock slot that was returned by a tool in this turn (never invent)."""

    slot_id: str = Field(description="Exact slot_id from find_feasible_slots or rank_slots_with_eta_buffers")
    dock_code: str = Field(description="Dock code from the same tool result")
    slot_start_ts: str = Field(description="Slot start timestamp from the tool result")
    slot_end_ts: str = Field(description="Slot end timestamp from the tool result")
    arrival_buffer_min: float | None = Field(default=None, description="Buffer minutes if the tool provided it")
    requires_manual_approval: bool = False


class AgentTurnOutput(BaseModel):
    """Structured final answer the exception agent must produce each turn."""

    reply: str = Field(
        description=(
            "Driver-facing text only — never JSON. For shipment/appointment details use a "
            "markdown table with columns Field | Value. No invented docks, slots, or times."
        )
    )
    intent: Intent = Field(
        default="GENERAL",
        description="Best-fit intent for this driver turn",
    )
    shipment_id: str | None = Field(
        default=None,
        description="Shipment this turn is about, if known (e.g. SHP1006)",
    )
    options: list[SlotOption] = Field(
        default_factory=list,
        description="Only tool-verified alternate slots to show in the UI",
    )
    client_actions: list[ClientAction] = Field(
        default_factory=list,
        description="UI actions; use REQUEST_BROWSER_LOCATION only after calling request_browser_location",
    )
    need_clarification: bool = Field(
        default=False,
        description="True when missing shipment identity, ETA, or option choice",
    )
    escalate: bool = Field(
        default=False,
        description="True when ops must take over (no feasible slot, reefer gap, cancelled, after-hours)",
    )
    escalation_reason: str | None = Field(
        default=None,
        description="Short reason if escalate is true",
    )

    @field_validator("reply")
    @classmethod
    def reply_not_empty(cls, v: str) -> str:
        text = (v or "").strip()
        if not text:
            raise ValueError("reply must be non-empty")
        return text
