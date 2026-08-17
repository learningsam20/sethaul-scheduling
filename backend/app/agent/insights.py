from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, TypedDict
from uuid import uuid4
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph
from langsmith import traceable

from app.config import get_settings
from app.db import db_session, rows_to_dicts
from app.services import metrics as metrics_service
from app.tracing import configure_langsmith

INSIGHT_SYSTEM_PROMPT = """You are SetuHaul's operations insight generator.
You analyze dock-scheduling KPIs and week-over-week movement for a freight network.
Write concise, actionable insights for ops and warehouse leads.

Rules:
- Use only the numbers and scopes provided. Do not invent facilities, drivers, carriers, or rates.
- Prefer operational language: human help, self-service, resolve time, agent fault, first-option accept.
- Call out regressions and improvements with the provided deltas.
- Suggest one concrete next action when severity is warn or danger.
- Return STRICT JSON only — no markdown fences.
"""


def _iso_week() -> str:
    settings = get_settings()
    try:
        dt = datetime.fromisoformat(settings.classroom_now)
    except Exception:
        dt = datetime.now(ZoneInfo("Asia/Kolkata"))
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _refresh_timestamp() -> str:
    """Wall-clock stamp so successive AI refreshes sort correctly (classroom_now is frozen)."""
    return datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds")


def _context_payload(iso_week: str | None = None) -> dict[str, Any]:
    week = iso_week or _iso_week()
    reports = metrics_service.list_weekly_reports(week)
    if not reports:
        metrics_service.generate_weekly_reports(week)
        reports = metrics_service.list_weekly_reports(week)
    health = metrics_service.agent_health()
    slim = []
    for r in reports:
        slim.append(
            {
                "scope_type": r["scope_type"],
                "scope_id": r["scope_id"],
                "iso_week": r["iso_week"],
                "kpi": r.get("kpi") or {},
                "wow": r.get("wow") or {},
                "rule_insights": r.get("insights") or [],
            }
        )
    return {"iso_week": week, "agent_health": health, "scopes": slim}


def _heuristic_insights(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic analyst narrative when LLM is unavailable."""
    out: list[dict[str, Any]] = []
    health = ctx.get("agent_health") or {}
    if health:
        trust = health.get("trust")
        autonomy = health.get("autonomy")
        fit = health.get("fit")
        severity = "ok"
        if (trust is not None and trust < 0.85) or (autonomy is not None and autonomy < 0.5):
            severity = "warn"
        out.append(
            {
                "scope_type": "NETWORK",
                "scope_id": "ALL",
                "title": "Agent health pulse",
                "body": (
                    f"Trust {round((trust or 0) * 100)}%, autonomy {round((autonomy or 0) * 100)}%, "
                    f"fit {round((fit or 0) * 100)}% across {health.get('cases', 0)} cases. "
                    + (
                        "Prioritize guardrail failures and high human-help threads."
                        if severity == "warn"
                        else "Network is holding steady — keep monitoring first-option accept."
                    )
                ),
                "severity": severity,
            }
        )

    for scope in ctx.get("scopes") or []:
        wow = scope.get("wow") or {}
        kpi = scope.get("kpi") or {}
        if scope["scope_type"] not in ("NETWORK", "FACILITY", "OPS", "CARRIER"):
            continue
        hh = wow.get("human_help_rate") or {}
        ss = wow.get("self_service_rate") or {}
        ar = wow.get("avg_resolve_min") or {}
        if hh.get("delta") is not None and hh["delta"] > 0.05:
            out.append(
                {
                    "scope_type": scope["scope_type"],
                    "scope_id": scope["scope_id"],
                    "title": "Human help rising",
                    "body": (
                        f"Human-help rate moved to {hh.get('current')} from {hh.get('previous')} "
                        f"(Δ {hh.get('delta')}). Review clarification loops and pending warehouse confirms."
                    ),
                    "severity": "warn",
                }
            )
        if ss.get("delta") is not None and ss["delta"] < -0.05:
            out.append(
                {
                    "scope_type": scope["scope_type"],
                    "scope_id": scope["scope_id"],
                    "title": "Self-service slipping",
                    "body": (
                        f"Self-service fell to {ss.get('current')} (Δ {ss.get('delta')}). "
                        f"Cases this week: {kpi.get('cases', 0)}."
                    ),
                    "severity": "warn",
                }
            )
        if ar.get("delta") is not None and ar["delta"] > 2:
            out.append(
                {
                    "scope_type": scope["scope_type"],
                    "scope_id": scope["scope_id"],
                    "title": "Resolve time stretched",
                    "body": (
                        f"Avg resolve {ar.get('current')}m vs {ar.get('previous')}m "
                        f"(Δ {ar.get('delta')}m). Check dock conflicts and late ETAs."
                    ),
                    "severity": "danger",
                }
            )
        if hh.get("delta") is not None and hh["delta"] < -0.05:
            out.append(
                {
                    "scope_type": scope["scope_type"],
                    "scope_id": scope["scope_id"],
                    "title": "Human help improving",
                    "body": (
                        f"Human-help improved to {hh.get('current')} (Δ {hh.get('delta')}). "
                        "Keep the current clarification and booking pattern."
                    ),
                    "severity": "ok",
                }
            )

    # de-dupe / cap
    seen = set()
    unique = []
    for item in out:
        key = (item["scope_type"], item["scope_id"], item["title"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:10] or [
        {
            "scope_type": "NETWORK",
            "scope_id": "ALL",
            "title": "No strong movement yet",
            "body": "Week-over-week deltas are quiet. Generate Weekly WoW after more exception traffic, then refresh AI insights.",
            "severity": "info",
        }
    ]


def _normalize_insight_item(item: dict[str, Any]) -> dict[str, Any] | None:
    title = str(item.get("title") or "").strip()
    body = str(item.get("body") or item.get("text") or "").strip()
    if not title or not body:
        return None
    severity = str(item.get("severity") or "info").lower()
    if severity not in ("info", "ok", "warn", "danger"):
        severity = "info"
    return {
        "scope_type": str(item.get("scope_type") or "NETWORK").upper(),
        "scope_id": str(item.get("scope_id") or "ALL"),
        "title": title[:120],
        "body": body[:600],
        "severity": severity,
    }


def _parse_llm_json(text: str) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    data: Any = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Free models often emit NDJSON / one object per line / concatenated objects.
        objects: list[Any] = []
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(raw):
            while idx < len(raw) and raw[idx].isspace():
                idx += 1
            if idx >= len(raw):
                break
            try:
                obj, end = decoder.raw_decode(raw, idx)
            except json.JSONDecodeError:
                break
            objects.append(obj)
            idx = end
        if len(objects) == 1 and isinstance(objects[0], list):
            data = objects[0]
        elif objects:
            data = objects
        else:
            raise

    if isinstance(data, dict):
        if any(k in data for k in ("title", "body", "text")):
            data = [data]
        else:
            data = data.get("insights") or data.get("items") or []
    if not isinstance(data, list):
        raise ValueError("Insights payload is not a list")

    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            continue
        norm = _normalize_insight_item(item)
        if norm:
            cleaned.append(norm)
    return cleaned


def _friendly_llm_error(exc: Exception | str) -> str:
    text = str(exc)
    lower = text.lower()
    if "402" in text or "insufficient credits" in lower:
        return (
            "OpenRouter credits insufficient for this model — showing heuristic insights. "
            "Use a free model (e.g. openrouter/free) or add credits."
        )
    if "401" in text or "unauthorized" in lower or "invalid api key" in lower:
        return "OpenRouter API key rejected — showing heuristic insights."
    if "model" in lower and ("not found" in lower or "does not exist" in lower):
        return "OpenRouter model unavailable — showing heuristic insights. Check OPENROUTER_MODEL."
    return "LLM unavailable — showing heuristic insights."


@traceable(name="llm_generate_insights", run_type="chain", tags=["setuhaul", "llm", "insights"])
def _llm_insights(ctx: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, str | None, str | None]:
    settings = get_settings()
    if not settings.openrouter_api_key:
        return None, None, "OPENROUTER_API_KEY not configured — showing heuristic insights"
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        configure_langsmith()

        llm = ChatOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=settings.openrouter_model,
            temperature=0.2,
            timeout=60,
        )
        prompt = (
            "Given this SetuHaul weekly analytics context, produce 4-8 insights.\n"
            "Return ONLY a JSON array (not NDJSON) of objects with keys: "
            "scope_type, scope_id, title, body, severity (info|ok|warn|danger).\n"
            'Example: [{"scope_type":"NETWORK","scope_id":"ALL","title":"...","body":"...","severity":"warn"}]\n\n'
            f"CONTEXT:\n{json.dumps(ctx, ensure_ascii=True)[:12000]}"
        )
        resp = llm.invoke([SystemMessage(content=INSIGHT_SYSTEM_PROMPT), HumanMessage(content=prompt)])
        content = getattr(resp, "content", "") or ""
        insights = _parse_llm_json(content)
        if not insights:
            return None, settings.openrouter_model, "Model returned no usable insights — showing heuristic insights"
        return insights, settings.openrouter_model, None
    except Exception as exc:  # noqa: BLE001 — surface model/provider failures to caller
        return None, settings.openrouter_model, _friendly_llm_error(exc)


class InsightsState(TypedDict, total=False):
    actor_user_id: str | None
    iso_week: str | None
    ctx: dict[str, Any]
    insights: list[dict[str, Any]]
    model: str | None
    source: str
    note: str | None
    run_id: str
    last_refreshed_at: str


def _node_gather(state: InsightsState) -> dict[str, Any]:
    return {"ctx": _context_payload(state.get("iso_week"))}


def _node_generate(state: InsightsState) -> dict[str, Any]:
    ctx = state["ctx"]
    llm_insights, model, llm_error = _llm_insights(ctx)
    if llm_insights:
        return {"insights": llm_insights, "model": model, "source": "ai", "note": None}
    return {
        "insights": _heuristic_insights(ctx),
        "model": model or "heuristic",
        "source": "heuristic",
        "note": llm_error or "LLM unavailable — persisted heuristic analyst insights",
    }


def _node_persist(state: InsightsState) -> dict[str, Any]:
    week = (state.get("ctx") or {}).get("iso_week") or _iso_week()
    ts = _refresh_timestamp()
    run_id = f"AIR-{uuid4().hex[:10].upper()}"
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO ai_insight_runs(run_id, iso_week, model, insights_json, last_refreshed_at, actor_user_id, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                week,
                state.get("model"),
                json.dumps(state.get("insights") or []),
                ts,
                state.get("actor_user_id"),
                state.get("note"),
            ),
        )
    return {"run_id": run_id, "last_refreshed_at": ts, "iso_week": week}


def build_insights_graph():
    g = StateGraph(InsightsState)
    g.add_node("gather_context", _node_gather)
    g.add_node("generate_insights", _node_generate)
    g.add_node("persist", _node_persist)
    g.add_edge(START, "gather_context")
    g.add_edge("gather_context", "generate_insights")
    g.add_edge("generate_insights", "persist")
    g.add_edge("persist", END)
    return g.compile(name="setuhaul_insights_agent")


_INSIGHTS_GRAPH = None


def get_insights_graph():
    global _INSIGHTS_GRAPH
    if _INSIGHTS_GRAPH is None:
        _INSIGHTS_GRAPH = build_insights_graph()
    return _INSIGHTS_GRAPH


def generate_ai_insights(actor_user_id: str | None = None, iso_week: str | None = None) -> dict[str, Any]:
    configure_langsmith()
    final = get_insights_graph().invoke(
        {"actor_user_id": actor_user_id, "iso_week": iso_week},
        config={
            "run_name": "setuhaul_insights_agent",
            "tags": ["setuhaul", "langgraph", "insights"],
        },
    )
    week = final.get("iso_week") or ((final.get("ctx") or {}).get("iso_week"))
    return {
        "run_id": final.get("run_id"),
        "iso_week": week,
        "model": final.get("model"),
        "source": final.get("source"),
        "note": final.get("note"),
        "insights": final.get("insights") or [],
        "last_refreshed_at": final.get("last_refreshed_at"),
        "trace": {"agent": "setuhaul_insights_agent", "framework": "langgraph"},
    }


def latest_ai_insights(iso_week: str | None = None) -> dict[str, Any]:
    week = iso_week or _iso_week()
    with db_session() as conn:
        # table may not exist yet on older DBs before migration apply
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_insight_runs'"
        ).fetchone()
        if not exists:
            return {"iso_week": week, "insights": [], "last_refreshed_at": None, "model": None, "source": None, "note": None}
        # Prefer rowid: classroom_now made many rows share the same last_refreshed_at.
        row = conn.execute(
            """
            SELECT * FROM ai_insight_runs
            WHERE iso_week = ?
            ORDER BY rowid DESC
            LIMIT 1
            """,
            (week,),
        ).fetchone()
        if not row:
            # fall back to newest run overall
            row = conn.execute(
                "SELECT * FROM ai_insight_runs ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
    if not row:
        return {"iso_week": week, "insights": [], "last_refreshed_at": None, "model": None, "source": None, "note": None}
    data = dict(row)
    insights = json.loads(data.get("insights_json") or "[]")
    model = data.get("model")
    note = data.get("note")
    source = "ai" if not note and model and model != "heuristic" else "heuristic"
    return {
        "run_id": data.get("run_id"),
        "iso_week": data.get("iso_week") or week,
        "insights": insights,
        "last_refreshed_at": data.get("last_refreshed_at"),
        "model": model,
        "source": source,
        "note": note,
    }


def list_ai_insight_history(limit: int = 10) -> list[dict[str, Any]]:
    with db_session() as conn:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_insight_runs'"
        ).fetchone()
        if not exists:
            return []
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT run_id, iso_week, model, last_refreshed_at, actor_user_id, note
                FROM ai_insight_runs
                ORDER BY rowid DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        )
    return rows
