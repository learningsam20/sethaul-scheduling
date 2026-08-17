from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from app.db import db_session, get_setting, now_iso, rows_to_dicts, row_to_dict
from app.services.booking import find_feasible_slots
from app.services import duty

PRIORITY_WEIGHT = {"CRITICAL": 40, "HIGH": 25, "NORMAL": 10, "LOW": 0}


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _hhmm(ts: datetime) -> str:
    return f"{ts.hour:02d}:{ts.minute:02d}"


def _compatible(dock: dict[str, Any], row: dict[str, Any]) -> bool:
    if dock.get("dock_status") != "ACTIVE":
        return False
    required = row.get("required_dock_type") or "ANY"
    if required not in ("ANY", None) and dock.get("dock_type") != required:
        return False
    if row.get("temperature_control_required") and not dock.get("supports_refrigerated"):
        return False
    weight = row.get("load_weight_kg") or 0
    if dock.get("max_vehicle_weight_kg") and weight > dock["max_vehicle_weight_kg"]:
        return False
    return True


def _dock_blocked(events: list[dict[str, Any]], dock_id: str, start: datetime, end: datetime) -> bool:
    for e in events:
        if e["dock_id"] != dock_id:
            continue
        if e["event_type"] not in ("MAINTENANCE", "BREAKDOWN", "CAPACITY_REDUCTION", "MANUAL_BLOCK"):
            continue
        es = _parse(e["event_start_ts"])
        ee = _parse(e.get("event_end_ts")) or datetime.max.replace(tzinfo=start.tzinfo)
        if es and es < end and ee > start:
            return True
    return False


def run_facility_schedule(
    facility_id: str,
    focus_shipment_id: str | None = None,
    trigger: str = "manual",
) -> dict[str, Any]:
    """Assign trucks to concrete dock time-intervals.

    Objective: minimise waiting + lateness + overtime, never move IN_PROGRESS,
    prefer higher-priority work, and report utilisation / priority violations.
    """
    with db_session() as conn:
        classroom_now = get_setting(conn, "classroom_now", now_iso()) or now_iso()
        now_dt = _parse(classroom_now) or datetime.fromisoformat(now_iso())
        facility = row_to_dict(
            conn.execute("SELECT * FROM facilities WHERE facility_id=?", (facility_id,)).fetchone()
        ) or {}
        docks = rows_to_dicts(
            conn.execute(
                "SELECT * FROM docks WHERE facility_id=? ORDER BY dock_code", (facility_id,)
            ).fetchall()
        )
        inbound = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM v_inbound_operational_state
                WHERE destination_facility_id = ?
                  AND current_status NOT IN ('COMPLETED','CANCELLED')
                ORDER BY effective_eta_ts
                """,
                (facility_id,),
            ).fetchall()
        )
        queue = rows_to_dicts(
            conn.execute(
                "SELECT * FROM v_current_facility_queue WHERE facility_id = ? ORDER BY queue_position",
                (facility_id,),
            ).fetchall()
        )
        events = rows_to_dicts(
            conn.execute(
                """
                SELECT e.* FROM dock_status_events e
                JOIN docks d ON d.dock_id = e.dock_id
                WHERE d.facility_id = ?
                """,
                (facility_id,),
            ).fetchall()
        )
        close_hhmm = facility.get("close_time") or "22:00"
        policy_row = conn.execute(
            "SELECT * FROM allocation_policy WHERE facility_id = ? AND active_flag = 1",
            (facility_id,),
        ).fetchone()
        policy = row_to_dict(policy_row) if policy_row else None
        priority_weights = json.loads(policy["priority_weights_json"]) if policy and policy.get("priority_weights_json") else PRIORITY_WEIGHT
        in_progress_protection = bool(policy["in_progress_protection"]) if policy and policy.get("in_progress_protection") is not None else True
        objective_summary = policy["objective_summary"] if policy and policy.get("objective_summary") else (
            "min waiting + lateness + overtime; never move IN_PROGRESS; "
            "priority then at-facility then ETA; assign concrete dock intervals"
        )

    # Per-dock occupied intervals (start, end, shipment_id, fixed)
    occupied: dict[str, list[tuple[datetime, datetime, str, bool]]] = {d["dock_id"]: [] for d in docks}
    dock_by_code = {d["dock_code"]: d for d in docks}
    assignments: list[dict[str, Any]] = []
    sequence: list[dict[str, Any]] = []

    def remaining_unload(row: dict[str, Any]) -> int:
        return int(row.get("expected_unload_min") or 60)

    # Fixed work: trucks already in a dock keep that interval.
    remaining: list[dict[str, Any]] = []
    for row in inbound:
        in_progress = row.get("current_status") == "IN_DOCK" or bool(row.get("actual_dock_code") and row.get("current_status") == "IN_DOCK")
        if row.get("current_status") == "IN_DOCK":
            in_progress = True
        at_facility = 1 if row.get("gate_in_ts") else 0
        priority = int(priority_weights.get(row.get("priority_code") or "NORMAL", 10))
        if not in_progress_protection and row.get("current_status") == "IN_DOCK":
            in_progress = False
        unload = remaining_unload(row)
        score = priority + (20 * at_facility) + (1000 * int(in_progress)) - (unload * 0.05)
        item = {
            "shipment_id": row["shipment_id"],
            "priority_code": row.get("priority_code"),
            "effective_eta_ts": row.get("effective_eta_ts"),
            "gate_in_ts": row.get("gate_in_ts"),
            "current_status": row.get("current_status"),
            "required_dock_type": row.get("required_dock_type"),
            "temperature_control_required": row.get("temperature_control_required"),
            "load_weight_kg": row.get("load_weight_kg"),
            "expected_unload_min": unload,
            "planned_dock_code": row.get("planned_dock_code"),
            "actual_dock_code": row.get("actual_dock_code"),
            "slot_start_ts": row.get("slot_start_ts"),
            "slot_end_ts": row.get("slot_end_ts"),
            "score": round(score, 2),
            "fixed": bool(in_progress),
        }
        if in_progress:
            dock = dock_by_code.get(row.get("actual_dock_code") or row.get("planned_dock_code") or "")
            start = _parse(row.get("slot_start_ts")) or now_dt
            if start < now_dt:
                start = now_dt
            end = start + timedelta(minutes=unload)
            if dock:
                occupied[dock["dock_id"]].append((start, end, row["shipment_id"], True))
                assignments.append(
                    {
                        "shipment_id": row["shipment_id"],
                        "dock_id": dock["dock_id"],
                        "dock_code": dock["dock_code"],
                        "assigned_start_ts": start.isoformat(),
                        "assigned_end_ts": end.isoformat(),
                        "fixed": True,
                        "waiting_min": 0,
                        "lateness_min": 0,
                        "overtime_min": 0,
                        "reason": "in_progress_protected",
                    }
                )
            item["reason"] = "in_progress_protected"
            sequence.append(item)
        else:
            remaining.append(item)

    remaining.sort(key=lambda x: (-x["score"], x.get("effective_eta_ts") or ""))

    total_wait = 0.0
    total_late = 0.0
    total_overtime = 0.0
    assigned_unload = 0.0

    for item in remaining:
        eta = _parse(item.get("gate_in_ts")) or _parse(item.get("effective_eta_ts")) or now_dt
        unload = item["expected_unload_min"]
        best: dict[str, Any] | None = None
        for dock in docks:
            if not _compatible(dock, item):
                continue
            busy = sorted(occupied[dock["dock_id"]], key=lambda t: t[0])
            cursor = eta if eta > now_dt else now_dt
            # Walk gaps on this dock
            for occ_start, occ_end, _, _ in busy:
                if cursor + timedelta(minutes=unload) <= occ_start:
                    break
                if occ_end > cursor:
                    cursor = occ_end
            start = cursor
            end = start + timedelta(minutes=unload)
            if _dock_blocked(events, dock["dock_id"], start, end):
                continue
            wait = max(0.0, (start - eta).total_seconds() / 60)
            late = max(0.0, (start - eta).total_seconds() / 60) if start > eta + timedelta(minutes=15) else 0.0
            overtime = 0.0
            if close_hhmm and _hhmm(end) > close_hhmm:
                overtime = 30.0
            cost = wait + late + overtime * 2 - (5 if dock.get("dock_type") == item.get("required_dock_type") else 0)
            cand = {
                "dock": dock,
                "start": start,
                "end": end,
                "wait": round(wait, 1),
                "late": round(late, 1),
                "overtime": overtime,
                "cost": cost,
            }
            if best is None or cand["cost"] < best["cost"]:
                best = cand
        if best is None:
            item["reason"] = "no_feasible_dock_interval"
            item["fixed"] = False
            sequence.append(item)
            continue
        dock = best["dock"]
        driver_id = item.get("driver_id")
        if driver_id:
            duty_check = duty.can_accept_slot(driver_id, best["start"].isoformat(), unload)
            if not duty_check.get("can_accept"):
                item["reason"] = "insufficient_duty_time"
                item["fixed"] = False
                sequence.append(item)
                continue
        occupied[dock["dock_id"]].append((best["start"], best["end"], item["shipment_id"], False))
        if driver_id:
            duty.update_duty_after_slot(driver_id, best["end"].isoformat(), unload)
        total_wait += best["wait"]
        total_late += best["late"]
        total_overtime += best["overtime"]
        assigned_unload += unload
        assignments.append(
            {
                "shipment_id": item["shipment_id"],
                "dock_id": dock["dock_id"],
                "dock_code": dock["dock_code"],
                "assigned_start_ts": best["start"].isoformat(),
                "assigned_end_ts": best["end"].isoformat(),
                "fixed": False,
                "waiting_min": best["wait"],
                "lateness_min": best["late"],
                "overtime_min": best["overtime"],
                "reason": "assigned_to_dock_interval",
            }
        )
        item["reason"] = "assigned_to_dock_interval"
        item["assigned_dock_code"] = dock["dock_code"]
        item["assigned_start_ts"] = best["start"].isoformat()
        item["assigned_end_ts"] = best["end"].isoformat()
        item["fixed"] = False
        sequence.append(item)

    sequence.sort(key=lambda x: (0 if x.get("fixed") else 1, x.get("assigned_start_ts") or x.get("effective_eta_ts") or ""))

    # Priority-policy violations: a lower-priority truck starts before a higher-priority
    # truck that is already available (ETA/gate-in <= that start) on a compatible dock type.
    violations: list[dict[str, Any]] = []
    by_id = {a["shipment_id"]: a for a in assignments}
    for high in remaining:
        ha = by_id.get(high["shipment_id"])
        if not ha:
            continue
        high_ready = _parse(high.get("gate_in_ts")) or _parse(high.get("effective_eta_ts"))
        high_start = _parse(ha["assigned_start_ts"])
        if not high_ready or not high_start:
            continue
        for low in remaining:
            if priority_weights.get(low.get("priority_code") or "NORMAL", 10) >= priority_weights.get(
                high.get("priority_code") or "NORMAL", 10
            ):
                continue
            la = by_id.get(low["shipment_id"])
            if not la:
                continue
            low_start = _parse(la["assigned_start_ts"])
            if low_start and high_ready <= low_start < high_start and la["dock_code"] == ha["dock_code"]:
                violations.append(
                    {
                        "higher": high["shipment_id"],
                        "lower": low["shipment_id"],
                        "dock_code": ha["dock_code"],
                    }
                )

    horizon_min = 14 * 60
    dock_count = max(len(docks), 1)
    utilisation = round(assigned_unload / (dock_count * horizon_min) * 100, 1) if horizon_min else 0

    focus_options = []
    if focus_shipment_id:
        focus_options = find_feasible_slots(focus_shipment_id, limit=5)

    result = {
        "facility_id": facility_id,
        "trigger": trigger,
        "sequence": sequence,
        "assignments": assignments,
        "queue": queue,
        "focus_shipment_id": focus_shipment_id,
        "focus_options": focus_options,
        "objective": objective_summary,
        "priority_weights": priority_weights,
        "in_progress_protection": in_progress_protection,
        "kpis": {
            "trucks": len(inbound),
            "assigned": len(assignments),
            "fixed_work": sum(1 for a in assignments if a.get("fixed")),
            "total_waiting_min": round(total_wait, 1),
            "total_lateness_min": round(total_late, 1),
            "total_overtime_min": round(total_overtime, 1),
            "slot_utilisation_pct": utilisation,
            "priority_violations": len(violations),
            "priority_violation_pairs": violations[:12],
        },
    }
    run_id = f"SCH-{uuid4().hex[:10].upper()}"
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO scheduling_runs(run_id, facility_id, shipment_id, objective_summary, input_snapshot_json, result_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                facility_id,
                focus_shipment_id,
                result["objective"],
                json.dumps(
                    {
                        "inbound_count": len(inbound),
                        "queue_count": len(queue),
                        "trigger": trigger,
                        "dock_count": len(docks),
                    }
                ),
                json.dumps(result),
                now_iso(),
            ),
        )
    result["run_id"] = run_id
    return result
