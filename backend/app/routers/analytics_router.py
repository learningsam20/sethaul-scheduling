from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.agent import insights as insight_agent
from app.auth import CurrentUser
from app.services import metrics as metrics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _require_ops_admin(user: dict[str, Any]) -> None:
    if user["role"] not in ("OPERATIONS", "ADMIN"):
        raise HTTPException(403, "Ops/Admin only")


@router.get("/health")
def health(user: CurrentUser, facility_id: str | None = None) -> dict[str, Any]:
    _require_ops_admin(user)
    return metrics_service.agent_health(facility_id)


@router.get("/cloudwatch-metrics")
def cloudwatch_metrics(user: CurrentUser, facility_id: str | None = None) -> dict[str, Any]:
    """CloudWatch PutMetricData-shaped snapshot (push from T1 deploy or scrape locally)."""
    _require_ops_admin(user)
    return metrics_service.cloudwatch_metric_data(facility_id)


@router.post("/cloudwatch-metrics/push")
def cloudwatch_metrics_push(user: CurrentUser, facility_id: str | None = None) -> dict[str, Any]:
    """Best-effort PutMetricData. Without boto3/AWS creds, returns the scrape payload instead."""
    _require_ops_admin(user)
    return metrics_service.push_cloudwatch_metrics(facility_id)


@router.post("/weekly/generate")
def weekly_generate(user: CurrentUser, iso_week: str | None = None) -> dict[str, Any]:
    _require_ops_admin(user)
    reports = metrics_service.generate_weekly_reports(iso_week)
    return {"count": len(reports), "reports": reports}


@router.get("/weekly")
def weekly_list(
    user: CurrentUser,
    iso_week: str | None = None,
    scope_type: str | None = None,
) -> dict[str, Any]:
    role = user["role"]
    if role == "DRIVER":
        reports = [
            r
            for r in metrics_service.list_weekly_reports(iso_week, "DRIVER")
            if r["scope_id"] == user.get("driver_id")
        ]
        return {"reports": reports}
    if role == "CARRIER":
        reports = [
            r
            for r in metrics_service.list_weekly_reports(iso_week, "CARRIER")
            if r["scope_id"] == user.get("carrier_id")
        ]
        return {"reports": reports}
    if role == "WAREHOUSE":
        reports = [
            r
            for r in metrics_service.list_weekly_reports(iso_week, "FACILITY")
            if r["scope_id"] == user.get("facility_id")
        ]
        return {"reports": reports}
    if role not in ("OPERATIONS", "ADMIN"):
        raise HTTPException(403, "Not allowed")
    return {"reports": metrics_service.list_weekly_reports(iso_week, scope_type)}


@router.post("/insights/refresh")
def insights_refresh(user: CurrentUser, iso_week: str | None = None) -> dict[str, Any]:
    """On-demand insight generator agent — persists AI (or heuristic fallback) insights."""
    _require_ops_admin(user)
    result = insight_agent.generate_ai_insights(actor_user_id=user["user_id"], iso_week=iso_week)
    return {"ok": True, **result}


@router.get("/insights")
def insights_list(user: CurrentUser, iso_week: str | None = None) -> dict[str, Any]:
    role = user["role"]
    latest = insight_agent.latest_ai_insights(iso_week)
    insights = latest.get("insights") or []
    if role == "DRIVER":
        insights = [i for i in insights if i.get("scope_type") == "DRIVER" and i.get("scope_id") == user.get("driver_id")]
    elif role == "CARRIER":
        insights = [i for i in insights if i.get("scope_type") == "CARRIER" and i.get("scope_id") == user.get("carrier_id")]
    elif role == "WAREHOUSE":
        insights = [
            i
            for i in insights
            if (
                (i.get("scope_type") == "FACILITY" and i.get("scope_id") == user.get("facility_id"))
                or i.get("scope_type") == "NETWORK"
            )
        ]
    elif role not in ("OPERATIONS", "ADMIN"):
        raise HTTPException(403, "Not allowed")
    return {
        "insights": insights,
        "last_refreshed_at": latest.get("last_refreshed_at"),
        "iso_week": latest.get("iso_week"),
        "model": latest.get("model"),
        "source": latest.get("source"),
        "note": latest.get("note"),
        "run_id": latest.get("run_id"),
    }
