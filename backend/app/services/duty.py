from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from app.db import db_session, get_setting, now_iso, row_to_dict


def get_driver_duty(driver_id: str) -> dict[str, Any] | None:
    with db_session() as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM drivers WHERE driver_id = ?", (driver_id,)).fetchone()
        )


def update_duty_after_slot(driver_id: str, slot_end_ts: str, unload_min: int = 60, buffer_min: int = 15) -> dict[str, Any]:
    duty = get_driver_duty(driver_id)
    if not duty:
        return {"ok": False, "error": "Driver not found"}
    current = int(duty.get("remaining_duty_minutes") or 600)
    deduct = unload_min + buffer_min
    new_remaining = max(0, current - deduct)
    with db_session() as conn:
        conn.execute(
            "UPDATE drivers SET remaining_duty_minutes = ?, updated_at = ? WHERE driver_id = ?",
            (new_remaining, now_iso(), driver_id),
        )
    return {
        "ok": True,
        "driver_id": driver_id,
        "deducted_min": deduct,
        "previous_remaining": current,
        "new_remaining": new_remaining,
    }


def can_accept_slot(driver_id: str, slot_start_ts: str, expected_unload_min: int = 60) -> dict[str, Any]:
    duty = get_driver_duty(driver_id)
    if not duty:
        return {"ok": False, "can_accept": False, "error": "Driver not found"}
    remaining = int(duty.get("remaining_duty_minutes") or 0)
    required = expected_unload_min + 15
    if remaining < required:
        return {
            "ok": True,
            "can_accept": False,
            "reason": f"insufficient_duty_time",
            "remaining_min": remaining,
            "required_min": required,
        }
    return {
        "ok": True,
        "can_accept": True,
        "remaining_min": remaining,
        "required_min": required,
    }


def reimburse_duty(driver_id: str, amount_min: int) -> dict[str, Any]:
    duty = get_driver_duty(driver_id)
    if not duty:
        return {"ok": False, "error": "Driver not found"}
    current = int(duty.get("remaining_duty_minutes") or 0)
    new_remaining = min(int(duty.get("max_daily_hours") or 10) * 60, current + amount_min)
    with db_session() as conn:
        conn.execute(
            "UPDATE drivers SET remaining_duty_minutes = ?, updated_at = ? WHERE driver_id = ?",
            (new_remaining, now_iso(), driver_id),
        )
    return {
        "ok": True,
        "driver_id": driver_id,
        "reimbursed_min": amount_min,
        "new_remaining": new_remaining,
    }
