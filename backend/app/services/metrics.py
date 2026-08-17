from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from app.db import db_session, get_setting, now_iso, rows_to_dicts, row_to_dict


def ensure_case_metric(
    thread_id: str,
    shipment_id: str | None,
    driver_id: str | None,
    facility_id: str | None,
    carrier_id: str | None,
    conn=None,
) -> None:
    def _write(c) -> None:
        existing = c.execute("SELECT case_id FROM case_metrics WHERE thread_id=?", (thread_id,)).fetchone()
        if existing:
            return
        ts = now_iso()
        c.execute(
            """
            INSERT INTO case_metrics(
                case_id, thread_id, shipment_id, driver_id, facility_id, carrier_id,
                started_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (f"CASE-{uuid4().hex[:10].upper()}", thread_id, shipment_id, driver_id, facility_id, carrier_id, ts, ts, ts),
        )

    if conn is not None:
        _write(conn)
        return
    with db_session() as c:
        _write(c)


def bump_clarification(thread_id: str) -> None:
    with db_session() as conn:
        conn.execute(
            """
            UPDATE case_metrics
            SET clarification_turns = clarification_turns + 1, updated_at=?
            WHERE thread_id=?
            """,
            (now_iso(), thread_id),
        )


def mark_human_help(thread_id: str) -> None:
    with db_session() as conn:
        conn.execute(
            "UPDATE case_metrics SET human_help=1, updated_at=? WHERE thread_id=?",
            (now_iso(), thread_id),
        )


def resolve_case(thread_id: str, outcome_status: str, first_option_accepted: bool | None = None) -> None:
    with db_session() as conn:
        conn.execute(
            """
            UPDATE case_metrics
            SET resolved_at=?, outcome_status=?, first_option_accepted=COALESCE(?, first_option_accepted), updated_at=?
            WHERE thread_id=?
            """,
            (now_iso(), outcome_status, None if first_option_accepted is None else int(first_option_accepted), now_iso(), thread_id),
        )


def record_turn_eval(thread_id: str, turn_index: int, flags: dict[str, Any]) -> None:
    with db_session() as conn:
        fails = int(flags.get("invented_slot", 0)) + int(flags.get("skipped_tool", 0)) + int(flags.get("invalid_book_attempt", 0))
        conn.execute(
            """
            INSERT INTO agent_turn_evals(
                eval_id, thread_id, turn_index, invented_slot, skipped_tool, invalid_book_attempt,
                tool_grounding_score, langsmith_run_id, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"EV-{uuid4().hex[:10].upper()}",
                thread_id,
                turn_index,
                int(flags.get("invented_slot", 0)),
                int(flags.get("skipped_tool", 0)),
                int(flags.get("invalid_book_attempt", 0)),
                flags.get("tool_grounding_score"),
                flags.get("langsmith_run_id"),
                flags.get("notes"),
                now_iso(),
            ),
        )
        if fails:
            conn.execute(
                """
                UPDATE case_metrics
                SET agent_fault=1, hard_gate_fails = hard_gate_fails + ?, updated_at=?
                WHERE thread_id=?
                """,
                (fails, now_iso(), thread_id),
            )


def record_predicted_eta(thread_id: str, predicted_eta_ts: str, source: str = "DRIVER_DECLARED") -> None:
    with db_session() as conn:
        conn.execute(
            """
            UPDATE case_metrics
            SET predicted_eta_ts=?, eta_source_used=?, updated_at=?
            WHERE thread_id=?
            """,
            (predicted_eta_ts, source, now_iso(), thread_id),
        )


def record_options_generated(thread_id: str, options: list[dict[str, Any]]) -> None:
    """Stamp when options were shown and remember slot ids so later capacity cuts can mark them stale."""
    ts = now_iso()
    slot_ids = [o.get("slot_id") for o in (options or []) if o.get("slot_id")]
    with db_session() as conn:
        conn.execute(
            """
            UPDATE case_metrics
            SET options_generated_at=?, displayed_options_json=?, options_stale=0, updated_at=?
            WHERE thread_id=?
            """,
            (ts, json.dumps(slot_ids), ts, thread_id),
        )


def get_displayed_slot_ids(thread_id: str) -> list[str]:
    """Retrieve the slot IDs that were displayed to the driver in this thread."""
    with db_session() as conn:
        row = conn.execute("SELECT displayed_options_json FROM case_metrics WHERE thread_id=?", (thread_id,)).fetchone()
        if row and row["displayed_options_json"]:
            try:
                return json.loads(row["displayed_options_json"])
            except Exception:
                return []
    return []


def mark_options_stale_for_slots(slot_ids: list[str]) -> int:
    if not slot_ids:
        return 0
    with db_session() as conn:
        cases = rows_to_dicts(
            conn.execute(
                "SELECT thread_id, displayed_options_json FROM case_metrics WHERE displayed_options_json IS NOT NULL"
            ).fetchall()
        )
        n = 0
        wanted = set(slot_ids)
        for c in cases:
            try:
                shown = set(json.loads(c["displayed_options_json"] or "[]"))
            except Exception:
                continue
            if shown & wanted:
                conn.execute(
                    "UPDATE case_metrics SET options_stale=1, updated_at=? WHERE thread_id=?",
                    (now_iso(), c["thread_id"]),
                )
                n += 1
        return n


def options_are_stale(thread_id: str) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT options_stale FROM case_metrics WHERE thread_id=?", (thread_id,)
        ).fetchone()
        return bool(row and row["options_stale"])


STALE_OPTIONS_WARNING = (
    "Those earlier options are stale — a slot was cancelled or a dock went down. "
    "Shown ≠ held ≠ confirmed. Use only the updated list."
)


def record_wait_projection(
    thread_id: str,
    old_wait_min: float | None,
    new_wait_min: float | None,
    predicted_eta_ts: str | None = None,
    eta_source: str | None = None,
) -> None:
    with db_session() as conn:
        fields = ["projected_wait_old_min=?", "projected_wait_new_min=?", "updated_at=?"]
        params: list[Any] = [old_wait_min, new_wait_min, now_iso()]
        if predicted_eta_ts:
            fields.append("predicted_eta_ts=COALESCE(?, predicted_eta_ts)")
            params.append(predicted_eta_ts)
        if eta_source:
            fields.append("eta_source_used=COALESCE(?, eta_source_used)")
            params.append(eta_source)
        params.append(thread_id)
        conn.execute(f"UPDATE case_metrics SET {', '.join(fields)} WHERE thread_id=?", params)


def record_carrier_fairness(carrier_id: str, facility_id: str, slots_assigned: int) -> None:
    with db_session() as conn:
        case_id = f"CASE-{uuid4().hex[:10].upper()}"
        conn.execute(
            """
            INSERT INTO case_metrics(
                case_id, thread_id, carrier_id, facility_id, started_at, created_at, updated_at
            ) VALUES (?, NULL, ?, ?, ?, ?, ?)
            """,
            (case_id, carrier_id, facility_id, now_iso(), now_iso(), now_iso()),
        )


def sync_gate_in_times() -> int:
    """Backfill actual_gate_in_ts from facility_checkins for ETA-error KPI."""
    with db_session() as conn:
        cur = conn.execute(
            """
            UPDATE case_metrics
            SET actual_gate_in_ts = (
                SELECT fc.gate_in_ts FROM facility_checkins fc
                WHERE fc.shipment_id = case_metrics.shipment_id
                  AND fc.gate_in_ts IS NOT NULL
                ORDER BY fc.gate_in_ts DESC LIMIT 1
            ),
            updated_at = ?
            WHERE shipment_id IS NOT NULL
              AND (actual_gate_in_ts IS NULL OR actual_gate_in_ts = '')
              AND EXISTS (
                SELECT 1 FROM facility_checkins fc
                WHERE fc.shipment_id = case_metrics.shipment_id AND fc.gate_in_ts IS NOT NULL
              )
            """,
            (now_iso(),),
        )
        return cur.rowcount or 0


def _eta_error_min(case: dict[str, Any]) -> float | None:
    pred = case.get("predicted_eta_ts")
    actual = case.get("actual_gate_in_ts")
    if not pred or not actual:
        return None
    try:
        return abs((datetime.fromisoformat(actual) - datetime.fromisoformat(pred)).total_seconds() / 60)
    except Exception:
        return None


def _wait_reduced_min(case: dict[str, Any]) -> float | None:
    old = case.get("projected_wait_old_min")
    new = case.get("projected_wait_new_min")
    if old is None or new is None:
        return None
    try:
        return float(old) - float(new)
    except Exception:
        return None


def agent_health(facility_id: str | None = None) -> dict[str, Any]:
    sync_gate_in_times()
    with db_session() as conn:
        sql = "SELECT * FROM case_metrics WHERE 1=1"
        params: list[Any] = []
        if facility_id:
            sql += " AND facility_id = ?"
            params.append(facility_id)
        cases = rows_to_dicts(conn.execute(sql, params).fetchall())
    total = len(cases) or 1
    trust = 1 - (sum(1 for c in cases if c["agent_fault"]) / total)
    autonomy = sum(1 for c in cases if c["resolved_at"] and not c["human_help"]) / total
    accepted = [c for c in cases if c["first_option_accepted"] is not None]
    fit = (sum(c["first_option_accepted"] for c in accepted) / len(accepted)) if accepted else 0
    eta_errors = [e for e in (_eta_error_min(c) for c in cases) if e is not None]
    wait_reduced = [w for w in (_wait_reduced_min(c) for c in cases) if w is not None]
    resolved = [c for c in cases if c.get("resolved_at")]
    resolve_times = []
    for c in resolved:
        try:
            resolve_times.append(
                (datetime.fromisoformat(c["resolved_at"]) - datetime.fromisoformat(c["started_at"])).total_seconds() / 60
            )
        except Exception:
            pass
    avg_resolve = round(sum(resolve_times) / len(resolve_times), 1) if resolve_times else 0.0
    self_service_rate = round(sum(1 for c in resolved if not c["human_help"]) / (len(resolved) or 1), 3)
    return {
        "trust": round(trust, 3),
        "autonomy": round(autonomy, 3),
        "fit": round(fit, 3),
        "cases": len(cases),
        "resolved_cases": len(resolved),
        "human_help_rate": round(sum(c["human_help"] for c in cases) / total, 3),
        "self_service_rate": self_service_rate,
        "avg_resolve_min": avg_resolve,
        "avg_eta_error_min": round(sum(eta_errors) / len(eta_errors), 1) if eta_errors else None,
        "eta_error_samples": len(eta_errors),
        "avg_wait_reduced_min": round(sum(wait_reduced) / len(wait_reduced), 1) if wait_reduced else None,
        "wait_reduced_samples": len(wait_reduced),
    }


def _iso_week(ts: str) -> str:
    d = datetime.fromisoformat(ts)
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


DEFAULT_MANUAL_BASELINE = {
    "human_help_rate": 1.0,
    "self_service_rate": 0.0,
    "avg_resolve_min": 45.0,
    "first_option_accept_rate": 0.35,
    "avg_eta_error_min": 40.0,
    "avg_wait_reduced_min": 0.0,
}


def load_manual_baseline(conn, scope: str = "NETWORK") -> dict[str, Any]:
    row = conn.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = ?", ("manual_baseline",)
    ).fetchone()
    if not row or not row["setting_value"]:
        return dict(DEFAULT_MANUAL_BASELINE)
    try:
        data = json.loads(row["setting_value"])
        if isinstance(data, dict):
            merged = dict(DEFAULT_MANUAL_BASELINE)
            merged.update({k: v for k, v in data.items() if k in merged})
            return merged
    except Exception:
        pass
    return dict(DEFAULT_MANUAL_BASELINE)


def vs_manual(kpi: dict[str, Any], baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    """Controlled before/after: current solution vs a documented manual-process baseline."""
    if baseline is None:
        baseline = DEFAULT_MANUAL_BASELINE
    out: dict[str, Any] = {}
    for key, manual in baseline.items():
        cur = kpi.get(key)
        if isinstance(cur, (int, float)):
            out[key] = {
                "current": cur,
                "manual": manual,
                "delta": round(cur - manual, 3),
            }
    return out


def cloudwatch_metric_data(facility_id: str | None = None) -> dict[str, Any]:
    """PutMetricData-shaped payload for a CloudWatch dashboard (or local scrape)."""
    health = agent_health(facility_id)
    ts = now_iso()
    namespace = "SetuHaul/Agent"
    dims = [{"Name": "Facility", "Value": facility_id or "NETWORK"}]
    metrics = []
    for name, key in (
        ("Trust", "trust"),
        ("Autonomy", "autonomy"),
        ("Fit", "fit"),
        ("HumanHelpRate", "human_help_rate"),
        ("SelfServiceRate", "self_service_rate"),
        ("AvgResolveMin", "avg_resolve_min"),
        ("AvgEtaErrorMin", "avg_eta_error_min"),
        ("AvgWaitReducedMin", "avg_wait_reduced_min"),
        ("Cases", "cases"),
    ):
        val = health.get(key)
        if val is None:
            continue
        metrics.append(
            {
                "MetricName": name,
                "Dimensions": dims,
                "Timestamp": ts,
                "Value": float(val),
                "Unit": "Count" if name == "Cases" else "None",
            }
        )
    return {"Namespace": namespace, "MetricData": metrics, "health": health}


def push_cloudwatch_metrics(facility_id: str | None = None) -> dict[str, Any]:
    """Push PutMetricData when boto3 + AWS creds are present; otherwise return the scrape payload."""
    import os
    from datetime import datetime, timezone

    payload = cloudwatch_metric_data(facility_id)
    scrape = "GET /api/analytics/cloudwatch-metrics"
    try:
        import boto3  # type: ignore
    except ImportError:
        return {
            "ok": False,
            "pushed": False,
            "reason": "boto3_not_installed",
            "scrape_path": scrape,
            "payload": payload,
        }
    wall = datetime.now(timezone.utc)
    metric_data = []
    for m in payload.get("MetricData") or []:
        item = dict(m)
        item["Timestamp"] = wall
        metric_data.append(item)
    if not metric_data:
        return {"ok": False, "pushed": False, "reason": "no_metric_samples", "scrape_path": scrape, "payload": payload}
    try:
        client = boto3.client("cloudwatch", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
        client.put_metric_data(Namespace=payload["Namespace"], MetricData=metric_data)
        return {
            "ok": True,
            "pushed": True,
            "count": len(metric_data),
            "namespace": payload["Namespace"],
            "scrape_path": scrape,
        }
    except Exception as exc:
        return {
            "ok": False,
            "pushed": False,
            "reason": str(exc),
            "scrape_path": scrape,
            "payload": payload,
        }


def generate_weekly_reports(iso_week: str | None = None) -> list[dict[str, Any]]:
    sync_gate_in_times()
    with db_session() as conn:
        cases = rows_to_dicts(conn.execute("SELECT * FROM case_metrics").fetchall())
        classroom_now = get_setting(conn, "classroom_now", now_iso()) or now_iso()
    if not iso_week:
        iso_week = _iso_week(classroom_now)

    # previous week label
    d = datetime.fromisoformat(classroom_now)
    prev = d - timedelta(days=7)
    prev_week = f"{prev.isocalendar()[0]}-W{prev.isocalendar()[1]:02d}"

    def week_cases(week: str, predicate=lambda c: True):
        return [c for c in cases if c.get("started_at") and _iso_week(c["started_at"]) == week and predicate(c)]

    def kpis(rows: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(rows) or 1
        resolved = [c for c in rows if c.get("resolved_at")]
        def avg_resolve(rs):
            vals = []
            for c in rs:
                try:
                    vals.append(
                        (datetime.fromisoformat(c["resolved_at"]) - datetime.fromisoformat(c["started_at"])).total_seconds()
                        / 60
                    )
                except Exception:
                    pass
            return round(sum(vals) / len(vals), 1) if vals else None

        eta_errors = [e for e in (_eta_error_min(c) for c in rows) if e is not None]
        wait_reduced = [w for w in (_wait_reduced_min(c) for c in rows) if w is not None]
        return {
            "cases": len(rows),
            "resolved": len(resolved),
            "human_help_rate": round(sum(c["human_help"] for c in rows) / n, 3),
            "self_service_rate": round(sum(1 for c in resolved if not c["human_help"]) / (len(resolved) or 1), 3),
            "avg_resolve_min": avg_resolve(resolved),
            "agent_fault_rate": round(sum(c["agent_fault"] for c in rows) / n, 3),
            "first_option_accept_rate": round(
                sum(c["first_option_accepted"] or 0 for c in rows if c["first_option_accepted"] is not None)
                / (sum(1 for c in rows if c["first_option_accepted"] is not None) or 1),
                3,
            ),
            "avg_eta_error_min": round(sum(eta_errors) / len(eta_errors), 1) if eta_errors else None,
            "eta_error_samples": len(eta_errors),
            "avg_wait_reduced_min": round(sum(wait_reduced) / len(wait_reduced), 1) if wait_reduced else None,
            "wait_reduced_samples": len(wait_reduced),
        }

    def wow(curr: dict[str, Any], prev: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for key in curr:
            if isinstance(curr[key], (int, float)) and isinstance(prev.get(key), (int, float)):
                delta = curr[key] - prev[key]
                out[key] = {"current": curr[key], "previous": prev[key], "delta": round(delta, 3)}
            elif curr[key] is not None and key.startswith("avg_"):
                out[key] = {"current": curr[key], "previous": prev.get(key), "delta": None}
        return out

    reports = []
    scopes: list[tuple[str, str, Any]] = [("NETWORK", "ALL", lambda c: True)]
    facilities = {c["facility_id"] for c in cases if c.get("facility_id")}
    for f in facilities:
        scopes.append(("FACILITY", f, lambda c, fid=f: c.get("facility_id") == fid))
    drivers = {c["driver_id"] for c in cases if c.get("driver_id")}
    for d_id in drivers:
        scopes.append(("DRIVER", d_id, lambda c, did=d_id: c.get("driver_id") == did))
    carriers = {c["carrier_id"] for c in cases if c.get("carrier_id")}
    for car in carriers:
        scopes.append(("CARRIER", car, lambda c, cid=car: c.get("carrier_id") == cid))
    scopes.append(("OPS", "NETWORK", lambda c: True))

    with db_session() as conn:
        for scope_type, scope_id, pred in scopes:
            curr_rows = week_cases(iso_week, pred)
            prev_rows = week_cases(prev_week, pred)
            kpi = kpis(curr_rows)
            prev_kpi = kpis(prev_rows)
            deltas = wow(kpi, prev_kpi)
            baseline = load_manual_baseline(conn, scope_type)
            deltas["vs_manual"] = vs_manual(kpi, baseline)
            insights = []
            for key, val in deltas.items():
                if isinstance(val, dict) and val.get("delta") is not None:
                    delta_val = val["delta"]
                    if key.endswith("_rate") or key == "avg_resolve_min":
                        if delta_val < -0.05 or (key == "avg_resolve_min" and delta_val < -2):
                            insights.append(f"{scope_type}:{scope_id} improved on {key} (Δ {delta_val})")
                        elif delta_val > 0.05 or (key == "avg_resolve_min" and delta_val > 2):
                            insights.append(f"{scope_type}:{scope_id} regressed on {key} (Δ {delta_val})")
            report_id = f"WR-{uuid4().hex[:10].upper()}"
            conn.execute(
                """
                INSERT OR REPLACE INTO weekly_report_snapshots(
                    report_id, iso_week, scope_type, scope_id, kpi_json, wow_json, insights_json, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    iso_week,
                    scope_type,
                    scope_id,
                    json.dumps(kpi),
                    json.dumps(deltas),
                    json.dumps(insights),
                    now_iso(),
                ),
            )
            reports.append(
                {
                    "report_id": report_id,
                    "iso_week": iso_week,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "kpi": kpi,
                    "wow": deltas,
                    "insights": insights,
                }
            )
    return reports


def list_weekly_reports(iso_week: str | None = None, scope_type: str | None = None) -> list[dict[str, Any]]:
    with db_session() as conn:
        sql = "SELECT * FROM weekly_report_snapshots WHERE 1=1"
        params: list[Any] = []
        if iso_week:
            sql += " AND iso_week = ?"
            params.append(iso_week)
        if scope_type:
            sql += " AND scope_type = ?"
            params.append(scope_type)
        sql += " ORDER BY scope_type, scope_id"
        rows = rows_to_dicts(conn.execute(sql, params).fetchall())
    for r in rows:
        r["kpi"] = json.loads(r.pop("kpi_json") or "{}")
        r["wow"] = json.loads(r.pop("wow_json") or "{}")
        r["insights"] = json.loads(r.pop("insights_json") or "[]")
    return rows
