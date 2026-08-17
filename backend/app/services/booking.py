from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.db import db_session, get_setting, now_iso, rows_to_dicts, row_to_dict
from app.services import duty

IST = ZoneInfo("Asia/Kolkata")


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def get_inbound_state(
    facility_id: str | None = None,
    shipment_id: str | None = None,
    driver_id: str | None = None,
) -> list[dict[str, Any]]:
    with db_session() as conn:
        sql = "SELECT * FROM v_inbound_operational_state WHERE 1=1"
        params: list[Any] = []
        if facility_id:
            sql += " AND destination_facility_id = ?"
            params.append(facility_id)
        if shipment_id:
            sql += " AND shipment_id = ?"
            params.append(shipment_id)
        if driver_id:
            sql += " AND driver_id = ?"
            params.append(driver_id)
        sql += " ORDER BY effective_eta_ts"
        return rows_to_dicts(conn.execute(sql, params).fetchall())


def shipment_owner(shipment_id: str) -> dict[str, Any] | None:
    with db_session() as conn:
        return row_to_dict(
            conn.execute(
                "SELECT shipment_id, driver_id, current_status FROM shipments WHERE shipment_id = ?",
                (shipment_id,),
            ).fetchone()
        )


def assert_driver_owns_shipment(driver_id: str, shipment_id: str) -> dict[str, Any]:
    """Return {ok: True, shipment} or {ok: False, error} — never allow cross-driver mutation."""
    if not shipment_id:
        return {"ok": False, "error": "shipment_id is required"}
    row = shipment_owner(shipment_id)
    if not row:
        return {"ok": False, "error": f"Shipment {shipment_id} was not found"}
    if row.get("driver_id") != driver_id:
        return {
            "ok": False,
            "error": f"Shipment {shipment_id} is not assigned to you. Use one of your own active shipments.",
        }
    return {"ok": True, "shipment": row}


def resolve_driver_context(driver_id: str) -> dict[str, Any]:
    with db_session() as conn:
        driver = row_to_dict(
            conn.execute("SELECT * FROM drivers WHERE driver_id = ?", (driver_id,)).fetchone()
        )
        shipments = rows_to_dicts(
            conn.execute(
                """
                SELECT s.*, le.effective_eta_ts, le.eta_source, le.eta_confidence
                FROM shipments s
                JOIN v_latest_eta le ON le.shipment_id = s.shipment_id
                WHERE s.driver_id = ?
                  AND s.current_status NOT IN ('COMPLETED','CANCELLED')
                ORDER BY s.original_eta_ts
                """,
                (driver_id,),
            ).fetchall()
        )
        return {"driver": driver, "active_shipments": shipments, "needs_disambiguation": len(shipments) > 1}


def check_appointment_feasibility(shipment_id: str) -> dict[str, Any]:
    state = get_inbound_state(shipment_id=shipment_id)
    if not state:
        return {"feasible": False, "reason": "Shipment not found"}
    row = state[0]
    if row["current_status"] == "CANCELLED":
        return {"feasible": False, "reason": "Shipment cancelled", "state": row}
    if not row.get("slot_start_ts") or not row.get("effective_eta_ts"):
        return {"feasible": False, "reason": "Missing appointment or ETA", "state": row}
    eta = _parse_ts(row["effective_eta_ts"])
    slot_start = _parse_ts(row["slot_start_ts"])
    slot_end = _parse_ts(row["slot_end_ts"])
    if eta > slot_end:
        return {
            "feasible": False,
            "reason": "Effective ETA is after current appointment window",
            "state": row,
        }
    if eta > slot_start:
        return {
            "feasible": False,
            "reason": "Effective ETA misses appointment start",
            "state": row,
        }
    return {"feasible": True, "reason": "Current appointment still feasible", "state": row}


def _compatible_dock_clause(shipment: dict[str, Any], rules: dict[str, str] | None = None) -> tuple[str, list[Any]]:
    required = shipment["required_dock_type"]
    weight = shipment["load_weight_kg"]
    reefer = shipment["temperature_control_required"]
    rules = rules or {}
    heavy_kg = None
    try:
        heavy_kg = int(rules.get("HEAVY_DOCK_REQUIRED_KG") or "")
    except (TypeError, ValueError):
        heavy_kg = None
    if heavy_kg is not None and weight >= heavy_kg:
        required = "HEAVY"
    clauses = ["d.max_vehicle_weight_kg >= ?", "d.dock_status = 'ACTIVE'"]
    params: list[Any] = [weight]
    if required != "ANY":
        clauses.append("d.dock_type = ?")
        params.append(required)
    if reefer or str(rules.get("REEFER_DOCK_REQUIRED") or "").upper() in ("TRUE", "1", "YES"):
        if reefer:
            clauses.append("d.supports_refrigerated = 1")
    return " AND ".join(clauses), params


def _facility_rules(conn, facility_id: str) -> dict[str, str]:
    classroom_now = get_setting(conn, "classroom_now", now_iso())
    now_hhmm = _hhmm(datetime.fromisoformat(classroom_now[:19]))
    rows = conn.execute(
        """
        SELECT rule_type, rule_value, partial_day_start, partial_day_end FROM facility_rules
        WHERE facility_id = ? AND active_flag = 1
          AND (effective_to IS NULL OR effective_to >= date(?))
          AND (
            partial_day_start IS NULL OR partial_day_end IS NULL
            OR (time(?) BETWEEN partial_day_start AND partial_day_end)
          )
        """,
        (facility_id, classroom_now[:10], now_hhmm),
    ).fetchall()
    return {r["rule_type"]: r["rule_value"] for r in rows}


def _hhmm(ts: datetime) -> str:
    return f"{ts.hour:02d}:{ts.minute:02d}"


def _replan(facility_id: str | None, trigger: str, shipment_id: str | None = None) -> None:
    if not facility_id:
        return
    from app.services import scheduling

    scheduling.run_facility_schedule(facility_id, shipment_id, trigger=trigger)


def _wait_minutes(eta_ts: str | None, slot_start: str | None, slot_end: str | None) -> float | None:
    if not eta_ts or not slot_start:
        return None
    try:
        eta_dt = datetime.fromisoformat(eta_ts)
        start = datetime.fromisoformat(slot_start)
        if eta_dt <= start:
            return round((start - eta_dt).total_seconds() / 60, 1)
        if slot_end:
            end = datetime.fromisoformat(slot_end)
            return round(max(0.0, (eta_dt - end).total_seconds() / 60), 1)
        return round((eta_dt - start).total_seconds() / 60, 1)
    except Exception:
        return None


def find_feasible_slots(
    shipment_id: str,
    after_ts: str | None = None,
    limit: int = 8,
    exclude_held: bool = True,
) -> list[dict[str, Any]]:
    with db_session() as conn:
        shipment = row_to_dict(
            conn.execute("SELECT * FROM shipments WHERE shipment_id = ?", (shipment_id,)).fetchone()
        )
        if not shipment:
            return []
        facility_id = shipment["destination_facility_id"]
        facility = row_to_dict(
            conn.execute("SELECT * FROM facilities WHERE facility_id = ?", (facility_id,)).fetchone()
        ) or {}
        rules = _facility_rules(conn, facility_id)

        blocked_products = {
            p.strip() for p in (rules.get("PRODUCT_RESTRICTED") or "").split(",") if p.strip()
        }
        blocked_carriers = {
            c.strip() for c in (rules.get("CARRIER_BLOCKED") or "").split(",") if c.strip()
        }
        if shipment.get("product_category") in blocked_products:
            return []
        if shipment.get("carrier_id") in blocked_carriers:
            return []

        eta_row = row_to_dict(
            conn.execute("SELECT * FROM v_latest_eta WHERE shipment_id = ?", (shipment_id,)).fetchone()
        )
        effective_eta = after_ts or (eta_row or {}).get("effective_eta_ts") or shipment["original_eta_ts"]
        dock_sql, dock_params = _compatible_dock_clause(shipment, rules)

        constraint = row_to_dict(
            conn.execute(
                """
                SELECT MAX(earliest_acceptable_ts) AS earliest_acceptable_ts,
                       MIN(latest_acceptable_ts) AS latest_acceptable_ts
                FROM driver_exceptions
                WHERE shipment_id = ?
                """,
                (shipment_id,),
            ).fetchone()
        ) or {}

        sql = f"""
            SELECT v.*, d.dock_id
            FROM v_slot_availability v
            JOIN docks d ON d.dock_code = v.dock_code AND d.facility_id = v.facility_id
            WHERE v.facility_id = ?
              AND v.availability_status = 'AVAILABLE'
              AND v.slot_start_ts >= ?
              AND {dock_sql}
            ORDER BY v.slot_start_ts, v.dock_code
            LIMIT 80
        """
        params = [facility_id, effective_eta, *dock_params]
        candidates = rows_to_dicts(conn.execute(sql, params).fetchall())

        last_start_hhmm = rules.get("LAST_NEW_START_TIME")
        classroom_now = get_setting(conn, "classroom_now", now_iso()) or now_iso()
        open_time = facility.get("open_time")
        close_time = facility.get("close_time")

        held_slots: set[str] = set()
        if exclude_held:
            held = conn.execute(
                """
                SELECT slot_id FROM slot_holds
                WHERE status = 'ACTIVE' AND expires_at > ? AND shipment_id <> ?
                """,
                (classroom_now, shipment_id),
            ).fetchall()
            held_slots = {h["slot_id"] for h in held}

        earliest = constraint.get("earliest_acceptable_ts")
        latest = constraint.get("latest_acceptable_ts")
        results: list[dict[str, Any]] = []
        for c in candidates:
            if c["slot_id"] in held_slots:
                continue
            start = _parse_ts(c["slot_start_ts"])
            end = _parse_ts(c["slot_end_ts"])
            if open_time and _hhmm(start) < open_time:
                continue
            if close_time and (
                _hhmm(start) >= close_time or end.date() > start.date() or _hhmm(end) > close_time
            ):
                continue
            if earliest and c["slot_start_ts"] < earliest:
                continue
            if latest and c["slot_end_ts"] > latest:
                continue
            slot_minutes = (end - start).total_seconds() / 60.0
            if shipment["expected_unload_min"] > slot_minutes + 5:
                continue
            driver_id = shipment.get("driver_id")
            if driver_id:
                duty_check = duty.can_accept_slot(driver_id, c["slot_start_ts"], shipment["expected_unload_min"])
                if not duty_check.get("can_accept"):
                    continue
            requires_manual = False
            if last_start_hhmm:
                hh, mm = map(int, last_start_hhmm.split(":"))
                if start.hour > hh or (start.hour == hh and start.minute > mm):
                    requires_manual = True
            eta = _parse_ts(effective_eta)
            buffer_min = (start - eta).total_seconds() / 60.0
            c["requires_manual_approval"] = requires_manual
            c["arrival_buffer_min"] = round(buffer_min, 1)
            c["priority_code"] = shipment["priority_code"]
            c["shipment_id"] = shipment_id
            c["expected_unload_min"] = shipment["expected_unload_min"]
            results.append(c)
            if len(results) >= limit:
                break
        return results


def soft_hold_slot(slot_id: str, shipment_id: str, thread_id: str | None, user_id: str | None) -> dict[str, Any]:
    with db_session() as conn:
        classroom_now = get_setting(conn, "classroom_now", now_iso()) or now_iso()
        ttl = int(get_setting(conn, "soft_hold_ttl_seconds", "120") or "120")
        expires = (_parse_ts(classroom_now) + timedelta(seconds=ttl)).isoformat()
        conn.execute(
            "UPDATE slot_holds SET status='EXPIRED' WHERE status='ACTIVE' AND expires_at <= ?",
            (classroom_now,),
        )
        # One active hold per shipment — release prior holds before taking a new one
        conn.execute(
            "UPDATE slot_holds SET status='RELEASED' WHERE shipment_id=? AND status='ACTIVE'",
            (shipment_id,),
        )
        hold_id = f"HOLD-{uuid4().hex[:10].upper()}"
        try:
            cur = conn.execute(
                """
                INSERT INTO slot_holds(
                    hold_id, slot_id, shipment_id, thread_id, held_by_user_id, status, created_at, expires_at
                )
                SELECT ?, ?, ?, ?, ?, 'ACTIVE', ?, ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM slot_holds
                    WHERE slot_id = ? AND status = 'ACTIVE' AND expires_at > ?
                )
                """,
                (hold_id, slot_id, shipment_id, thread_id, user_id, classroom_now, expires, slot_id, classroom_now),
            )
            if cur.rowcount == 0:
                return {"ok": False, "error": "Slot held by another shipment", "hold": None}
        except sqlite3.IntegrityError:
            return {"ok": False, "error": "Slot held by another shipment", "hold": None}
        return {
            "ok": True,
            "hold": {
                "hold_id": hold_id,
                "slot_id": slot_id,
                "shipment_id": shipment_id,
                "expires_at": expires,
                "ttl_seconds": ttl,
            },
        }


def confirm_driver_choice(
    shipment_id: str,
    slot_id: str,
    booking_source: str = "DRIVER_CHAT",
) -> dict[str, Any]:
    with db_session() as conn:
        classroom_now = get_setting(conn, "classroom_now", now_iso()) or now_iso()
        avail = conn.execute(
            "SELECT * FROM v_slot_availability WHERE slot_id = ?", (slot_id,)
        ).fetchone()
        if avail is None or (avail["availability_status"] != "AVAILABLE" and avail["shipment_id"] != shipment_id):
            return {"ok": False, "error": "Slot no longer available"}

        current = conn.execute(
            """
            SELECT * FROM appointments
            WHERE shipment_id = ? AND is_current = 1
              AND appointment_status IN ('PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS')
            """,
            (shipment_id,),
        ).fetchone()
        replaced_id = None
        if current:
            replaced_id = current["appointment_id"]
            conn.execute(
                """
                UPDATE appointments
                SET appointment_status='CANCELLED', is_current=0, cancelled_at=?,
                    cancellation_reason=?, updated_at=?
                WHERE appointment_id=?
                """,
                (classroom_now, "Replaced by driver chat reschedule", classroom_now, replaced_id),
            )

        appointment_id = f"APT-{uuid4().hex[:8].upper()}"
        try:
            conn.execute(
                """
                INSERT INTO appointments(
                    appointment_id, shipment_id, slot_id, appointment_status, booking_source,
                    is_current, booked_at, confirmed_at, cancelled_at, cancellation_reason,
                    replaced_appointment_id, warehouse_confirmation_ref, updated_at
                ) VALUES (?, ?, ?, 'PENDING_CONFIRMATION', ?, 1, ?, NULL, NULL, NULL, ?, NULL, ?)
                """,
                (
                    appointment_id,
                    shipment_id,
                    slot_id,
                    booking_source,
                    classroom_now,
                    replaced_id,
                    classroom_now,
                ),
            )
        except Exception as exc:
            return {"ok": False, "error": f"Booking conflict: {exc}"}

        conn.execute(
            """
            UPDATE slot_holds SET status='CONSUMED'
            WHERE slot_id=? AND shipment_id=? AND status='ACTIVE'
            """,
            (slot_id, shipment_id),
        )
        slot_row = row_to_dict(
            conn.execute(
                "SELECT slot_start_ts, slot_end_ts, facility_id FROM appointment_slots WHERE slot_id=?",
                (slot_id,),
            ).fetchone()
        ) or {}
        old_slot = None
        if current:
            old_slot = row_to_dict(
                conn.execute(
                    "SELECT slot_start_ts, slot_end_ts FROM appointment_slots WHERE slot_id=?",
                    (current["slot_id"],),
                ).fetchone()
            )
        eta_row = row_to_dict(
            conn.execute("SELECT effective_eta_ts FROM v_latest_eta WHERE shipment_id=?", (shipment_id,)).fetchone()
        )
        eta_ts = (eta_row or {}).get("effective_eta_ts")
        old_wait = _wait_minutes(eta_ts, (old_slot or {}).get("slot_start_ts"), (old_slot or {}).get("slot_end_ts"))
        new_wait = _wait_minutes(eta_ts, slot_row.get("slot_start_ts"), slot_row.get("slot_end_ts"))
        result = {
            "ok": True,
            "appointment_id": appointment_id,
            "appointment_status": "PENDING_CONFIRMATION",
            "slot_id": slot_id,
            "replaced_appointment_id": replaced_id,
            "message": "Pending warehouse confirmation — not yet confirmed",
            "projected_wait_old_min": old_wait,
            "projected_wait_new_min": new_wait,
            "facility_id": slot_row.get("facility_id"),
        }
    _replan(result.get("facility_id"), "confirm_choice", shipment_id)
    return result


def warehouse_decide(appointment_id: str, approve: bool, actor: str | None = None) -> dict[str, Any]:
    facility_id = None
    shipment_id = None
    with db_session() as conn:
        classroom_now = get_setting(conn, "classroom_now", now_iso()) or now_iso()
        appt = conn.execute(
            "SELECT * FROM appointments WHERE appointment_id = ?", (appointment_id,)
        ).fetchone()
        if not appt:
            return {"ok": False, "error": "Appointment not found"}
        if appt["appointment_status"] != "PENDING_CONFIRMATION":
            return {"ok": False, "error": f"Cannot decide status {appt['appointment_status']}"}
        shipment_id = appt["shipment_id"]
        slot = conn.execute(
            "SELECT facility_id FROM appointment_slots WHERE slot_id=?", (appt["slot_id"],)
        ).fetchone()
        facility_id = slot["facility_id"] if slot else None
        if approve:
            ref = f"WH-{uuid4().hex[:6].upper()}"
            conn.execute(
                """
                UPDATE appointments
                SET appointment_status='CONFIRMED', confirmed_at=?, warehouse_confirmation_ref=?, updated_at=?
                WHERE appointment_id=?
                """,
                (classroom_now, ref, classroom_now, appointment_id),
            )
            wall_ts = datetime.now(IST).isoformat(timespec="seconds")
            thread = conn.execute(
                """
                SELECT thread_id FROM chat_threads
                WHERE shipment_id=? OR driver_id = (SELECT driver_id FROM shipments WHERE shipment_id = ?)
                ORDER BY opened_at DESC LIMIT 1
                """,
                (shipment_id, shipment_id),
            ).fetchone()
            if thread:
                msg_id = f"MSG-{uuid4().hex[:8].upper()}"
                conn.execute(
                    """
                    INSERT INTO chat_messages(
                        chat_message_id, thread_id, sender_type, sender_reference, message_text,
                        message_ts, is_duplicate, parsed_intent, requires_human_review
                    ) VALUES (?, ?, 'SYSTEM', 'warehouse', ?, ?, 0, 'CONFIRMATION', 0)
                    """,
                    (
                        msg_id,
                        thread["thread_id"],
                        f"Warehouse confirmed appointment {appointment_id} (Ref: {ref}). Your dock slot is now CONFIRMED.",
                        wall_ts,
                    ),
                )
        else:
            conn.execute(
                """
                UPDATE appointments
                SET appointment_status='REJECTED', is_current=0, cancelled_at=?,
                    cancellation_reason=?, updated_at=?
                WHERE appointment_id=?
                """,
                (classroom_now, f"Rejected by warehouse ({actor or 'warehouse'})", classroom_now, appointment_id),
            )
            result = {"ok": True, "appointment_status": "REJECTED"}
            wall_ts = datetime.now(IST).isoformat(timespec="seconds")
            thread = conn.execute(
                """
                SELECT thread_id FROM chat_threads
                WHERE shipment_id=? OR driver_id = (SELECT driver_id FROM shipments WHERE shipment_id = ?)
                ORDER BY opened_at DESC LIMIT 1
                """,
                (shipment_id, shipment_id),
            ).fetchone()
            if thread:
                msg_id = f"MSG-{uuid4().hex[:8].upper()}"
                conn.execute(
                    """
                    INSERT INTO chat_messages(
                        chat_message_id, thread_id, sender_type, sender_reference, message_text,
                        message_ts, is_duplicate, parsed_intent, requires_human_review
                    ) VALUES (?, ?, 'SYSTEM', 'warehouse', ?, ?, 0, 'REJECTION', 0)
                    """,
                    (
                        msg_id,
                        thread["thread_id"],
                        f"Warehouse rejected appointment request {appointment_id}. Please check for alternate slots or ask for assistance.",
                        wall_ts,
                    ),
                )
    _replan(facility_id, "warehouse_decide", shipment_id)
    return result


def list_pending_confirmations(facility_id: str | None = None) -> list[dict[str, Any]]:
    with db_session() as conn:
        sql = """
            SELECT a.*, s.driver_id, s.destination_facility_id, s.priority_code,
                   s.customer_name, sl.slot_start_ts, sl.slot_end_ts, d.dock_code
            FROM appointments a
            JOIN shipments s ON s.shipment_id = a.shipment_id
            JOIN appointment_slots sl ON sl.slot_id = a.slot_id
            JOIN docks d ON d.dock_id = sl.dock_id
            WHERE a.appointment_status = 'PENDING_CONFIRMATION' AND a.is_current = 1
        """
        params: list[Any] = []
        if facility_id:
            sql += " AND s.destination_facility_id = ?"
            params.append(facility_id)
        sql += " ORDER BY a.booked_at"
        return rows_to_dicts(conn.execute(sql, params).fetchall())


def cancel_appointment(appointment_id: str, reason: str, actor: str | None = None) -> dict[str, Any]:
    """Runtime cancel — frees the slot, drops active holds, and triggers a rolling replan."""
    facility_id = None
    shipment_id = None
    slot_id = None
    with db_session() as conn:
        classroom_now = get_setting(conn, "classroom_now", now_iso()) or now_iso()
        appt = conn.execute(
            "SELECT * FROM appointments WHERE appointment_id = ?", (appointment_id,)
        ).fetchone()
        if not appt:
            return {"ok": False, "error": "Appointment not found"}
        if appt["appointment_status"] in ("CANCELLED", "COMPLETED", "NO_SHOW", "REJECTED"):
            return {"ok": False, "error": f"Cannot cancel status {appt['appointment_status']}"}
        shipment_id = appt["shipment_id"]
        slot_id = appt["slot_id"]
        slot = conn.execute(
            "SELECT facility_id FROM appointment_slots WHERE slot_id=?", (slot_id,)
        ).fetchone()
        facility_id = slot["facility_id"] if slot else None
        conn.execute(
            """
            UPDATE appointments
            SET appointment_status='CANCELLED', is_current=0, cancelled_at=?,
                cancellation_reason=?, updated_at=?
            WHERE appointment_id=?
            """,
            (classroom_now, reason or f"Cancelled by {actor or 'ops'}", classroom_now, appointment_id),
        )
        conn.execute(
            "UPDATE slot_holds SET status='RELEASED' WHERE slot_id=? AND status='ACTIVE'",
            (slot_id,),
        )
    from app.services import metrics as metrics_service

    if slot_id:
        metrics_service.mark_options_stale_for_slots([slot_id])
    _replan(facility_id, "cancellation", shipment_id)
    return {
        "ok": True,
        "appointment_status": "CANCELLED",
        "appointment_id": appointment_id,
        "slot_id": slot_id,
        "shipment_id": shipment_id,
        "slot_freed": True,
    }


def record_dock_event(
    dock_id: str,
    event_type: str,
    reason: str,
    event_start_ts: str | None = None,
    event_end_ts: str | None = None,
) -> dict[str, Any]:
    """Apply a runtime capacity event: block overlapping slots, drop holds, stale options, replan."""
    start = event_start_ts or now_iso()
    event_id = f"DEVT-{uuid4().hex[:8].upper()}"
    with db_session() as conn:
        dock = conn.execute("SELECT * FROM docks WHERE dock_id=?", (dock_id,)).fetchone()
        if not dock:
            return {"ok": False, "error": "Dock not found"}
        conn.execute(
            """
            INSERT INTO dock_status_events(
                dock_event_id, dock_id, event_type, event_start_ts, event_end_ts, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, dock_id, event_type, start, event_end_ts, reason, now_iso()),
        )
        overlapping = rows_to_dicts(
            conn.execute(
                """
                SELECT slot_id FROM appointment_slots
                WHERE dock_id = ?
                  AND slot_start_ts < COALESCE(?, '9999-12-31')
                  AND slot_end_ts > ?
                """,
                (dock_id, event_end_ts, start),
            ).fetchall()
        )
        slot_ids = [r["slot_id"] for r in overlapping]
        if event_type in ("MAINTENANCE", "BREAKDOWN", "CAPACITY_REDUCTION", "MANUAL_BLOCK") and slot_ids:
            conn.execute(
                f"""
                UPDATE slot_holds SET status='RELEASED'
                WHERE status='ACTIVE' AND slot_id IN ({",".join("?" * len(slot_ids))})
                """,
                slot_ids,
            )
        facility_id = dock["facility_id"]
    from app.services import metrics as metrics_service

    stale = metrics_service.mark_options_stale_for_slots(slot_ids)
    _replan(facility_id, f"dock_{event_type.lower()}", None)
    return {
        "ok": True,
        "dock_event_id": event_id,
        "dock_id": dock_id,
        "affected_slots": slot_ids,
        "holds_released": True,
        "options_marked_stale": stale,
    }


def persist_exception_constraints(
    shipment_id: str,
    driver_id: str,
    thread_id: str,
    declared_eta_ts: str | None,
    delay_min: int | None = None,
    earliest_acceptable_ts: str | None = None,
    latest_acceptable_ts: str | None = None,
    exception_type: str = "DELAY",
    description: str = "",
) -> dict[str, Any]:
    """Write runtime driver_exceptions including earliest/latest acceptable windows."""
    with db_session() as conn:
        existing = conn.execute(
            """
            SELECT exception_id FROM driver_exceptions
            WHERE shipment_id=? AND thread_id=?
            ORDER BY reported_at DESC LIMIT 1
            """,
            (shipment_id, thread_id),
        ).fetchone()
        ts = now_iso()
        if existing:
            conn.execute(
                """
                UPDATE driver_exceptions
                SET declared_eta_ts=COALESCE(?, declared_eta_ts),
                    reported_delay_min=COALESCE(?, reported_delay_min),
                    earliest_acceptable_ts=COALESCE(?, earliest_acceptable_ts),
                    latest_acceptable_ts=COALESCE(?, latest_acceptable_ts),
                    description=CASE WHEN ? = '' THEN description ELSE ? END
                WHERE exception_id=?
                """,
                (
                    declared_eta_ts,
                    delay_min,
                    earliest_acceptable_ts,
                    latest_acceptable_ts,
                    description,
                    description,
                    existing["exception_id"],
                ),
            )
            return {"ok": True, "exception_id": existing["exception_id"], "updated": True}
        exc_id = f"EXC-{uuid4().hex[:8].upper()}"
        conn.execute(
            """
            INSERT INTO driver_exceptions(
                exception_id, shipment_id, driver_id, thread_id, exception_type, reported_at,
                reported_delay_min, declared_eta_ts, earliest_acceptable_ts, latest_acceptable_ts,
                severity_code, exception_status, description, dedupe_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'MEDIUM', 'OPEN', ?, ?)
            """,
            (
                exc_id,
                shipment_id,
                driver_id,
                thread_id,
                exception_type,
                ts,
                delay_min,
                declared_eta_ts,
                earliest_acceptable_ts,
                latest_acceptable_ts,
                description or f"{exception_type} reported in chat",
                f"{driver_id}-{shipment_id}-{ts[:16]}",
            ),
        )
        return {"ok": True, "exception_id": exc_id, "updated": False}
