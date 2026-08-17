from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.agent.lc_tools import TurnContext, build_langchain_tools, extract_eta_from_text, extract_shipment_id, extract_delay_min, extract_constraint_ts
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.reply_format import format_inbound_details, humanize_reply, is_leaked_internal
from app.agent.schemas import AgentTurnOutput, SlotOption
from app.agent import tools as tool_impl
from app.config import get_settings
from app.db import db_session, now_iso, row_to_dict
from app.services import booking
from app.services import chat
from app.services import eta as eta_service
from app.services import metrics as metrics_service
from app.services import operational_messages as opmsg_service
from app.tracing import configure_langsmith

logger = logging.getLogger(__name__)


def _history_to_messages(history: list[dict[str, Any]], current_message: str) -> list[Any]:
    """Convert chat history to LangChain messages; ensure current user turn is last."""
    msgs: list[Any] = []
    for m in history or []:
        text = (m.get("message_text") or m.get("content") or "").strip()
        if not text or is_leaked_internal(text):
            continue
        sender = (m.get("sender_type") or m.get("sender") or "").upper()
        msg_obj = HumanMessage(content=text) if sender in ("DRIVER", "USER", "HUMAN") else AIMessage(content=text)
        if msgs and type(msgs[-1]) is type(msg_obj) and msgs[-1].content == msg_obj.content:
            continue
        msgs.append(msg_obj)
    # If history already ends with current driver message, keep it; else append.
    if not msgs or not isinstance(msgs[-1], HumanMessage) or msgs[-1].content != current_message:
        msgs.append(HumanMessage(content=current_message))
    return msgs[-6:]


def _is_lightweight(message: str) -> bool:
    """Greetings, FAQs, and policy/clarification questions — answer with one LLM call, no tools."""
    t = (message or "").strip().lower()
    if not t:
        return False
    # If it is a booking action or contains an ETA/delay, it is operational
    if any(k in t for k in ("take option", "book", "confirm reschedule", "hold slot", "cancel")):
        return False
    if extract_eta_from_text(message) or extract_delay_min(message):
        return False
    if _is_details_request(message):
        return False

    exact = {
        "hi",
        "hello",
        "hey",
        "hiya",
        "yo",
        "namaste",
        "good morning",
        "good afternoon",
        "good evening",
        "hi there",
        "hello there",
        "hey there",
        "help",
        "help?",
        "capabilities",
        "?",
        "thanks",
        "thank you",
    }
    if t in exact:
        return True
    indicators = (
        "what can you",
        "what do you",
        "how can you",
        "who are you",
        "what are you",
        "your capabilities",
        "what all can",
        "are these",
        "is this",
        "what is",
        "what does",
        "how does",
        "why is",
        "why are",
        "explain",
        "meaning of",
        "available slots or",
    )
    return any(k in t for k in indicators)


def _session_preamble(ctx: TurnContext, classroom_now: str, allowed_shipments: list[str]) -> str:
    ships = ", ".join(allowed_shipments) if allowed_shipments else "none"
    sid = ctx.shipment_id or (allowed_shipments[0] if len(allowed_shipments) == 1 else None)
    recent_loc = eta_service.get_recent_location_route(sid, ctx.driver_id, ctx.thread_id, max_age_seconds=300)
    loc_line = "recent_cached_location=none (no fresh location in last 5 minutes - prompt driver to share one-time location if they report a delay)\n"
    if recent_loc:
        r_hm = str(recent_loc.get("route_eta_ts"))[11:16] if recent_loc.get("route_eta_ts") else "n/a"
        with db_session() as conn:
            dec_row = conn.execute("SELECT effective_eta_ts FROM v_latest_eta WHERE shipment_id=?", (sid or "",)).fetchone()
            d_ts = dec_row["effective_eta_ts"] if dec_row else ""
            d_hm = str(d_ts)[11:16] if d_ts else "n/a"

        diff_min = 0.0
        if d_ts and recent_loc.get("route_eta_ts"):
            try:
                d_dt = datetime.fromisoformat(str(d_ts).replace("Z", "+00:00"))
                r_dt = datetime.fromisoformat(str(recent_loc["route_eta_ts"]).replace("Z", "+00:00"))
                d_norm = d_dt.astimezone(timezone.utc).replace(tzinfo=None) if d_dt.tzinfo else d_dt
                r_norm = r_dt.astimezone(timezone.utc).replace(tzinfo=None) if r_dt.tzinfo else r_dt
                diff_min = abs((d_norm - r_norm).total_seconds()) / 60.0
            except Exception:
                pass
        diff_h = round(diff_min / 60.0, 1) if diff_min >= 60 else f"{int(diff_min)} mins"
        diff_str = f"{diff_h} hours" if isinstance(diff_h, float) else str(diff_h)

        if diff_min > 30.0:
            reconcile_instruction = (
                f"2. SIGNIFICANT DIFFERENCE DETECTED (Declared ETA ~{d_hm} vs GPS Route ETA ~{r_hm}, Δ {diff_str}):\n"
                f"   - When driver reports a delay or revising time, YOU MUST ASK:\n"
                f"     'I have updated your declared ETA to ~{d_hm}. I am seeing a significant difference between your declared ETA (~{d_hm}) and your live GPS route ETA (~{r_hm}, difference of ~{diff_str}). Would you like to schedule based on your GPS location ETA (~{r_hm})? (Reply yes for location ETA, or no to use your declared ETA).'\n"
                "   - DO NOT output slots yet in this turn. Wait for driver response.\n"
            )
        else:
            reconcile_instruction = (
                f"2. ETAs ALIGNED (Declared ETA ~{d_hm} vs GPS Route ETA ~{r_hm}, Δ {diff_str}):\n"
                f"   - State: 'Using your recent location snapshot (Route ETA ~{r_hm}).'\n"
                f"   - Call rank_slots_with_eta_buffers(shipment_id, route_eta_ts='{recent_loc['route_eta_ts']}') and present the slots.\n"
            )

        loc_line = (
            f"recent_cached_location=AVAILABLE (shared {recent_loc['age_minutes']}m ago, "
            f"route_eta_ts='{recent_loc['route_eta_ts']}' [~{r_hm}], declared_eta_ts='{d_ts}' [~{d_hm}], diff={diff_str})\n"
            "LOCATION RULES:\n"
            "1. Location is ALREADY active. NEVER call request_browser_location or ask the driver to share location again.\n"
            + reconcile_instruction
            + "3. If the driver answers the discrepancy question:\n"
            f"   - If driver says 'no' / 'use declared' / 'no location': Call rank_slots_with_eta_buffers(shipment_id, declared_eta_ts='{d_ts}') and present the slots.\n"
            f"   - If driver says 'yes' / 'use location' / 'location': Call rank_slots_with_eta_buffers(shipment_id, route_eta_ts='{recent_loc['route_eta_ts']}') and present the slots.\n"
        )
    return (
        "[Session context]\n"
        f"thread_id={ctx.thread_id}\n"
        f"driver_id={ctx.driver_id}\n"
        f"known_shipment_id={sid or 'none'}\n"
        f"your_active_shipments={ships}\n"
        f"classroom_clock={classroom_now}\n"
        + loc_line
        + "SECURITY: Only act on shipments in your_active_shipments. "
        "If the driver names another id, refuse and list their shipments.\n"
        "Prefer the shortest tool path. Then return AgentTurnOutput."
    )


def _ground_options(raw_options: list[SlotOption], ctx: TurnContext) -> list[dict[str, Any]]:
    grounded: list[dict[str, Any]] = []
    by_id = {o.get("slot_id"): o for o in (ctx.last_options or []) if o.get("slot_id")}
    for opt in raw_options or []:
        sid = opt.slot_id
        if sid not in ctx.allowed_slot_ids:
            continue
        base = dict(by_id.get(sid) or {})
        grounded.append(
            {
                "slot_id": sid,
                "dock_code": opt.dock_code or base.get("dock_code"),
                "slot_start_ts": opt.slot_start_ts or base.get("slot_start_ts"),
                "slot_end_ts": opt.slot_end_ts or base.get("slot_end_ts"),
                "arrival_buffer_min": opt.arrival_buffer_min
                if opt.arrival_buffer_min is not None
                else base.get("arrival_buffer_min"),
                "requires_manual_approval": opt.requires_manual_approval
                or bool(base.get("requires_manual_approval")),
            }
        )
    return grounded


def _fallback_turn(ctx: TurnContext, message: str) -> AgentTurnOutput:
    """Deterministic fallback when LLM is unavailable."""
    lower = (message or "").lower().strip()
    if lower in {"hi", "hello", "hey", "hiya", "namaste"} or lower.startswith("good "):
        return AgentTurnOutput(
            reply="Hi — I'm SetuHaul's dock assistant. Tell me if you're delayed, early, need options, or want status.",
            intent="GREETING",
            shipment_id=ctx.shipment_id,
        )
    # Minimal operational path: resolve + feasibility
    raw = tool_impl.tool_resolve_driver_context(ctx.driver_id)
    ctx.tools_used.append("resolve_driver_context")
    import json

    data = json.loads(raw)
    ships = data.get("active_shipments") or []
    sid = ctx.shipment_id or extract_shipment_id(message)
    if not sid and len(ships) == 1:
        sid = ships[0]["shipment_id"]
    if not sid and len(ships) > 1:
        lines = [f"{s['shipment_id']} → {s.get('destination_facility_id')}" for s in ships]
        return AgentTurnOutput(
            reply="You have multiple active shipments. Which one is this about?\n" + "\n".join(lines),
            intent="CLARIFY",
            need_clarification=True,
        )
    if not sid:
        return AgentTurnOutput(
            reply="I could not find an active shipment. Operations can help if this is unexpected.",
            intent="CLARIFY",
            need_clarification=True,
        )
    ctx.shipment_id = sid
    if _is_details_request(message):
        rows = booking.get_inbound_state(shipment_id=sid, driver_id=ctx.driver_id)
        ctx.tools_used.append("get_inbound_state")
        ctx.inbound_state = rows
        return AgentTurnOutput(
            reply=format_inbound_details(rows, sid),
            intent="STATUS",
            shipment_id=sid,
        )

    # Option selection path (e.g. "2", "take option 1", "option 2", "choose 1", "#3", "book 2")
    opt_match = re.search(r"^\s*#?(\d+)\s*$|\b(?:take\s+)?opt(?:ion)?\s*#?\s*(\d+)\b|\b(?:take|choose|book|select)\s*#?\s*(\d+)\b", lower)
    if opt_match:
        idx_str = opt_match.group(1) or opt_match.group(2) or opt_match.group(3)
        choice_idx = int(idx_str) - 1

        # Check if the driver already has an active CONFIRMED appointment
        with db_session() as conn:
            current_confirmed = conn.execute(
                """
                SELECT a.*, sl.slot_start_ts, sl.slot_end_ts, d.dock_code
                FROM appointments a
                JOIN appointment_slots sl ON sl.slot_id = a.slot_id
                JOIN docks d ON d.dock_id = sl.dock_id
                WHERE a.shipment_id = ? AND a.is_current = 1 AND a.appointment_status = 'CONFIRMED'
                """,
                (sid,),
            ).fetchone()

        is_explicit_reschedule = any(k in lower for k in ("confirm reschedule", "reschedule", "replace", "cancel current", "confirm change"))
        if current_confirmed and not is_explicit_reschedule:
            dock = current_confirmed["dock_code"]
            start = str(current_confirmed["slot_start_ts"])[11:16]
            end = str(current_confirmed["slot_end_ts"])[11:16]
            return AgentTurnOutput(
                reply=(
                    f"You already have a CONFIRMED appointment at Dock {dock} ({start}–{end}). "
                    f"Selecting a new slot will cancel your current confirmed appointment. "
                    f"Say 'confirm reschedule to option {choice_idx + 1}' if you want to replace it, "
                    f"or keep your current appointment."
                ),
                intent="CLARIFY",
                shipment_id=sid,
                need_clarification=True,
            )

        ranked_raw = tool_impl.tool_rank_with_buffers(sid)
        ranked = json.loads(ranked_raw) if ranked_raw else {}
        options = ranked.get("options") or []
        if 0 <= choice_idx < len(options):
            chosen = options[choice_idx]
            slot_id = chosen["slot_id"]
            ctx.allowed_slot_ids.add(slot_id)
            hold_res = json.loads(tool_impl.tool_soft_hold(slot_id, sid, ctx.thread_id, ctx.user_id))
            ctx.tools_used.append("soft_hold_slot")
            ctx.hold = hold_res
            book_res = json.loads(tool_impl.tool_confirm_choice(sid, slot_id))
            ctx.tools_used.append("confirm_driver_choice")
            ctx.booking = book_res
            return AgentTurnOutput(
                reply=(
                    f"Selected Option {choice_idx + 1}: Dock {chosen.get('dock_code', '')} "
                    f"({str(chosen.get('slot_start_ts'))[11:16]}–{str(chosen.get('slot_end_ts'))[11:16]}) "
                    f"[{slot_id}]. Soft-held and submitted to warehouse as PENDING_CONFIRMATION."
                ),
                intent="BOOK_CHOICE",
                shipment_id=sid,
                options=[
                    SlotOption(
                        slot_id=chosen["slot_id"],
                        dock_code=chosen.get("dock_code", ""),
                        slot_start_ts=chosen.get("slot_start_ts", ""),
                        slot_end_ts=chosen.get("slot_end_ts", ""),
                        arrival_buffer_min=chosen.get("arrival_buffer_min"),
                        requires_manual_approval=bool(chosen.get("requires_manual_approval")),
                    )
                ],
            )

    eta = extract_eta_from_text(message)
    latest = extract_constraint_ts(message, "latest")
    earliest = extract_constraint_ts(message, "earliest")
    if eta:
        tool_impl.tool_record_eta(
            sid,
            ctx.driver_id,
            eta,
            delay_min=extract_delay_min(message),
            thread_id=ctx.thread_id,
            earliest_acceptable_ts=earliest,
            latest_acceptable_ts=latest,
        )
        ctx.tools_used.append("record_exception_and_eta")
    elif latest or earliest:
        booking.persist_exception_constraints(
            sid,
            ctx.driver_id,
            ctx.thread_id,
            declared_eta_ts=None,
            earliest_acceptable_ts=earliest,
            latest_acceptable_ts=latest,
            exception_type="DELAY",
            description="Driver time window from chat",
        )
        ctx.tools_used.append("record_exception_and_eta")
    feas = json.loads(tool_impl.tool_check_feasibility(sid))
    ctx.tools_used.append("check_appointment_feasibility")
    ctx.feasibility = feas
    ranked = json.loads(tool_impl.tool_rank_with_buffers(sid, declared_eta_ts=eta))
    ctx.tools_used.append("rank_slots_with_eta_buffers")
    ctx.last_rank = ranked
    options = ranked.get("options") or []
    for o in options:
        if o.get("slot_id"):
            ctx.allowed_slot_ids.add(o["slot_id"])
    ctx.last_options = options
    st = feas.get("state") or {}
    if latest and st.get("slot_end_ts") and st["slot_end_ts"] > latest:
        feas = dict(feas)
        feas["feasible"] = False
    if not options and not feas.get("feasible"):
        reason = f"No feasible slot finishing by {latest[11:16]}" if latest else "No feasible compatible slot"
        tool_impl.tool_escalate(ctx.thread_id, reason)
        ctx.tools_used.append("escalate_to_ops")
        return AgentTurnOutput(
            reply=("I could not find a compatible slot that finishes by "
                   f"{latest[11:16]}. Escalating to operations." if latest
                   else "I could not find a feasible compatible slot. Escalating to operations."),
            intent="DELAY",
            shipment_id=sid,
            escalate=True,
            escalation_reason=reason,
        )
    if feas.get("feasible") and not options:
        extra = f" It finishes before {latest[11:16]}." if latest else " Tell me if your ETA changed."
        return AgentTurnOutput(
            reply=(
                f"Your current appointment still looks feasible "
                f"({st.get('planned_dock_code')} "
                f"{str(st.get('slot_start_ts'))[11:16]}–{str(st.get('slot_end_ts'))[11:16]})."
                + extra
            ),
            intent="STATUS",
            shipment_id=sid,
        )
    lines = []
    slot_models: list[SlotOption] = []
    for i, o in enumerate(options[:5], 1):
        lines.append(
            f"{i}. {o['dock_code']} {o['slot_start_ts'][11:16]}–{o['slot_end_ts'][11:16]} [{o['slot_id']}]"
        )
        slot_models.append(
            SlotOption(
                slot_id=o["slot_id"],
                dock_code=o["dock_code"],
                slot_start_ts=o["slot_start_ts"],
                slot_end_ts=o["slot_end_ts"],
                arrival_buffer_min=o.get("arrival_buffer_min"),
                requires_manual_approval=bool(o.get("requires_manual_approval")),
            )
        )
    lead = "Current appointment may need a change. Tool-verified options (shown ≠ held ≠ confirmed):"
    if latest:
        lead = f"Slots that finish by {latest[11:16]} (shown ≠ held ≠ confirmed):"
    return AgentTurnOutput(
        reply=lead + "\n" + "\n".join(lines) + "\nSay 'take option 1' to soft-hold (still needs confirmation).",
        intent="DELAY",
        shipment_id=sid,
        options=slot_models,
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            pass
    return None


def _run_llm_lightweight(
    ctx: TurnContext,
    message: str,
    allowed_shipments: list[str] | None = None,
) -> AgentTurnOutput:
    """Single LLM call for greetings, FAQs, and domain clarification questions (no tool loop)."""
    settings = get_settings()
    llm = ChatOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        model=settings.openrouter_model,
        temperature=0.2,
        timeout=35,
        max_tokens=400,
    )
    preamble = _session_preamble(ctx, settings.classroom_now, allowed_shipments or [])
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"{preamble}\n\n"
        "This is an FAQ, greeting, or general question from the driver. "
        "Answer naturally, directly, and concisely in plain text. "
        "Knowledge: "
        "- Options shown in chat are only available, compatible dock slots matching the shipment requirements (occupied/maintenance slots are excluded). "
        "- Soft-hold temporarily reserves a slot while waiting for warehouse confirmation. "
        "- Keep replies short and direct (1-3 sentences). "
        "Respond with a JSON object with keys: reply, intent (GREETING or GENERAL), shipment_id.\n\n"
        f"Driver message: {message}"
    )
    try:
        structured_llm = llm.with_structured_output(AgentTurnOutput)
        result = structured_llm.invoke(prompt)
        if isinstance(result, AgentTurnOutput):
            return result
        if isinstance(result, dict):
            return AgentTurnOutput.model_validate(result)
    except Exception as err:
        logger.info("Structured output parsing failed, falling back to raw LLM extraction: %s", err)

    raw = llm.invoke(prompt)
    content = raw.content if hasattr(raw, "content") else str(raw)
    if isinstance(content, list):
        content = " ".join(str(c) for c in content)
    extracted = _extract_json_object(str(content))
    if extracted and isinstance(extracted, dict) and "reply" in extracted:
        try:
            return AgentTurnOutput.model_validate(extracted)
        except Exception:
            pass

    clean_text = str(content)
    clean_text = re.sub(r"User Safety:[^\n]*\n?", "", clean_text, flags=re.IGNORECASE).strip()
    return AgentTurnOutput(
        reply=clean_text or "Hello! How can I help you today with your shipment or dock appointment?",
        intent="GREETING" if any(g in message.lower() for g in ("hi", "hello", "hey", "morning")) else "GENERAL",
        shipment_id=ctx.shipment_id,
    )


def _run_llm_agent(
    ctx: TurnContext,
    message: str,
    history: list[dict[str, Any]],
    allowed_shipments: list[str],
) -> AgentTurnOutput:
    settings = get_settings()
    llm = ChatOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        model=settings.openrouter_model,
        temperature=0.1,
        timeout=55,
        max_tokens=1500,
    )
    tools = build_langchain_tools(ctx)
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT + "\n\n" + _session_preamble(ctx, settings.classroom_now, allowed_shipments),
        name="setuhaul_exception_agent",
    )
    msgs = _history_to_messages(history, message)
    result = agent.invoke(
        {"messages": msgs},
        config={
            "run_name": "setuhaul_exception_agent",
            "tags": ["setuhaul", "langgraph", "agent", "tools"],
            "metadata": {
                "thread_id": ctx.thread_id,
                "driver_id": ctx.driver_id,
                "shipment_id": ctx.shipment_id,
            },
            "recursion_limit": 18,
        },
    )
    for m in reversed(result.get("messages") or []):
        if not isinstance(m, AIMessage):
            continue
        content = getattr(m, "content", None)
        if isinstance(content, list):
            content = " ".join(str(c) for c in content)
        if isinstance(content, str) and content.strip() and not getattr(m, "tool_calls", None):
            raw_text = content.strip()
            # If the model emitted structured JSON, parse it
            extracted = _extract_json_object(raw_text)
            if extracted and isinstance(extracted, dict) and "reply" in extracted:
                try:
                    return AgentTurnOutput.model_validate(extracted)
                except Exception:
                    pass
            clean = re.sub(r"User Safety:[^\n]*\n?", "", raw_text, flags=re.IGNORECASE).strip()
            if is_leaked_internal(clean):
                continue
            opts: list[SlotOption] = []
            for o in ctx.last_options or []:
                if isinstance(o, dict) and o.get("slot_id"):
                    try:
                        opts.append(
                            SlotOption(
                                slot_id=o["slot_id"],
                                dock_code=o.get("dock_code", ""),
                                slot_start_ts=o.get("slot_start_ts", ""),
                                slot_end_ts=o.get("slot_end_ts", ""),
                                arrival_buffer_min=o.get("arrival_buffer_min"),
                                requires_manual_approval=bool(o.get("requires_manual_approval")),
                            )
                        )
                    except Exception:
                        pass
            return AgentTurnOutput(
                reply=clean,
                intent="DELAY" if any(k in clean.lower() for k in ("delay", "late", "eta", "slot", "dock")) else "GENERAL",
                shipment_id=ctx.shipment_id,
                options=opts,
            )
    raise RuntimeError("Agent did not return a valid assistant message")


def _is_details_request(message: str) -> bool:
    lower = (message or "").lower()
    if any(k in lower for k in ("late", "delay", "running behind", "traffic", "miss the", "early")):
        return False
    return any(
        k in lower
        for k in (
            "detail",
            "get info",
            "status",
            "shipment info",
            "inbound state",
            "which shipment",
            "my shipment",
            "what shipment",
            "current shipment",
            "what load",
            "my load",
            "order info",
        )
    )


def _sanitize_reply(text: str) -> str:
    """Strip leaked JSON and turn tool dumps into markdown tables."""
    return humanize_reply(text)


def _nudge_intent(intent: str, message: str) -> str:
    lower = (message or "").lower()
    if intent in ("GENERAL", "GREETING") and any(
        k in lower for k in ("late", "delay", "running behind", "eta", "traffic", "miss")
    ):
        return "DELAY"
    if intent in ("GENERAL", "GREETING") and any(
        k in lower for k in ("what can you", "what do you", "capabilities", "how can you")
    ):
        return "GENERAL"
    if intent in ("GENERAL", "GREETING") and _is_details_request(message):
        return "STATUS"
    return intent


def _apply_stale_options(
    thread_id: str,
    shipment_id: str | None,
    options: list[dict[str, Any]],
    reply: str,
    stale: bool | None = None,
) -> tuple[list[dict[str, Any]], str, bool]:
    """Drop cancelled/blocked slots from a prior list and warn the driver with specifics."""
    if stale is None:
        stale = metrics_service.options_are_stale(thread_id)
    if not stale:
        return options, reply, False
    if options and shipment_id:
        live = {s["slot_id"] for s in booking.find_feasible_slots(shipment_id, limit=30)}
        removed = [o for o in options if o.get("slot_id") not in live]
        options = [o for o in options if o.get("slot_id") in live]
        specific = []
        with db_session() as conn:
            for o in removed:
                slot_id = o.get("slot_id")
                dock_id = None
                slot = conn.execute(
                    "SELECT dock_id FROM appointment_slots WHERE slot_id = ?", (slot_id,)
                ).fetchone()
                if slot:
                    dock_id = slot["dock_id"]
                reason = "no longer available"
                if dock_id:
                    event = conn.execute(
                        """
                        SELECT reason, event_type FROM dock_status_events
                        WHERE dock_id = ? AND event_start_ts <= ?
                          AND (event_end_ts IS NULL OR event_end_ts > ?)
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (dock_id, now_iso(), now_iso()),
                    ).fetchone()
                    if event:
                        reason = f"DOCK blocked: {event['event_type']} — {event['reason']}"
                specific.append(f"{slot_id} is no longer available because {reason}")
        if specific:
            stale_msg = "Stale options removed: " + "; ".join(specific) + ". Use only the updated list."
        else:
            stale_msg = metrics_service.STALE_OPTIONS_WARNING
        if stale_msg not in (reply or ""):
            reply = stale_msg + ("\n\n" + reply if reply else "")
        return options, reply, True
    warning = metrics_service.STALE_OPTIONS_WARNING
    if warning not in (reply or ""):
        reply = warning + ("\n\n" + reply if reply else "")
    return options, reply, True


def run_agent_turn(
    user: dict[str, Any],
    thread: dict[str, Any],
    message: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    configure_langsmith()
    settings = get_settings()
    ctx = TurnContext(
        driver_id=user.get("driver_id") or thread["driver_id"],
        thread_id=thread["thread_id"],
        user_id=user.get("user_id"),
        shipment_id=thread.get("shipment_id"),
    )

    # Prefetch this driver's shipments — ownership gate for the whole turn
    driver_ctx = booking.resolve_driver_context(ctx.driver_id)
    allowed = [s["shipment_id"] for s in (driver_ctx.get("active_shipments") or []) if s.get("shipment_id")]
    allowed_set = set(allowed)

    # Thread-bound shipment must still belong to this driver
    if ctx.shipment_id and ctx.shipment_id not in allowed_set:
        check = booking.assert_driver_owns_shipment(ctx.driver_id, ctx.shipment_id)
        if not check.get("ok"):
            ctx.shipment_id = None

    mentioned = extract_shipment_id(message)
    ownership_reject: AgentTurnOutput | None = None
    if mentioned:
        if mentioned not in allowed_set:
            check = booking.assert_driver_owns_shipment(ctx.driver_id, mentioned)
            ships_line = ", ".join(allowed) if allowed else "none on file"
            err = (check.get("error") or f"Shipment {mentioned} is not assigned to you.").rstrip(".")
            ownership_reject = AgentTurnOutput(
                reply=f"{err}. Your active shipments: {ships_line}.",
                intent="CLARIFY",
                shipment_id=ctx.shipment_id,
                need_clarification=True,
            )
        elif not ctx.shipment_id:
            ctx.shipment_id = mentioned

    if not ctx.shipment_id and len(allowed) == 1:
        ctx.shipment_id = allowed[0]

    delay_m = extract_delay_min(message)
    clock_ts = extract_eta_from_text(message)
    if ctx.shipment_id and (delay_m is not None or clock_ts is not None):
        try:
            eta_service.record_driver_eta(
                ctx.shipment_id,
                ctx.driver_id,
                clock_ts or "",
                delay_min=delay_m,
                thread_id=ctx.thread_id,
            )
            if "record_exception_and_eta" not in ctx.tools_used:
                ctx.tools_used.append("record_exception_and_eta")
        except Exception as e:
            logger.warning("Auto-recording ETA exception failed: %s", e)

        recent_loc = eta_service.get_recent_location_route(ctx.shipment_id, ctx.driver_id, ctx.thread_id, max_age_seconds=300)
        if recent_loc and recent_loc.get("route_eta_ts"):
            with db_session() as conn:
                dec_row = conn.execute("SELECT effective_eta_ts FROM v_latest_eta WHERE shipment_id=?", (ctx.shipment_id,)).fetchone()
                d_ts = dec_row["effective_eta_ts"] if dec_row else ""
            diff_min = 0.0
            if d_ts and recent_loc.get("route_eta_ts"):
                try:
                    d_dt = datetime.fromisoformat(str(d_ts).replace("Z", "+00:00"))
                    r_dt = datetime.fromisoformat(str(recent_loc["route_eta_ts"]).replace("Z", "+00:00"))
                    d_norm = d_dt.astimezone(timezone.utc).replace(tzinfo=None) if d_dt.tzinfo else d_dt
                    r_norm = r_dt.astimezone(timezone.utc).replace(tzinfo=None) if r_dt.tzinfo else r_dt
                    diff_min = abs((d_norm - r_norm).total_seconds()) / 60.0
                except Exception:
                    pass
            d_hm = str(d_ts)[11:16] if d_ts else "n/a"
            r_hm = str(recent_loc["route_eta_ts"])[11:16]
            diff_h = round(diff_min / 60.0, 1) if diff_min >= 60 else f"{int(diff_min)} mins"
            diff_str = f"{diff_h} hours" if isinstance(diff_h, float) else str(diff_h)
            if diff_min > 30.0:
                reply = (
                    f"I've recorded your declared delay (updated ETA: ~{d_hm}).\n\n"
                    f"I'm seeing a significant difference between your declared ETA (~{d_hm}) and your live GPS route ETA (~{r_hm}, difference of ~{diff_str}).\n\n"
                    f"Would you like to schedule based on your GPS location ETA (~{r_hm})? (Reply **yes** for location ETA, or **no** to use your declared ETA)."
                )
                return {
                    "reply": reply,
                    "options": [],
                    "options_stale": False,
                    "client_actions": [],
                    "thread_id": ctx.thread_id,
                    "shipment_id": ctx.shipment_id,
                    "tools_used": ["record_exception_and_eta"],
                    "intent": "DELAY",
                    "structured": {"reply": reply, "intent": "DELAY", "options": [], "client_actions": []},
                    "trace": {"agent": "setuhaul_exception_agent", "framework": "langgraph", "mode": "discrepancy_gate", "tools_used": ["record_exception_and_eta"]},
                }

    llm_ok = False
    mode = "fallback"
    try:
        if ownership_reject is not None:
            out = ownership_reject
            mode = "ownership_guard"
        elif settings.openrouter_api_key:
            out = _run_llm_agent(ctx, message, history or [], allowed)
            llm_ok = True
            mode = "llm_agent"
        else:
            out = _fallback_turn(ctx, message)
    except Exception as exc:
        is_rate_limit = "429" in str(exc) or "rate limit" in str(exc).lower()
        if is_rate_limit:
            logger.warning("OpenRouter rate limit reached (429): %s", exc)
        else:
            logger.exception("LLM agent turn failed; using fallback: %s", exc)
        out = _fallback_turn(ctx, message)
        llm_ok = False
        mode = "rate_limit_fallback" if is_rate_limit else "fallback"

    # Never accept a foreign shipment_id from the model
    if out.shipment_id and out.shipment_id not in allowed_set:
        if out.shipment_id != ctx.shipment_id:
            out = out.model_copy(update={"shipment_id": ctx.shipment_id})

    cleaned = _sanitize_reply(out.reply)
    if mode not in ("fallback", "ownership_guard") and (not cleaned or is_leaked_internal(out.reply)):
        out = _fallback_turn(ctx, message)
        cleaned = _sanitize_reply(out.reply)
        mode = "fallback_after_leak"
        llm_ok = False
    out = out.model_copy(
        update={
            "reply": cleaned or out.reply,
            "intent": _nudge_intent(out.intent, message),
        }
    )

    # Persist shipment binding only when owned
    shipment_id = out.shipment_id or ctx.shipment_id
    if shipment_id and shipment_id not in allowed_set:
        shipment_id = ctx.shipment_id if ctx.shipment_id in allowed_set else None
    if shipment_id and not thread.get("shipment_id"):
        with db_session() as conn:
            conn.execute(
                "UPDATE chat_threads SET shipment_id=? WHERE thread_id=?",
                (shipment_id, thread["thread_id"]),
            )
        thread["shipment_id"] = shipment_id

    # Ensure escalate / location side effects if model set flags or mentioned escalation
    client_actions = list(out.client_actions or [])
    wants_escalation = (
        out.escalate
        or "escalate_to_ops" in ctx.tools_used
        or any(k in (out.reply or "").lower() for k in (
            "escalated to warehouse operations",
            "escalated this to warehouse operations",
            "escalating to warehouse operations",
            "escalated to operations",
            "escalating to operations",
            "alerted warehouse operations",
        ))
    )
    if wants_escalation:
        if "escalate_to_ops" not in ctx.tools_used:
            tool_impl.tool_escalate(ctx.thread_id, out.escalation_reason or "Escalated for operational review")
            ctx.tools_used.append("escalate_to_ops")
        out.escalate = True
    if (
        "REQUEST_BROWSER_LOCATION" in client_actions
        or "request_browser_location" in ctx.tools_used
        or any(k in out.reply.lower() for k in ("share location", "live location", "share your location", "one-time location", "route eta via gps"))
    ):
        if "REQUEST_BROWSER_LOCATION" not in client_actions:
            client_actions.append("REQUEST_BROWSER_LOCATION")
        if "request_browser_location" not in ctx.tools_used:
            tool_impl.tool_request_browser_location(ctx.thread_id)
            ctx.tools_used.append("request_browser_location")

    options = _ground_options(out.options, ctx)
    grounding = tool_impl.validate_options_grounding(options, ctx.allowed_slot_ids or {o["slot_id"] for o in options})
    metrics_service.record_turn_eval(thread["thread_id"], len(history or []), grounding)

    stale = metrics_service.options_are_stale(thread["thread_id"])
    options, reply, stale = _apply_stale_options(
        thread["thread_id"], shipment_id, options, out.reply, stale=stale
    )

    eta = extract_eta_from_text(message)
    if eta and "record_exception_and_eta" in ctx.tools_used:
        metrics_service.record_predicted_eta(thread["thread_id"], eta, source="DRIVER_DECLARED")

    if options:
        metrics_service.record_options_generated(thread["thread_id"], options)
        rank = ctx.last_rank or {}
        if rank.get("projected_wait_old_min") is not None or rank.get("projected_wait_new_min") is not None:
            src = "ROUTE" if rank.get("route_eta_ts") else "DRIVER_DECLARED"
            metrics_service.record_wait_projection(
                thread["thread_id"],
                rank.get("projected_wait_old_min"),
                rank.get("projected_wait_new_min"),
                predicted_eta_ts=rank.get("scheduling_eta_ts") or eta,
                eta_source=src,
            )

    if out.need_clarification:
        metrics_service.bump_clarification(thread["thread_id"])

    if ctx.booking and ctx.booking.get("ok"):
        metrics_service.resolve_case(thread["thread_id"], "PENDING_CONFIRMATION", first_option_accepted=True)
        if ctx.booking.get("projected_wait_old_min") is not None:
            metrics_service.record_wait_projection(
                thread["thread_id"],
                ctx.booking.get("projected_wait_old_min"),
                ctx.booking.get("projected_wait_new_min"),
            )
        _shipment_id = ctx.booking.get("shipment_id") or shipment_id
        if _shipment_id:
            try:
                opmsg_service.send_message(
                    _shipment_id,
                    ctx.booking.get("appointment_id"),
                    "INTERNAL",
                    "agent@setuhaul.example",
                    "warehouse-ops@setuhaul.example",
                    "Revised appointment selected",
                    f"Driver selected a revised slot. Appointment {ctx.booking.get('appointment_id')} is pending confirmation.",
                )
            except Exception:
                pass

    return {
        "reply": reply,
        "options": options,
        "options_stale": stale,
        "client_actions": client_actions,
        "thread_id": thread["thread_id"],
        "shipment_id": shipment_id,
        "feasibility": ctx.feasibility,
        "hold": ctx.hold,
        "booking": ctx.booking,
        "llm_polished": llm_ok,
        "tools_used": list(dict.fromkeys(ctx.tools_used)),
        "intent": out.intent,
        "structured": out.model_dump(),
        "trace": {
            "agent": "setuhaul_exception_agent",
            "framework": "langgraph",
            "mode": mode,
            "tools_used": list(dict.fromkeys(ctx.tools_used)),
            "llm_polished": llm_ok,
            "intent": out.intent,
            "structured_output": True,
        },
    }


def handle_driver_message(
    user: dict[str, Any],
    message: str,
    thread_id: str | None = None,
    shipment_id: str | None = None,
) -> dict[str, Any]:
    configure_langsmith()
    driver_id = user.get("driver_id")
    if not driver_id:
        return {"error": "User is not linked to a driver_id"}

    if shipment_id:
        owned = booking.assert_driver_owns_shipment(driver_id, shipment_id)
        if not owned.get("ok"):
            return {"error": owned.get("error") or "Shipment not assigned to you"}

    if thread_id:
        with db_session() as conn:
            thread = row_to_dict(
                conn.execute("SELECT * FROM chat_threads WHERE thread_id=?", (thread_id,)).fetchone()
            )
        if not thread:
            thread = chat.ensure_thread(driver_id, shipment_id)
        elif thread.get("driver_id") != driver_id:
            return {"error": "Thread does not belong to this driver"}
        elif thread.get("thread_status") in ("CLOSED", "RESOLVED"):
            chat.set_thread_status(thread_id, "OPEN")
            thread["thread_status"] = "OPEN"
    else:
        if shipment_id:
            thread = chat.ensure_thread(driver_id, shipment_id)
        else:
            thread = chat.create_thread(driver_id, None, intent="REPORT_DELAY")

    if shipment_id and not thread.get("shipment_id"):
        with db_session() as conn:
            conn.execute(
                "UPDATE chat_threads SET shipment_id=? WHERE thread_id=?",
                (shipment_id, thread["thread_id"]),
            )
        thread["shipment_id"] = shipment_id

    if thread.get("thread_status") == "ESCALATED":
        chat.add_message(thread["thread_id"], "DRIVER", message, driver_id)
        return {
            "reply": "This thread is with operations. An operator will respond shortly.",
            "options": [],
            "client_actions": [],
            "thread_id": thread["thread_id"],
            "shipment_id": thread.get("shipment_id"),
            "human_takeover": True,
            "messages": chat.get_thread_messages(thread["thread_id"]),
        }

    driver_msg = chat.add_message(thread["thread_id"], "DRIVER", message, driver_id, extracted_eta_ts=extract_eta_from_text(message))
    history = chat.get_thread_messages(thread["thread_id"])

    is_action = any(k in message.lower() for k in ("option", "hold", "book", "confirm", "select", "slot", "take"))
    if driver_msg.get("is_duplicate") and not _is_lightweight(message) and not is_action:
        prior = next((m for m in reversed(history) if m.get("sender_type") == "AGENT" and not m.get("is_duplicate")), None)
        reply = (
            "I already have that update — treating this as a duplicate message, not a new delay."
            if not prior
            else f"Duplicate of your earlier message. Last reply still stands: {prior.get('message_text')}"
        )
        agent_msg = chat.add_message(thread["thread_id"], "AGENT", reply, "agent", parsed_intent="DUPLICATE")
        return {
            "reply": reply,
            "options": [],
            "client_actions": [],
            "thread_id": thread["thread_id"],
            "shipment_id": thread.get("shipment_id"),
            "duplicate": True,
            "agent_message": agent_msg,
            "messages": chat.get_thread_messages(thread["thread_id"]),
        }

    if len(message.strip()) < 2:
        metrics_service.record_turn_eval(thread["thread_id"], len(history), {"notes": "empty_blocked"})
        return {
            "reply": "Please share a short update (delay, ETA, or question).",
            "options": [],
            "client_actions": [],
            "thread_id": thread["thread_id"],
            "shipment_id": thread.get("shipment_id"),
        }

    result = run_agent_turn(user, thread, message, history)
    agent_msg = chat.add_message(result["thread_id"], "AGENT", result["reply"], "agent")
    result["agent_message"] = agent_msg
    result["messages"] = chat.get_thread_messages(result["thread_id"])
    return result


# Compatibility aliases for older imports / docs
def get_exception_graph():
    """Legacy hook — agent is built per turn with create_agent + tools."""
    return None


def build_exception_graph():
    return None
