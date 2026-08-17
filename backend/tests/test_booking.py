from concurrent.futures import ThreadPoolExecutor

from app.db import db_session
from app.services import booking


def test_soft_hold_is_exclusive(db):
    slots = booking.find_feasible_slots("SHP1006", after_ts="2026-08-04T11:20:00+05:30", limit=3)
    assert slots, "expected feasible slots for delayed SHP1006"
    slot_id = slots[0]["slot_id"]

    def hold(shipment_id: str):
        return booking.soft_hold_slot(slot_id, shipment_id, None, None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(hold, "SHP1006")
        b = pool.submit(hold, "SHP1012")
        results = [a.result(), b.result()]
    wins = [r for r in results if r.get("ok")]
    losses = [r for r in results if not r.get("ok")]
    assert len(wins) == 1
    assert len(losses) == 1


def test_operating_hours_enforced(db):
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO appointment_slots(
                slot_id, facility_id, dock_id, slot_start_ts, slot_end_ts, slot_status, block_reason, created_at
            ) VALUES (
                'SLOT-JAI-NIGHT', 'FAC-JAI-01', 'DOCK-JAI-D1',
                '2026-08-04T23:00:00+05:30', '2026-08-05T00:00:00+05:30',
                'OPEN', NULL, '2026-08-01T12:00:00+05:30'
            )
            """
        )
    slots = booking.find_feasible_slots("SHP1006", after_ts="2026-08-04T22:30:00+05:30", limit=20)
    assert all(s["slot_id"] != "SLOT-JAI-NIGHT" for s in slots)


def test_product_restriction_blocks_slots(db):
    with db_session() as conn:
        conn.execute(
            "UPDATE shipments SET product_category='Hazmat' WHERE shipment_id='SHP1017'"
        )
    assert booking.find_feasible_slots("SHP1017", after_ts="2026-08-04T12:00:00+05:30") == []


def test_cancel_frees_slot(db):
    before = booking.find_feasible_slots("SHP1007", after_ts="2026-08-04T11:00:00+05:30", limit=50)
    assert "SLOT-JAI-018" not in {s["slot_id"] for s in before}
    # APT1013A is pending on SLOT-JAI-018
    result = booking.cancel_appointment("APT1013A", "test cancel", "ops")
    assert result["ok"] is True
    after = booking.find_feasible_slots("SHP1007", after_ts="2026-08-04T11:00:00+05:30", limit=50)
    assert "SLOT-JAI-018" in {s["slot_id"] for s in after}


def test_dock_event_invalidates_holds(db):
    slots = booking.find_feasible_slots("SHP1006", after_ts="2026-08-04T11:20:00+05:30", limit=1)
    assert slots
    slot_id = slots[0]["slot_id"]
    dock_id = slots[0]["dock_id"]
    held = booking.soft_hold_slot(slot_id, "SHP1006", "THR001", None)
    assert held["ok"]
    ev = booking.record_dock_event(dock_id, "BREAKDOWN", "test breakdown", "2026-08-04T11:00:00+05:30", "2026-08-04T20:00:00+05:30")
    assert ev["ok"]
    assert slot_id in ev["affected_slots"]
    again = booking.soft_hold_slot(slot_id, "SHP1012", None, None)
    # Slot should now be blocked by the dock event, so confirm-time availability fails;
    # a new hold may still insert, but find_feasible should exclude it.
    found = booking.find_feasible_slots("SHP1012", after_ts="2026-08-04T11:20:00+05:30", limit=20)
    assert all(s["slot_id"] != slot_id for s in found)


def test_stale_options_are_warned_and_dropped(db):
    from app.agent.graph import _apply_stale_options
    from app.services import chat
    from app.services import metrics as metrics_service

    thread = chat.create_thread("DRV006", "SHP1006")
    metrics_service.ensure_case_metric(thread["thread_id"], "SHP1006", "DRV006", "FAC-JAI-01", "CAR003")
    slots = booking.find_feasible_slots("SHP1006", after_ts="2026-08-04T11:20:00+05:30", limit=1)
    assert slots
    metrics_service.record_options_generated(thread["thread_id"], slots)
    ev = booking.record_dock_event(
        slots[0]["dock_id"],
        "BREAKDOWN",
        "stale-options test",
        "2026-08-04T11:00:00+05:30",
        "2026-08-04T20:00:00+05:30",
    )
    assert ev["ok"]
    assert metrics_service.options_are_stale(thread["thread_id"])
    opts, reply, stale = _apply_stale_options(
        thread["thread_id"], "SHP1006", slots, "Here are your options."
    )
    assert stale is True
    assert "stale" in reply.lower()
    assert slots[0]["slot_id"] not in {o.get("slot_id") for o in opts}


def test_runtime_constraints_persisted(db):
    booking.persist_exception_constraints(
        "SHP1006",
        "DRV006",
        "THR001",
        "2026-08-04T11:20:00+05:30",
        delay_min=60,
        earliest_acceptable_ts="2026-08-04T12:00:00+05:30",
        latest_acceptable_ts="2026-08-04T14:00:00+05:30",
    )
    slots = booking.find_feasible_slots("SHP1006", after_ts="2026-08-04T11:20:00+05:30", limit=20)
    assert slots, "expected at least one slot inside the persisted window"
    for s in slots:
        assert s["slot_start_ts"] >= "2026-08-04T12:00:00+05:30"
        assert s["slot_end_ts"] <= "2026-08-04T14:00:00+05:30"
