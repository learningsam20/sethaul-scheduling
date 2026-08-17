from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.auth import CurrentUser
from app.db import db_session, now_iso, row_to_dict
from app.services import chat, eta, metrics as metrics_service
from app.agent.graph import _apply_stale_options, handle_driver_message

router = APIRouter(prefix="/location", tags=["location"])


class LocationBody(BaseModel):
    thread_id: str
    latitude: float
    longitude: float
    accuracy_m: float | None = None
    captured_at: str | None = None
    client_now: str | None = None
    denied: bool = False


@router.post("/resume")
def resume_location(body: LocationBody, user: CurrentUser) -> dict[str, Any]:
    if user["role"] not in ("DRIVER", "ADMIN"):
        raise HTTPException(403, "Driver only")
    with db_session() as conn:
        thread = row_to_dict(
            conn.execute("SELECT * FROM chat_threads WHERE thread_id=?", (body.thread_id,)).fetchone()
        )
        conn.execute(
            """
            UPDATE agent_pending_actions
            SET status=?, updated_at=?
            WHERE thread_id=? AND action_type='REQUEST_BROWSER_LOCATION' AND status='WAITING'
            """,
            ("CANCELLED" if body.denied else "COMPLETED", now_iso(), body.thread_id),
        )
    if not thread:
        raise HTTPException(404, "Thread not found")
    if body.denied:
        msg = chat.add_message(
            body.thread_id,
            "SYSTEM",
            "Location sharing declined. Continuing with driver-declared ETA only.",
            "system",
        )
        follow = handle_driver_message(
            user,
            "Continue without location using my declared ETA.",
            thread_id=body.thread_id,
            shipment_id=thread.get("shipment_id"),
        )
        return {"ok": True, "denied": True, "system_message": msg, "agent": follow}

    loc = eta.save_location_snapshot(
        body.thread_id,
        user.get("driver_id") or thread["driver_id"],
        thread.get("shipment_id"),
        body.latitude,
        body.longitude,
        body.accuracy_m,
        body.captured_at or now_iso(),
    )
    route = {"ok": False}
    if thread.get("shipment_id"):
        route = eta.compute_route_eta(
            thread["shipment_id"], body.thread_id, loc["location_id"], client_now=body.client_now
        )
        if not route.get("ok"):
            err = route.get("error") or "location_failed"
            if err == "stale_location":
                reply = (
                    f"That location looks stale ({int(route.get('age_seconds') or 0)}s old). "
                    "Share a fresh one-time location, or continue with your declared ETA."
                )
            elif route.get("hard_outage") or err == "routing_unavailable":
                reply = "Routing is unavailable right now. Continuing with your driver-declared ETA only."
            else:
                reply = "Could not compute a route ETA. Continuing with your declared ETA."
            chat.add_message(body.thread_id, "AGENT", reply, "agent")
            return {
                "ok": False,
                "error": err,
                "location": loc,
                "route": route,
                "options": [],
                "reply": reply,
                "messages": chat.get_thread_messages(body.thread_id),
                "client_actions": [],
            }
        if route.get("at_gate"):
            reply = (
                "You are already at the gate — route ETA is not used. "
                "Yard wait follows the current appointment / queue, not an en-route estimate."
            )
            chat.add_message(body.thread_id, "AGENT", reply, "agent")
            metrics_service.record_predicted_eta(body.thread_id, route.get("route_eta_ts") or "", source="GATE_IN")
            return {
                "ok": True,
                "at_gate": True,
                "location": loc,
                "route": route,
                "options": [],
                "reply": reply,
                "messages": chat.get_thread_messages(body.thread_id),
                "client_actions": [],
            }
        r_ts = route.get("route_eta_ts")
        d_ts = route.get("driver_declared_eta_ts")
        r_eta = str(r_ts)[11:16] if r_ts else ""
        d_eta = str(d_ts)[11:16] if d_ts else ""

        def _safe_dt(ts_str: str | None) -> datetime | None:
            if not ts_str:
                return None
            try:
                t = str(ts_str).strip().replace("Z", "+00:00")
                dt = datetime.fromisoformat(t)
                return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
            except Exception:
                return None

        r_dt = _safe_dt(r_ts)
        d_dt = _safe_dt(d_ts)
        diff_min = abs((r_dt - d_dt).total_seconds()) / 60.0 if (r_dt and d_dt) else 0.0

        # If there is a large difference (> 30 mins), ask the driver before scheduling on location ETA
        if diff_min > 30.0:
            diff_h = round(diff_min / 60.0, 1) if diff_min >= 60 else f"{int(diff_min)} mins"
            diff_str = f"{diff_h} hours" if isinstance(diff_h, float) else diff_h
            reply = (
                f"I'm seeing a significant difference between your declared ETA (~{d_eta}) "
                f"and your live GPS route ETA (~{r_eta}, difference of ~{diff_str}).\n\n"
                f"Would you like to schedule based on your GPS location ETA (~{r_eta})? "
                f"(Reply **yes** for location ETA, or **no** to use your declared ETA)."
            )
            chat.add_message(body.thread_id, "AGENT", reply, "agent")
            return {
                "ok": True,
                "location": loc,
                "route": route,
                "options": [],
                "options_stale": False,
                "reply": reply,
                "messages": chat.get_thread_messages(body.thread_id),
                "client_actions": [],
            }

        rec = route.get("eta_source_recommendation") or "ROUTE"
        source = "ROUTE" if rec in ("ROUTE", "EITHER", "GATE_IN") else "DRIVER_DECLARED"
        predicted = route.get("route_eta_ts") if source == "ROUTE" else route.get("driver_declared_eta_ts")
        if predicted:
            metrics_service.record_predicted_eta(body.thread_id, predicted, source=source)
        ranked = eta.rank_slots_with_eta_buffers(
            thread["shipment_id"],
            route_eta_ts=route.get("route_eta_ts"),
            declared_eta_ts=route.get("driver_declared_eta_ts"),
        )
        options = ranked.get("options") or []
        eta_desc = f"Verified route ETA: ~{r_eta}" if r_eta else "Location updated"
        if d_eta and r_eta and d_eta != r_eta:
            eta_desc += f" (declared: ~{d_eta})"

        opt_lines = []
        for i, opt in enumerate(options[:5], 1):
            start = str(opt.get("slot_start_ts", ""))
            end = str(opt.get("slot_end_ts", ""))
            start_hm = start[11:16] if len(start) >= 16 else start
            end_hm = end[11:16] if len(end) >= 16 else end
            dock = opt.get("dock_code") or "Dock"
            buf = f" (+{opt.get('arrival_buffer_min')}m buffer)" if opt.get("arrival_buffer_min") is not None else ""
            opt_lines.append(f"**Option {i}:** Dock {dock} ({start_hm}–{end_hm}){buf} `[{opt.get('slot_id')}]`")

        if opt_lines:
            reply = (
                f"{eta_desc}. Here are the available slots fitting your arrival window:\n\n"
                + "\n".join(opt_lines)
                + "\n\nSay **\"take option 1\"** to soft-hold (still needs warehouse confirmation)."
            )
        else:
            reply = f"{eta_desc}. No open dock slots fit this arrival window. Escalating to warehouse operations."
        options, reply, stale = _apply_stale_options(
            body.thread_id,
            thread.get("shipment_id"),
            options,
            reply,
        )
        if options:
            metrics_service.record_options_generated(body.thread_id, options)
            metrics_service.record_wait_projection(
                body.thread_id,
                ranked.get("projected_wait_old_min"),
                ranked.get("projected_wait_new_min"),
                predicted_eta_ts=ranked.get("scheduling_eta_ts"),
                eta_source=source,
            )
        chat.add_message(body.thread_id, "AGENT", reply, "agent")
        return {
            "ok": True,
            "location": loc,
            "route": route,
            "options": options[:5],
            "options_stale": stale,
            "reply": reply,
            "messages": chat.get_thread_messages(body.thread_id),
            "client_actions": [],
        }
    return {"ok": True, "location": loc, "route": route}
