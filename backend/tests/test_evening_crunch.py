from concurrent.futures import ThreadPoolExecutor

from app.services import booking


def test_evening_crunch_four_slots_ten_drivers(crunch_db):
    shipments = [f"SHP11{i:02d}" for i in range(1, 11)]
    after = "2026-08-04T18:40:00+05:30"
    option_counts = [len(booking.find_feasible_slots(s, after_ts=after, limit=8)) for s in shipments]
    assert max(option_counts) <= 6
    assert min(option_counts) >= 1

    def book(sid: str):
        slots = booking.find_feasible_slots(sid, after_ts=after, limit=4)
        if not slots:
            return {"shipment_id": sid, "ok": False, "stage": "options"}
        slot_id = slots[0]["slot_id"]
        hold = booking.soft_hold_slot(slot_id, sid, None, None)
        if not hold.get("ok"):
            return {"shipment_id": sid, "ok": False, "stage": "hold", "error": hold.get("error"), "slot_id": slot_id}
        conf = booking.confirm_driver_choice(sid, slot_id)
        return {
            "shipment_id": sid,
            "ok": bool(conf.get("ok")),
            "stage": "confirm",
            "slot_id": slot_id,
            "error": conf.get("error"),
        }

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(book, shipments))
    wins = [r for r in results if r.get("ok")]
    slot_ids = [r["slot_id"] for r in wins if r.get("slot_id")]
    assert len(wins) <= 4
    assert len(set(slot_ids)) == len(slot_ids)
    assert len(wins) >= 1
