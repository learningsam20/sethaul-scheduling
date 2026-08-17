"""Expand the classroom seed: evening crunch always; spec-scale volumes when expand_seed=full."""
from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings

IST = ZoneInfo("Asia/Kolkata")
DAY0 = datetime(2026, 8, 4, tzinfo=IST)
CREATED = "2026-08-01T12:00:00+05:30"

FIRST_NAMES = [
    "Amit", "Rahul", "Suresh", "Vijay", "Anil", "Rakesh", "Sunil", "Deepak",
    "Manoj", "Pankaj", "Rohit", "Sanjay", "Yogesh", "Naveen", "Harish", "Kiran",
]
LAST_NAMES = [
    "Sharma", "Patel", "Singh", "Yadav", "Verma", "Gupta", "Meena", "Jain",
    "Khan", "Reddy", "Nair", "Iyer", "Das", "Joshi", "Mishra", "Chauhan",
]
CITIES = ["Jaipur", "Ajmer", "Kota", "Udaipur", "Alwar", "Bikaner", "Jodhpur", "Sikar"]
PRODUCTS = [
    "FMCG", "Auto components", "Textiles", "Packaging material", "Machine parts",
    "Home appliances", "Office supplies", "Agricultural inputs", "Consumer electronics",
]
CUSTOMERS = ["RajRetail", "NorthWest Retail", "IndustrialHub", "StyleMart", "HomeCraft", "AgriServe"]
ORIGINS = [
    ("Neemrana Auto Components", "Neemrana"),
    ("Manesar Consumer Goods Plant", "Manesar"),
    ("Kota Engineering Supplies", "Kota"),
    ("Ajmer Textile Mill", "Ajmer"),
    ("Bhiwadi Packaging Works", "Bhiwadi"),
    ("Ludhiana Home Appliances", "Ludhiana"),
]

NEW_FACILITIES = [
    ("FAC-AMD-01", "SetuHaul Ahmedabad Distribution Centre", "Ahmedabad", "Gujarat", "07:00", "21:00"),
    ("FAC-MUM-01", "SetuHaul Bhiwandi Cross-Dock", "Bhiwandi", "Maharashtra", "06:00", "22:00"),
    ("FAC-DEL-01", "SetuHaul Delhi NCR Distribution Centre", "Delhi", "Delhi", "06:00", "22:00"),
    ("FAC-BLR-01", "SetuHaul Bengaluru Distribution Centre", "Bengaluru", "Karnataka", "07:00", "21:00"),
]


def expand_seed(conn: sqlite3.Connection) -> None:
    mode = (get_settings().expand_seed or "full").strip().lower()
    if mode in ("off", "0", "false", "none"):
        return
    rng = random.Random(42)
    _evening_crunch(conn, rng)
    if mode == "full":
        _volume_pack(conn, rng)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _evening_crunch(conn: sqlite3.Connection, rng: random.Random) -> None:
    """10 delayed STANDARD trucks vs 3–4 free evening slots at Jaipur."""
    carriers = ["CAR001", "CAR002", "CAR003", "CAR004"]
    for i in range(16, 26):
        did = f"DRV{i:03d}"
        vid = f"VEH{i:03d}"
        car = carriers[(i - 16) % 4]
        name = f"{FIRST_NAMES[(i - 16) % len(FIRST_NAMES)]} {LAST_NAMES[(i - 1) % len(LAST_NAMES)]}"
        conn.execute(
            """
            INSERT OR IGNORE INTO drivers(
                driver_id, carrier_id, driver_name, phone, licence_number, home_base_city, driver_status
            ) VALUES (?, ?, ?, ?, ?, 'Jaipur', 'ACTIVE')
            """,
            (did, car, name, f"+91-9000020{i:03d}", f"RJ14DL1{i:03d}"),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO vehicles(
                vehicle_id, carrier_id, vehicle_type_code, registration_number,
                capacity_kg, refrigeration_capable, active_flag
            ) VALUES (?, ?, '32FT_SXL', ?, 15000, 0, 1)
            """,
            (vid, car, f"RJ14CR{i:03d}"),
        )

    # Occupy evening STANDARD slots except four 19:00–20:00 windows.
    keep_free = {"SLOT-JAI-012", "SLOT-JAI-026", "SLOT-JAI-040", "SLOT-JAI-054"}
    evening = conn.execute(
        """
        SELECT sl.slot_id FROM appointment_slots sl
        JOIN docks d ON d.dock_id = sl.dock_id
        WHERE sl.facility_id='FAC-JAI-01'
          AND d.dock_type='STANDARD'
          AND sl.slot_start_ts >= '2026-08-04T18:00:00+05:30'
          AND sl.slot_start_ts < '2026-08-04T22:00:00+05:30'
          AND sl.slot_status='OPEN'
        """
    ).fetchall()
    occupy_ids = [r["slot_id"] if isinstance(r, sqlite3.Row) else r[0] for r in evening if (r["slot_id"] if isinstance(r, sqlite3.Row) else r[0]) not in keep_free]

    for n, slot_id in enumerate(occupy_ids, start=1):
        sid = f"SHP12{n:02d}"
        did = f"DRV{((n - 1) % 15) + 1:03d}"
        vid = f"VEH{((n - 1) % 15) + 1:03d}"
        car = carriers[(n - 1) % 4]
        eta = "2026-08-04T18:10:00+05:30"
        conn.execute(
            """
            INSERT OR IGNORE INTO shipments(
                shipment_id, order_reference, carrier_id, driver_id, vehicle_id,
                origin_name, origin_city, destination_facility_id, customer_name, product_category,
                load_weight_kg, pallet_count, required_dock_type, temperature_control_required,
                priority_code, planned_departure_ts, actual_departure_ts, original_eta_ts, latest_eta_ts,
                expected_unload_min, current_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'Ajmer Textile Mill', 'Ajmer', 'FAC-JAI-01', 'Evening Occupier',
                      'FMCG', 12000, 20, 'STANDARD', 0, 'NORMAL',
                      '2026-08-04T12:00:00+05:30', '2026-08-04T12:10:00+05:30', ?, ?,
                      60, 'IN_TRANSIT', ?, ?)
            """,
            (sid, f"ORD-CRUNCH-OCC-{n:02d}", car, did, vid, eta, eta, CREATED, CREATED),
        )
        try:
            conn.execute(
                """
                INSERT INTO appointments(
                    appointment_id, shipment_id, slot_id, appointment_status, booking_source,
                    is_current, booked_at, confirmed_at, cancelled_at, cancellation_reason,
                    replaced_appointment_id, warehouse_confirmation_ref, updated_at
                ) VALUES (?, ?, ?, 'CONFIRMED', 'PLANNER', 1, ?, ?, NULL, NULL, NULL, ?, ?)
                """,
                (f"APT-OCC-{n:02d}", sid, slot_id, CREATED, CREATED, f"WH-OCC-{n:02d}", CREATED),
            )
        except sqlite3.IntegrityError:
            pass

    # 10 competing delayed trucks — no current evening appointment, ETA ~18:45
    for i in range(1, 11):
        sid = f"SHP11{i:02d}"
        did = f"DRV{i + 15:03d}"
        vid = f"VEH{i + 15:03d}"
        car = carriers[(i - 1) % 4]
        eta = f"2026-08-04T18:{40 + (i % 10):02d}:00+05:30"
        prio = ["HIGH", "CRITICAL", "NORMAL", "HIGH", "NORMAL", "HIGH", "CRITICAL", "NORMAL", "HIGH", "LOW"][i - 1]
        conn.execute(
            """
            INSERT OR IGNORE INTO shipments(
                shipment_id, order_reference, carrier_id, driver_id, vehicle_id,
                origin_name, origin_city, destination_facility_id, customer_name, product_category,
                load_weight_kg, pallet_count, required_dock_type, temperature_control_required,
                priority_code, planned_departure_ts, actual_departure_ts, original_eta_ts, latest_eta_ts,
                expected_unload_min, current_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'Delhi Electronics Hub', 'Delhi', 'FAC-JAI-01', 'Evening Crunch Retail',
                      'Consumer electronics', 11000, 18, 'STANDARD', 0, ?,
                      '2026-08-04T14:00:00+05:30', '2026-08-04T14:20:00+05:30',
                      '2026-08-04T17:30:00+05:30', ?, 55, 'IN_TRANSIT', ?, ?)
            """,
            (sid, f"ORD-CRUNCH-{i:02d}", car, did, vid, prio, eta, CREATED, CREATED),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO eta_updates(
                eta_update_id, shipment_id, source_type, reported_by_driver_id,
                declared_eta_ts, confidence_code, delay_reason_code, note, created_at
            ) VALUES (?, ?, 'DRIVER_DECLARED', ?, ?, 'HIGH', 'TRAFFIC', 'Evening crunch delay', ?)
            """,
            (f"ETA-CR-{i:02d}", sid, did, eta, "2026-08-04T16:30:00+05:30"),
        )


def _volume_pack(conn: sqlite3.Connection, rng: random.Random) -> None:
    carriers = ["CAR001", "CAR002", "CAR003", "CAR004"]
    for fid, name, city, state, open_t, close_t in NEW_FACILITIES:
        conn.execute(
            """
            INSERT OR IGNORE INTO facilities(
                facility_id, facility_name, city, state, timezone, open_time, close_time,
                checkin_grace_min, default_unload_min, active_flag
            ) VALUES (?, ?, ?, ?, 'Asia/Kolkata', ?, ?, 30, 60, 1)
            """,
            (fid, name, city, state, open_t, close_t),
        )
        prefix = fid.split("-")[1]
        specs = [
            ("D1", "STANDARD", 0, 22000),
            ("D2", "STANDARD", 0, 22000),
            ("D3", "STANDARD", 0, 25000),
            ("D4", "REEFER", 1, 20000),
            ("D5", "HEAVY", 0, 35000),
        ]
        for code, dtype, reefer, kg in specs:
            conn.execute(
                """
                INSERT OR IGNORE INTO docks(
                    dock_id, facility_id, dock_code, dock_type, supports_refrigerated,
                    max_vehicle_weight_kg, dock_status
                ) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE')
                """,
                (f"DOCK-{prefix}-{code}", fid, code, dtype, reefer, kg),
            )

    # Extra drivers / vehicles to reach ~100 / ~110
    existing_drv = conn.execute("SELECT COUNT(*) AS n FROM drivers").fetchone()["n"]
    need_drv = max(0, 100 - existing_drv)
    for i in range(need_drv):
        n = 26 + i
        did = f"DRV{n:03d}"
        vid = f"VEH{n:03d}"
        car = carriers[n % 4]
        vtype = ["32FT_SXL", "32FT_MXL", "20FT", "REEFER_32", "HEAVY_40"][n % 5]
        reefer = 1 if vtype.startswith("REEFER") else 0
        cap = {"32FT_SXL": 15000, "32FT_MXL": 22000, "20FT": 9000, "REEFER_32": 18000, "HEAVY_40": 32000}[vtype]
        conn.execute(
            """
            INSERT OR IGNORE INTO drivers(
                driver_id, carrier_id, driver_name, phone, licence_number, home_base_city, driver_status
            ) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE')
            """,
            (
                did,
                car,
                f"{FIRST_NAMES[n % len(FIRST_NAMES)]} {LAST_NAMES[(n * 3) % len(LAST_NAMES)]}",
                f"+91-9000030{n:03d}",
                f"MH04DL2{n:03d}",
                CITIES[n % len(CITIES)],
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO vehicles(
                vehicle_id, carrier_id, vehicle_type_code, registration_number,
                capacity_kg, refrigeration_capable, active_flag
            ) VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (vid, car, vtype, f"MH04VL{n:03d}", cap, reefer),
        )

    docks = conn.execute("SELECT dock_id, facility_id FROM docks").fetchall()
    slot_rows = []
    extra_days = [DAY0 + timedelta(days=d) for d in range(-3, 4) if d != 0]
    for dock in docks:
        dock_id = dock["dock_id"]
        fac = dock["facility_id"]
        for day in extra_days:
            for hour in range(8, 21):
                start = day.replace(hour=hour, minute=0, second=0, microsecond=0)
                end = start + timedelta(hours=1)
                slot_id = f"SLOT-X-{dock_id[-6:]}-{start.strftime('%m%d%H')}"
                slot_rows.append(
                    (slot_id, fac, dock_id, _iso(start), _iso(end), "OPEN", None, CREATED)
                )
    conn.executemany(
        """
        INSERT OR IGNORE INTO appointment_slots(
            slot_id, facility_id, dock_id, slot_start_ts, slot_end_ts, slot_status, block_reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        slot_rows,
    )

    drivers = [r["driver_id"] for r in conn.execute("SELECT driver_id FROM drivers ORDER BY driver_id").fetchall()]
    vehicles = [r["vehicle_id"] for r in conn.execute("SELECT vehicle_id FROM vehicles ORDER BY vehicle_id").fetchall()]
    facilities = [r["facility_id"] for r in conn.execute("SELECT facility_id FROM facilities").fetchall()]
    existing_shp = conn.execute("SELECT COUNT(*) AS n FROM shipments").fetchone()["n"]
    need_shp = max(0, 720 - existing_shp)

    open_slots = conn.execute(
        """
        SELECT slot_id, facility_id, slot_start_ts, slot_end_ts FROM appointment_slots
        WHERE slot_status='OPEN' AND slot_id LIKE 'SLOT-X-%'
        ORDER BY slot_start_ts
        """
    ).fetchall()

    shp_rows = []
    apt_rows = []
    eta_rows = []
    chk_rows = []
    exc_rows = []
    msg_rows = []
    thr_rows = []
    slot_i = 0
    for i in range(need_shp):
        n = 2000 + i
        sid = f"SHP{n}"
        did = drivers[i % len(drivers)]
        vid = vehicles[i % len(vehicles)]
        car = carriers[i % 4]
        fac = facilities[i % len(facilities)]
        day = extra_days[i % len(extra_days)]
        hour = 8 + (i % 10)
        eta = day.replace(hour=hour, minute=15, second=0, microsecond=0)
        origin = ORIGINS[i % len(ORIGINS)]
        product = PRODUCTS[i % len(PRODUCTS)]
        status = "COMPLETED"
        shp_rows.append(
            (
                sid,
                f"ORD-VOL-{n}",
                car,
                did,
                vid,
                origin[0],
                origin[1],
                fac,
                CUSTOMERS[i % len(CUSTOMERS)],
                product,
                8000 + (i % 20) * 500,
                12 + (i % 10),
                "STANDARD",
                0,
                "NORMAL",
                _iso(eta - timedelta(hours=4)),
                _iso(eta - timedelta(hours=4)),
                _iso(eta),
                _iso(eta),
                50 + (i % 3) * 10,
                status,
                CREATED,
                _iso(eta + timedelta(hours=2)),
            )
        )
        eta_rows.append(
            (
                f"ETA-V{n}",
                sid,
                "DRIVER_DECLARED",
                did,
                _iso(eta),
                "HIGH",
                None,
                "Historical volume ETA",
                _iso(eta - timedelta(hours=2)),
            )
        )
        if slot_i < len(open_slots):
            sl = open_slots[slot_i]
            slot_i += 1
            apt_rows.append(
                (
                    f"APT-V{n}",
                    sid,
                    sl["slot_id"],
                    "COMPLETED",
                    "PLANNER",
                    1,
                    CREATED,
                    CREATED,
                    None,
                    None,
                    None,
                    f"WH-V{n}",
                    _iso(eta + timedelta(hours=1)),
                )
            )
            if i % 2 == 0:
                chk_rows.append(
                    (
                        f"CHK-V{n}",
                        sid,
                        sl["facility_id"],
                        _iso(eta - timedelta(minutes=10)),
                        _iso(eta - timedelta(minutes=8)),
                        _iso(eta),
                        _iso(eta),
                        _iso(eta + timedelta(minutes=50)),
                        _iso(eta + timedelta(minutes=55)),
                        "ON_TIME",
                        "COMPLETED",
                        None,
                        None,
                        "Volume pack completed unload",
                        _iso(eta + timedelta(hours=1)),
                    )
                )
        if i < 240:
            tid = f"THR-V{n}"
            thr_rows.append(
                (tid, did, sid, _iso(eta - timedelta(hours=3)), _iso(eta), "CLOSED", "REPORT_DELAY")
            )
            msg_rows.append(
                (
                    f"MSG-V{n}A",
                    tid,
                    "DRIVER",
                    did,
                    f"Running late, ETA {_iso(eta)[11:16]}",
                    _iso(eta - timedelta(hours=3)),
                    None,
                    0,
                    "REPORT_DELAY",
                    _iso(eta),
                    0,
                )
            )
            msg_rows.append(
                (
                    f"MSG-V{n}B",
                    tid,
                    "AGENT",
                    "agent",
                    "Historical case resolved.",
                    _iso(eta - timedelta(hours=3, minutes=-2)),
                    None,
                    0,
                    "RESOLVED",
                    None,
                    0,
                )
            )
            exc_rows.append(
                (
                    f"EXC-V{n}",
                    sid,
                    did,
                    tid,
                    "DELAY",
                    _iso(eta - timedelta(hours=3)),
                    20,
                    _iso(eta),
                    None,
                    None,
                    "LOW",
                    "RESOLVED",
                    "Volume-pack historical delay",
                    f"{did}-{sid}-vol",
                )
            )

    conn.executemany(
        """
        INSERT OR IGNORE INTO shipments(
            shipment_id, order_reference, carrier_id, driver_id, vehicle_id,
            origin_name, origin_city, destination_facility_id, customer_name, product_category,
            load_weight_kg, pallet_count, required_dock_type, temperature_control_required,
            priority_code, planned_departure_ts, actual_departure_ts, original_eta_ts, latest_eta_ts,
            expected_unload_min, current_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        shp_rows,
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO eta_updates(
            eta_update_id, shipment_id, source_type, reported_by_driver_id,
            declared_eta_ts, confidence_code, delay_reason_code, note, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        eta_rows,
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO appointments(
            appointment_id, shipment_id, slot_id, appointment_status, booking_source,
            is_current, booked_at, confirmed_at, cancelled_at, cancellation_reason,
            replaced_appointment_id, warehouse_confirmation_ref, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        apt_rows,
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO facility_checkins(
            checkin_id, shipment_id, facility_id, gate_in_ts, yard_queue_enter_ts, dock_in_ts,
            unload_start_ts, unload_end_ts, gate_out_ts, arrival_state, queue_state,
            queue_position, actual_dock_id, notes, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        chk_rows,
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO chat_threads(
            thread_id, driver_id, shipment_id, opened_at, closed_at, thread_status, thread_intent
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        thr_rows,
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO chat_messages(
            chat_message_id, thread_id, sender_type, sender_reference, message_text,
            message_ts, external_message_id, is_duplicate, parsed_intent, extracted_eta_ts, requires_human_review
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        msg_rows,
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO driver_exceptions(
            exception_id, shipment_id, driver_id, thread_id, exception_type, reported_at,
            reported_delay_min, declared_eta_ts, earliest_acceptable_ts, latest_acceptable_ts,
            severity_code, exception_status, description, dedupe_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        exc_rows,
    )
