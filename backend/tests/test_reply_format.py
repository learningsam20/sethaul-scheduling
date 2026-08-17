from app.agent.lc_tools import extract_constraint_ts, extract_eta_from_text
from app.agent.reply_format import format_inbound_details, humanize_reply, is_leaked_internal, json_to_markdown


def test_humanize_inbound_json_becomes_table():
    raw = """[
      {
        "shipment_id": "SHP1006",
        "current_status": "IN_TRANSIT",
        "destination_facility_id": "FAC-JAI-01",
        "planned_dock_code": "A1",
        "slot_start_ts": "2026-08-04T10:00:00+05:30",
        "slot_end_ts": "2026-08-04T11:00:00+05:30",
        "effective_eta_ts": "2026-08-04T11:20:00+05:30",
        "temperature_control_required": 0,
        "queue_state": null
      }
    ]"""
    out = humanize_reply(raw)
    assert "| Field | Value |" in out
    assert "SHP1006" in out
    assert "IN_TRANSIT" in out
    assert "{" not in out
    assert "A1" in out


def test_humanize_keeps_plain_greeting():
    assert humanize_reply("Hi — I'm SetuHaul's dock assistant.") == "Hi — I'm SetuHaul's dock assistant."


def test_humanize_feasibility_wrapper():
    payload = {
        "feasible": False,
        "reason": "Effective ETA is after current appointment window",
        "state": {
            "shipment_id": "SHP1006",
            "current_status": "IN_TRANSIT",
            "planned_dock_code": "A1",
        },
    }
    out = json_to_markdown(payload)
    assert "Feasible" in out
    assert "No" in out
    assert "SHP1006" in out
    assert "A1" in out


def test_fallback_details_prompt_returns_table(db):
    from app.agent.graph import handle_driver_message

    user = {"user_id": "USR-DRV006", "driver_id": "DRV006", "role": "DRIVER"}
    result = handle_driver_message(user, "get details of SHP1006", shipment_id="SHP1006")
    reply = result["reply"]
    assert "| Field | Value |" in reply
    assert "SHP1006" in reply
    assert not reply.strip().startswith("{")
    assert "{" not in reply


def test_format_inbound_details_empty():
    assert "No inbound details" in format_inbound_details([], "SHP1006")


def test_before_time_is_deadline_not_declared_eta():
    text = "yes, let me know the eta before 13:00"
    assert extract_eta_from_text(text) is None
    assert extract_constraint_ts(text, "latest") == "2026-08-04T13:00:00+05:30"
    assert extract_eta_from_text("Traffic after Shahpura. Reaching around 11:20.") == "2026-08-04T11:20:00+05:30"
    assert extract_constraint_ts("Any slot after 12:00?", "earliest") == "2026-08-04T12:00:00+05:30"


def test_humanize_strips_session_context_leak():
    leaked = (
        "[Session context]\n"
        "thread_id=THR-CCFAF7DD\n"
        "driver_id=DRV006\n"
        "known_shipment_id=SHP1006\n"
        "your_active_shipments=SHP1006, SHP1021\n"
        "classroom_clock=2026-08-04T09:40:00+05:30\n"
        "SECURITY: Only act on shipments in your_active_shipments.\n"
        "Prefer the shortest tool path. Then return AgentTurnOutput.\n\n"
        "Driver message:\nyes, let me know the eta before 13:00"
    )
    assert is_leaked_internal(leaked)
    assert humanize_reply(leaked) == ""


def test_eta_before_deadline_does_not_echo_session(db):
    from app.agent.graph import handle_driver_message

    user = {"user_id": "USR-DRV006", "driver_id": "DRV006", "role": "DRIVER"}
    result = handle_driver_message(
        user, "yes, let me know the eta before 13:00", shipment_id="SHP1006"
    )
    reply = result["reply"]
    assert "[Session context]" not in reply
    assert "your_active_shipments=" not in reply
    assert "Driver message:" not in reply
    assert "13:00" in reply or "slot" in reply.lower() or "option" in reply.lower() or "feasible" in reply.lower()
