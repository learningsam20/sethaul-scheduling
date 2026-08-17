from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx

from app.config import get_settings
from app.db import db_session, now_iso, row_to_dict, get_setting
from app.services.booking import find_feasible_slots, persist_exception_constraints


def record_driver_eta(
    shipment_id: str,
    driver_id: str,
    declared_eta_ts: str,
    confidence: str = "MEDIUM",
    delay_reason: str | None = "TRAFFIC",
    note: str | None = None,
    delay_min: int | None = None,
    thread_id: str | None = None,
    earliest_acceptable_ts: str | None = None,
    latest_acceptable_ts: str | None = None,
) -> dict[str, Any]:
    mismatch = None
    with db_session() as conn:
        shipment = row_to_dict(
            conn.execute("SELECT * FROM shipments WHERE shipment_id=?", (shipment_id,)).fetchone()
        )
        eta_id = f"ETA-{uuid4().hex[:8].upper()}"
        ts = now_iso()
        if delay_min is not None and int(delay_min) > 0 and shipment:
            base_str = shipment.get("original_eta_ts") or shipment.get("latest_eta_ts")
            if base_str:
                try:
                    base_dt = datetime.fromisoformat(base_str.replace("Z", "+00:00"))
                    computed_dt = base_dt + timedelta(minutes=int(delay_min))
                    if not declared_eta_ts or declared_eta_ts == base_str:
                        declared_eta_ts = computed_dt.isoformat()
                    else:
                        declared_dt = datetime.fromisoformat(declared_eta_ts.replace("Z", "+00:00"))
                        drift = abs((declared_dt - computed_dt).total_seconds()) / 60
                        if drift > 20:
                            mismatch = (
                                f"Delay {delay_min} min from original ETA implies {computed_dt.isoformat()}; "
                                f"declared {declared_eta_ts} (Δ {round(drift, 1)} min)"
                            )
                            note = f"{note + ' | ' if note else ''}{mismatch}"
                except Exception:
                    pass
        conn.execute(
            """
            INSERT INTO eta_updates(
                eta_update_id, shipment_id, source_type, reported_by_driver_id,
                declared_eta_ts, confidence_code, delay_reason_code, note, created_at
            ) VALUES (?, ?, 'DRIVER_DECLARED', ?, ?, ?, ?, ?, ?)
            """,
            (eta_id, shipment_id, driver_id, declared_eta_ts, confidence, delay_reason, note, ts),
        )
        conn.execute(
            "UPDATE shipments SET latest_eta_ts=?, updated_at=? WHERE shipment_id=?",
            (declared_eta_ts, ts, shipment_id),
        )
        facility_id = (shipment or {}).get("destination_facility_id")
    if thread_id:
        persist_exception_constraints(
            shipment_id,
            driver_id,
            thread_id,
            declared_eta_ts,
            delay_min=delay_min,
            earliest_acceptable_ts=earliest_acceptable_ts,
            latest_acceptable_ts=latest_acceptable_ts,
            exception_type="BREAKDOWN" if delay_reason == "BREAKDOWN" else "DELAY",
            description=note or "",
        )
    from app.services.booking import _replan

    _replan(facility_id, "eta_update", shipment_id)
    return {
        "eta_update_id": eta_id,
        "declared_eta_ts": declared_eta_ts,
        "source_type": "DRIVER_DECLARED",
        "delay_eta_mismatch": mismatch,
    }


def save_location_snapshot(
    thread_id: str,
    driver_id: str,
    shipment_id: str | None,
    latitude: float,
    longitude: float,
    accuracy_m: float | None,
    captured_at: str,
) -> dict[str, Any]:
    location_id = f"LOC-{uuid4().hex[:8].upper()}"
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO location_snapshots(
                location_id, thread_id, driver_id, shipment_id, latitude, longitude, accuracy_m, captured_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                location_id,
                thread_id,
                driver_id,
                shipment_id,
                latitude,
                longitude,
                accuracy_m,
                captured_at,
                now_iso(),
            ),
        )
    return {"location_id": location_id}


def compute_route_eta(
    shipment_id: str,
    thread_id: str,
    location_id: str,
    client_now: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    with db_session() as conn:
        loc = row_to_dict(
            conn.execute("SELECT * FROM location_snapshots WHERE location_id=?", (location_id,)).fetchone()
        )
        shipment = row_to_dict(
            conn.execute("SELECT * FROM shipments WHERE shipment_id=?", (shipment_id,)).fetchone()
        )
        geo = row_to_dict(
            conn.execute(
                "SELECT * FROM facility_geo WHERE facility_id=?",
                (shipment["destination_facility_id"],),
            ).fetchone()
        ) if shipment else None
        declared = row_to_dict(
            conn.execute("SELECT * FROM v_latest_eta WHERE shipment_id=?", (shipment_id,)).fetchone()
        )
        checkin = row_to_dict(
            conn.execute(
                "SELECT * FROM facility_checkins WHERE shipment_id=? AND gate_in_ts IS NOT NULL",
                (shipment_id,),
            ).fetchone()
        ) if shipment else None
        classroom_now = get_setting(conn, "classroom_now", now_iso()) or now_iso()

    if not loc or not shipment or not geo:
        return {"ok": False, "error": "Missing location, shipment, or facility geo"}

    if checkin and checkin.get("gate_in_ts"):
        return {
            "ok": True,
            "at_gate": True,
            "provider": "AT_GATE",
            "distance_m": 0,
            "duration_s": 0,
            "route_eta_ts": checkin["gate_in_ts"],
            "driver_declared_eta_ts": (declared or {}).get("effective_eta_ts"),
            "eta_source_recommendation": "GATE_IN",
            "stale": False,
            "age_seconds": 0,
        }

    age_seconds = _location_age_seconds(loc.get("captured_at"), client_now)
    stale = age_seconds is not None and age_seconds > settings.location_stale_seconds
    if stale:
        return {
            "ok": False,
            "error": "stale_location",
            "stale": True,
            "age_seconds": age_seconds,
            "stale_after_seconds": settings.location_stale_seconds,
            "driver_declared_eta_ts": (declared or {}).get("effective_eta_ts"),
        }

    distance_m = None
    duration_s = None
    provider = "HAVERSINE_FALLBACK"
    provider_error = None
    if settings.geoapify_api_key:
        try:
            url = "https://api.geoapify.com/v1/routing"
            params = {
                "waypoints": f"{loc['latitude']},{loc['longitude']}|{geo['latitude']},{geo['longitude']}",
                "mode": "truck",
                "apiKey": settings.geoapify_api_key,
            }
            with httpx.Client(timeout=20) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                feat = (data.get("features") or [None])[0]
                if feat:
                    props = feat.get("properties") or {}
                    distance_m = props.get("distance")
                    duration_s = props.get("time")
                    provider = "GEOAPIFY"
        except Exception as exc:
            provider = f"GEOAPIFY_FAILED:{exc}"
            provider_error = str(exc)

    if duration_s is None:
        if settings.geoapify_hard_fail:
            return {
                "ok": False,
                "error": "routing_unavailable",
                "provider": provider,
                "provider_error": provider_error,
                "hard_outage": True,
                "driver_declared_eta_ts": (declared or {}).get("effective_eta_ts"),
            }
        from math import radians, cos, sin, asin, sqrt

        def haversine(lat1, lon1, lat2, lon2):
            r = 6371000
            dlat = radians(lat2 - lat1)
            dlon = radians(lon2 - lon1)
            a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
            return 2 * r * asin(sqrt(a))

        distance_m = haversine(loc["latitude"], loc["longitude"], geo["latitude"], geo["longitude"])
        duration_s = distance_m / (40_000 / 3600)

    # Fresh GPS maps onto the classroom clock; remaining = duration - age.
    remaining = float(duration_s) - float(age_seconds or 0)
    if remaining < 0:
        remaining = 0
    route_eta = (datetime.fromisoformat(classroom_now) + timedelta(seconds=remaining)).isoformat()
    route_eta_id = f"RETA-{uuid4().hex[:8].upper()}"
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO route_eta_calculations(
                route_eta_id, thread_id, shipment_id, location_id, provider,
                distance_m, duration_s, route_eta_ts, calculated_at, raw_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                route_eta_id,
                thread_id,
                shipment_id,
                location_id,
                provider,
                distance_m,
                duration_s,
                route_eta,
                now_iso(),
                f"distance_m={distance_m};age_s={age_seconds}",
            ),
        )

    declared_ts = (declared or {}).get("effective_eta_ts")
    return {
        "ok": True,
        "route_eta_id": route_eta_id,
        "provider": provider,
        "distance_m": distance_m,
        "duration_s": duration_s,
        "route_eta_ts": route_eta,
        "driver_declared_eta_ts": declared_ts,
        "eta_source_recommendation": _recommend_source(declared_ts, route_eta),
        "stale": False,
        "age_seconds": age_seconds,
        "degraded": provider.startswith("GEOAPIFY_FAILED") or provider == "HAVERSINE_FALLBACK",
    }


def _location_age_seconds(captured_at: str | None, client_now: str | None) -> float | None:
    """Age is wall-clock (client_now - captured_at), independent of the frozen classroom clock."""
    if not captured_at:
        return None
    try:
        captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        if client_now:
            now = datetime.fromisoformat(client_now.replace("Z", "+00:00"))
        else:
            now = datetime.now(captured.tzinfo) if captured.tzinfo else datetime.now()
        if captured.tzinfo and now.tzinfo is None:
            now = now.replace(tzinfo=captured.tzinfo)
        if now.tzinfo and captured.tzinfo is None:
            captured = captured.replace(tzinfo=now.tzinfo)
        return max(0.0, (now - captured).total_seconds())
    except Exception:
        return None


def _recommend_source(declared: str | None, route_eta: str) -> str:
    if not declared:
        return "ROUTE"
    d = datetime.fromisoformat(declared)
    r = datetime.fromisoformat(route_eta)
    diff_min = abs((d - r).total_seconds()) / 60
    if diff_min <= 15:
        return "EITHER"
    # prefer later (safer) for buffer
    return "ROUTE" if r > d else "DRIVER_DECLARED"


def rank_slots_with_eta_buffers(
    shipment_id: str,
    route_eta_ts: str | None = None,
    declared_eta_ts: str | None = None,
) -> dict[str, Any]:
    from app.services.booking import get_inbound_state

    scheduling_eta = route_eta_ts or declared_eta_ts
    slots = find_feasible_slots(shipment_id, after_ts=scheduling_eta, limit=8)
    for s in slots:
        start = datetime.fromisoformat(s["slot_start_ts"])
        if route_eta_ts:
            buf_r = round((start - datetime.fromisoformat(route_eta_ts)).total_seconds() / 60, 1)
            s["buffer_vs_route_min"] = buf_r
            s["arrival_buffer_min"] = buf_r
        if declared_eta_ts:
            buf_d = round((start - datetime.fromisoformat(declared_eta_ts)).total_seconds() / 60, 1)
            s["buffer_vs_declared_min"] = buf_d
            if not route_eta_ts:
                s["arrival_buffer_min"] = buf_d

    # Ordered first based on Location ETA feasibility (buffer >= 15m), then Driver ETA feasibility, then earliest slot start
    if route_eta_ts and declared_eta_ts:
        slots.sort(
            key=lambda x: (
                -(x.get("buffer_vs_route_min", 0) >= 15),
                -(x.get("buffer_vs_declared_min", 0) >= 0),
                x["slot_start_ts"],
                x.get("buffer_vs_route_min", 0),
            )
        )
    elif route_eta_ts:
        slots.sort(
            key=lambda x: (
                -(x.get("buffer_vs_route_min", 0) >= 15),
                x["slot_start_ts"],
                x.get("buffer_vs_route_min", 0),
            )
        )
    else:
        slots.sort(
            key=lambda x: (
                -(x.get("buffer_vs_declared_min", 0) >= 15),
                x["slot_start_ts"],
                x.get("buffer_vs_declared_min", 0),
            )
        )

    # Waiting projection: old appointment vs best new option relative to ETA
    projected_wait_old_min = None
    projected_wait_new_min = None
    wait_reduced_min = None
    eta_ts = scheduling_eta
    state_rows = get_inbound_state(shipment_id=shipment_id)
    if state_rows and eta_ts:
        st = state_rows[0]
        try:
            eta_dt = datetime.fromisoformat(eta_ts)
            if st.get("slot_start_ts"):
                old_start = datetime.fromisoformat(st["slot_start_ts"])
                # Early → positive wait until slot; late → overrun past slot end
                if eta_dt <= old_start:
                    projected_wait_old_min = round((old_start - eta_dt).total_seconds() / 60, 1)
                elif st.get("slot_end_ts"):
                    old_end = datetime.fromisoformat(st["slot_end_ts"])
                    projected_wait_old_min = round(max(0.0, (eta_dt - old_end).total_seconds() / 60), 1)
                else:
                    projected_wait_old_min = round((eta_dt - old_start).total_seconds() / 60, 1)
            if slots:
                new_start = datetime.fromisoformat(slots[0]["slot_start_ts"])
                projected_wait_new_min = round(max(0.0, (new_start - eta_dt).total_seconds() / 60), 1)
            if projected_wait_old_min is not None and projected_wait_new_min is not None:
                wait_reduced_min = round(projected_wait_old_min - projected_wait_new_min, 1)
        except Exception:
            pass

    return {
        "shipment_id": shipment_id,
        "scheduling_eta_ts": scheduling_eta,
        "driver_declared_eta_ts": declared_eta_ts,
        "route_eta_ts": route_eta_ts,
        "options": slots,
        "projected_wait_old_min": projected_wait_old_min,
        "projected_wait_new_min": projected_wait_new_min,
        "wait_reduced_min": wait_reduced_min,
    }


def get_recent_location_route(
    shipment_id: str | None = None,
    driver_id: str | None = None,
    thread_id: str | None = None,
    max_age_seconds: int = 300,
) -> dict[str, Any] | None:
    """Returns the most recent location & route calculation if taken within max_age_seconds (default 5 minutes)."""
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT r.*, l.latitude, l.longitude, l.accuracy_m, l.captured_at
            FROM route_eta_calculations r
            JOIN location_snapshots l ON l.location_id = r.location_id
            WHERE (r.shipment_id = ? OR r.thread_id = ? OR l.driver_id = ?)
            ORDER BY l.rowid DESC
            LIMIT 1
            """,
            (shipment_id or "", thread_id or "", driver_id or ""),
        ).fetchone()
        if not row:
            return None
        row_dict = row_to_dict(row)
        # Always use browser captured_at (wall clock) for real-time freshness
        capt_at = row_dict.get("captured_at")
        age_s = _location_age_seconds(capt_at, None)
        if age_s is None or age_s > max_age_seconds:
            return None
        return {
            "route_eta_id": row_dict.get("route_eta_id"),
            "route_eta_ts": row_dict.get("route_eta_ts"),
            "provider": row_dict.get("provider"),
            "distance_m": row_dict.get("distance_m"),
            "duration_s": row_dict.get("duration_s"),
            "age_seconds": round(age_s, 1),
            "age_minutes": round(age_s / 60, 1),
            "latitude": row_dict.get("latitude"),
            "longitude": row_dict.get("longitude"),
        }
