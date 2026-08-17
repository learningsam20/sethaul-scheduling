"""Turn tool JSON / leaked structured output into driver-facing markdown tables."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

FIELD_LABELS = {
    "shipment_id": "Shipment",
    "driver_id": "Driver",
    "vehicle_id": "Vehicle",
    "destination_facility_id": "Facility",
    "priority_code": "Priority",
    "required_dock_type": "Dock type",
    "temperature_control_required": "Reefer",
    "load_weight_kg": "Weight (kg)",
    "expected_unload_min": "Unload (min)",
    "current_status": "Status",
    "effective_eta_ts": "ETA",
    "eta_source": "ETA source",
    "eta_confidence": "ETA confidence",
    "appointment_id": "Appointment",
    "slot_id": "Slot",
    "slot_start_ts": "Slot start",
    "slot_end_ts": "Slot end",
    "planned_dock_code": "Planned dock",
    "gate_in_ts": "Gate-in",
    "queue_state": "Queue",
    "queue_position": "Queue position",
    "actual_dock_code": "Actual dock",
    "feasible": "Feasible",
    "reason": "Reason",
    "customer_name": "Customer",
    "product_category": "Product",
    "original_eta_ts": "Original ETA",
    "latest_eta_ts": "Latest ETA",
    "dock_code": "Dock",
    "arrival_buffer_min": "Buffer (min)",
    "requires_manual_approval": "Needs approval",
    "count": "Count",
}

INBOUND_ORDER = [
    "shipment_id",
    "current_status",
    "priority_code",
    "destination_facility_id",
    "required_dock_type",
    "planned_dock_code",
    "slot_start_ts",
    "slot_end_ts",
    "effective_eta_ts",
    "eta_source",
    "eta_confidence",
    "appointment_id",
    "slot_id",
    "load_weight_kg",
    "expected_unload_min",
    "temperature_control_required",
    "driver_id",
    "vehicle_id",
    "gate_in_ts",
    "queue_state",
    "queue_position",
    "actual_dock_code",
]

LIST_PREVIEW_COLS = [
    ("shipment_id", "Shipment"),
    ("current_status", "Status"),
    ("destination_facility_id", "Facility"),
    ("planned_dock_code", "Dock"),
    ("slot_start_ts", "Start"),
    ("slot_end_ts", "End"),
    ("effective_eta_ts", "ETA"),
    ("dock_code", "Dock"),
    ("arrival_buffer_min", "Buffer"),
]

SKIP_KEYS = {"ok", "error", "invented_ids", "invented_slot", "tool_grounding_score"}


def is_leaked_internal(text: str) -> bool:
    """True when the model echoed session context, raw tool JSON, or internal chain-of-thought."""
    t = (text or "").strip()
    if not t:
        return False
    if t.startswith("[Session context]"):
        return True
    # Truncated or raw tool call JSON leakage (e.g. [{"name": ... or {"name": ...)
    if re.match(r"^\[?\s*\{\s*[\"'](?:name|tool_call|function|parameters|arguments)[\"']", t):
        return True
    if t.startswith('[{"name"') or t.startswith('{"name"') or t.startswith('[{"name":'):
        return True
    # Chain-of-thought / reasoning leaks (e.g. "So I need to: Call record_exception_and_eta...")
    if re.match(r"(?is)^(?:So I need to|Let me think|Thinking Process|I should call|I need to call|First, I will|The driver says|Call record_exception_and_eta)\b", t):
        return True
    head = t[:800]
    return (
        "your_active_shipments=" in head
        or "Prefer the shortest tool path" in head
        or "Call record_exception_and_eta" in head
        or ("declared_eta_ts" in head and "delay_min=" in head)
    )


def _label(key: str) -> str:
    if key in FIELD_LABELS:
        return FIELD_LABELS[key]
    return key.replace("_", " ").strip().title()


def _fmt_value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    text = str(value).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text):
        try:
            dt = datetime.fromisoformat(text)
            return dt.strftime("%d %b %H:%M")
        except ValueError:
            return text
    return text


def _md_cell(text: str) -> str:
    return str(text).replace("|", "/").replace("\n", " ").strip()


def kv_table(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return ""
    lines = ["| Field | Value |", "| --- | --- |"]
    for label, value in rows:
        lines.append(f"| {_md_cell(label)} | {_md_cell(value)} |")
    return "\n".join(lines)


def grid_table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers or not rows:
        return ""
    head = "| " + " | ".join(_md_cell(h) for h in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_md_cell(c) for c in row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


def _dict_to_kv_rows(data: dict[str, Any], preferred: list[str] | None = None) -> list[tuple[str, str]]:
    keys = list(preferred or [])
    for key in data:
        if key not in keys:
            keys.append(key)
    rows: list[tuple[str, str]] = []
    for key in keys:
        if key in SKIP_KEYS or key not in data:
            continue
        value = data[key]
        if value is None or value == "":
            continue
        if isinstance(value, (dict, list)):
            continue
        if key in ("temperature_control_required",) and value in (0, 1, "0", "1"):
            rows.append((_label(key), "Yes" if str(value) == "1" else "No"))
            continue
        rows.append((_label(key), _fmt_value(value)))
    return rows


def _list_of_dicts_table(items: list[dict[str, Any]]) -> str:
    if len(items) == 1:
        return kv_table(_dict_to_kv_rows(items[0], INBOUND_ORDER))
    present = {k for item in items for k in item}
    cols = [(k, lab) for k, lab in LIST_PREVIEW_COLS if k in present]
    if not cols:
        cols = [(k, _label(k)) for k in items[0] if k not in SKIP_KEYS][:6]
    headers = [lab for _, lab in cols]
    rows = [[_fmt_value(item.get(k)) for k, _ in cols] for item in items[:12]]
    return grid_table(headers, rows)


def json_to_markdown(data: Any) -> str:
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, list):
        if not data:
            return "No records found."
        if all(isinstance(x, dict) for x in data):
            return _list_of_dicts_table(data)  # type: ignore[arg-type]
        return kv_table([("Items", ", ".join(_fmt_value(x) for x in data[:20]))])
    if not isinstance(data, dict):
        return _fmt_value(data)

    # Leaked AgentTurnOutput — use the inner reply
    if "reply" in data and ("intent" in data or "options" in data or "client_actions" in data):
        inner = data.get("reply")
        if isinstance(inner, str) and inner.strip():
            return humanize_reply(inner)
        if isinstance(inner, (dict, list)):
            return json_to_markdown(inner)

    parts: list[str] = []
    scalars = {k: v for k, v in data.items() if not isinstance(v, (dict, list))}
    nested_dicts = {k: v for k, v in data.items() if isinstance(v, dict)}
    nested_lists = {k: v for k, v in data.items() if isinstance(v, list)}

    # Common tool shapes
    if "state" in nested_dicts:
        head = _dict_to_kv_rows(scalars)
        body = _dict_to_kv_rows(nested_dicts["state"], INBOUND_ORDER)
        merged: list[tuple[str, str]] = []
        seen = set()
        for row in head + body:
            if row[0] in seen:
                continue
            seen.add(row[0])
            merged.append(row)
        parts.append(kv_table(merged))
        nested_dicts = {k: v for k, v in nested_dicts.items() if k != "state"}
        scalars = {}

    if "options" in nested_lists and nested_lists["options"] and all(
        isinstance(x, dict) for x in nested_lists["options"]
    ):
        if scalars:
            parts.append(kv_table(_dict_to_kv_rows(scalars)))
        parts.append(_list_of_dicts_table(nested_lists["options"]))
        nested_lists = {k: v for k, v in nested_lists.items() if k != "options"}
        scalars = {}

    if "active_shipments" in nested_lists and all(isinstance(x, dict) for x in nested_lists["active_shipments"]):
        if scalars:
            parts.append(kv_table(_dict_to_kv_rows(scalars)))
        parts.append(_list_of_dicts_table(nested_lists["active_shipments"]))
        nested_lists = {k: v for k, v in nested_lists.items() if k != "active_shipments"}
        scalars = {}

    if scalars:
        parts.append(kv_table(_dict_to_kv_rows(scalars)))
    for key, nested in nested_dicts.items():
        if key in SKIP_KEYS:
            continue
        block = kv_table(_dict_to_kv_rows(nested, INBOUND_ORDER))
        if block:
            parts.append(f"**{_label(key)}**\n{block}")
    for key, nested in nested_lists.items():
        if key in SKIP_KEYS or not nested:
            continue
        if all(isinstance(x, dict) for x in nested):
            parts.append(f"**{_label(key)}**\n{_list_of_dicts_table(nested)}")
        else:
            parts.append(kv_table([(_label(key), ", ".join(_fmt_value(x) for x in nested[:20]))]))

    return "\n\n".join(p for p in parts if p).strip() or "No details available."


def _strip_fences(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json|JSON)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _try_json(text: str) -> Any | None:
    raw = _strip_fences(text)
    if not raw or raw[0] not in "{[":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        try:
            obj, end = decoder.raw_decode(raw)
        except json.JSONDecodeError:
            return None
        trailing = raw[end:].strip()
        if trailing.startswith("{") and '"reply"' in trailing[:40]:
            return obj
        if trailing:
            return None
        return obj


def _looks_like_markdown_table(text: str) -> bool:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return len(lines) >= 2 and lines[0].lstrip().startswith("|") and "---" in lines[1]


def humanize_reply(text: str) -> str:
    """If the model pasted JSON or schema artifacts, clean and turn tool dumps into markdown tables."""
    raw = (text or "").strip()

    # Strip reasoning tags like <think>...</think>
    raw = re.sub(r"(?s)<think>.*?</think>", "", raw).strip()

    if not raw or is_leaked_internal(raw):
        return raw if not is_leaked_internal(raw) else ""

    # Strip model safety annotations
    raw = re.sub(r"(?i)\bUser Safety:\s*safe\b\s*", "", raw).strip()

    # Normalize single-line table runs like "| A | B | |---|---| | C | D |"
    if "|" in raw and re.search(r"\|\s*\|", raw):
        raw = re.sub(r"\|\s*\|", "|\n|", raw)

    # Strip AgentTurnOutput / schema echoing and deduplicate identical mirrored sections
    if re.search(r"(?i)\bAgentTurnOutput\b", raw):
        parts = re.split(r"(?i)\bAgentTurnOutput(?:\([^)]*\))?:?", raw)
        clean_parts = [p.strip() for p in parts if p.strip()]
        if len(clean_parts) == 1:
            raw = clean_parts[0]
        elif len(clean_parts) >= 2:
            if clean_parts[0] == clean_parts[1] or clean_parts[0] in clean_parts[1]:
                raw = clean_parts[1]
            elif clean_parts[1] in clean_parts[0]:
                raw = clean_parts[0]
            else:
                raw = clean_parts[0]
        raw = raw.strip()

    if _looks_like_markdown_table(raw) and raw[0] != "{":
        return raw

    parsed = _try_json(raw)
    if parsed is not None:
        return json_to_markdown(parsed)

    # Cut leaked structured JSON appended after a normal sentence
    for marker in ('\n{"reply"', "\n{\n  \"reply\"", "\n```json", "\n```"):
        idx = raw.find(marker)
        if idx > 0:
            head = raw[:idx].strip()
            tail = raw[idx:].strip()
            parsed_tail = _try_json(tail.lstrip("`").lstrip("json").strip() if "```" in marker else tail)
            if parsed_tail is not None:
                converted = json_to_markdown(parsed_tail)
                if head and not _looks_like_markdown_table(head):
                    return f"{head}\n\n{converted}" if converted else head
                return converted or head
            raw = head
            break

    # Prefix prose + JSON blob
    brace = raw.find("\n{")
    if brace > 0:
        parsed_tail = _try_json(raw[brace:].strip())
        if parsed_tail is not None:
            return f"{raw[:brace].strip()}\n\n{json_to_markdown(parsed_tail)}"
    bracket = raw.find("\n[")
    if bracket > 0:
        parsed_tail = _try_json(raw[bracket:].strip())
        if parsed_tail is not None:
            return f"{raw[:bracket].strip()}\n\n{json_to_markdown(parsed_tail)}"

    return raw


def format_inbound_details(rows: list[dict[str, Any]], shipment_id: str | None = None) -> str:
    if not rows:
        sid = f" for {shipment_id}" if shipment_id else ""
        return f"No inbound details found{sid}."
    title = f"Details for {rows[0].get('shipment_id') or shipment_id or 'shipment'}:"
    return f"{title}\n\n{json_to_markdown(rows)}"
