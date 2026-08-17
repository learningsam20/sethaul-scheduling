#!/usr/bin/env python3
"""10 delayed drivers vs 3–4 free evening standard slots at Jaipur DC."""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("EXPAND_SEED", "crunch")

from app.config import _cached_settings  # noqa: E402
from app.db import rebuild_database  # noqa: E402
from app.services import booking  # noqa: E402


def main() -> int:
    _cached_settings.cache_clear()
    rebuild_database(force=True)
    shipments = [f"SHP11{i:02d}" for i in range(1, 11)]
    after = "2026-08-04T18:40:00+05:30"

    def book(sid: str) -> dict:
        slots = booking.find_feasible_slots(sid, after_ts=after, limit=4)
        if not slots:
            return {"shipment_id": sid, "ok": False, "stage": "options"}
        slot_id = slots[0]["slot_id"]
        hold = booking.soft_hold_slot(slot_id, sid, None, None)
        if not hold.get("ok"):
            return {"shipment_id": sid, "ok": False, "stage": "hold", "slot_id": slot_id, "error": hold.get("error")}
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
    print("=== Evening crunch (10 drivers, ~4 free slots) ===")
    for r in results:
        print(json.dumps(r))
    unique = {r.get("slot_id") for r in wins}
    ok = 1 <= len(wins) <= 4 and len(unique) == len(wins)
    print(f"\n[{'PASS' if ok else 'FAIL'}] wins={len(wins)} unique_slots={len(unique)}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
