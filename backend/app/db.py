from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterator

from passlib.context import CryptContext

from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
IST = timezone(timedelta(hours=5, minutes=30))


def now_iso() -> str:
    settings = get_settings()
    if settings.classroom_now:
        return settings.classroom_now
    return datetime.now(IST).isoformat(timespec="seconds")


def get_connection() -> sqlite3.Connection:
    settings = get_settings()
    path = Path(settings.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [{k: r[k] for k in r.keys()} for r in rows]


def rebuild_database(force: bool = True) -> None:
    settings = get_settings()
    db_path = Path(settings.database_path)
    seed_path = Path(settings.seed_sql_path)
    migrations_dir = Path(settings.migrations_dir)

    if force and db_path.exists():
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(db_path) + suffix) if suffix else db_path
            if p.exists():
                p.unlink()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    sql = seed_path.read_text(encoding="utf-8")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(sql)
        conn.execute("PRAGMA foreign_keys = ON")
        for mig in sorted(migrations_dir.glob("*.sql")):
            conn.executescript(mig.read_text(encoding="utf-8"))
        _ensure_schema_patches(conn)
        from app.seed_expand import expand_seed

        expand_seed(conn)
        _seed_app_defaults(conn)
        conn.commit()
    finally:
        conn.close()


def ensure_database() -> None:
    settings = get_settings()
    db_path = Path(settings.database_path)
    if not db_path.exists():
        rebuild_database(force=False)
        return
    migrations_dir = Path(settings.migrations_dir)
    with db_session() as conn:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='app_users'"
        ).fetchone()
        if not exists:
            for mig in sorted(migrations_dir.glob("*.sql")):
                conn.executescript(mig.read_text(encoding="utf-8"))
            _ensure_schema_patches(conn)
        else:
            # Idempotent migrations (CREATE IF NOT EXISTS) for schema upgrades
            for mig in sorted(migrations_dir.glob("*.sql")):
                conn.executescript(mig.read_text(encoding="utf-8"))
            _ensure_schema_patches(conn)
        _maybe_expand_existing(conn)
        _seed_app_defaults(conn)


def _ensure_schema_patches(conn: sqlite3.Connection) -> None:
    def add_col(table: str, name: str, ddl: str) -> None:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if name not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    add_col("case_metrics", "options_generated_at", "options_generated_at TEXT")
    add_col("case_metrics", "displayed_options_json", "displayed_options_json TEXT")
    add_col("case_metrics", "options_stale", "options_stale INTEGER NOT NULL DEFAULT 0")
    add_col("drivers", "duty_start_ts", "duty_start_ts TEXT")
    add_col("drivers", "max_daily_hours", "max_daily_hours REAL DEFAULT 10")
    add_col("drivers", "remaining_duty_minutes", "remaining_duty_minutes INTEGER DEFAULT 600")
    add_col("drivers", "updated_at", "updated_at TEXT")
    add_col("facility_rules", "partial_day_start", "partial_day_start TIME")
    add_col("facility_rules", "partial_day_end", "partial_day_end TIME")

    conn.execute("DROP VIEW IF EXISTS v_latest_eta")
    conn.execute(
        """
        CREATE VIEW v_latest_eta AS
        WITH ranked AS (
            SELECT
                e.*,
                ROW_NUMBER() OVER (PARTITION BY shipment_id ORDER BY rowid DESC) AS rn
            FROM eta_updates e
        )
        SELECT
            s.shipment_id,
            s.original_eta_ts,
            COALESCE(r.declared_eta_ts, s.latest_eta_ts, s.original_eta_ts) AS effective_eta_ts,
            COALESCE(r.source_type, 'ORIGINAL_PLAN') AS eta_source,
            COALESCE(r.confidence_code, 'HIGH') AS eta_confidence,
            r.delay_reason_code,
            r.note AS eta_note,
            r.created_at AS eta_updated_at
        FROM shipments s
        LEFT JOIN ranked r ON r.shipment_id = s.shipment_id AND r.rn = 1
        """
    )


def _maybe_expand_existing(conn: sqlite3.Connection) -> None:
    """Apply expand_seed to an already-shipped narrative DB (start.sh uses ensure, not reset)."""
    mode = (get_settings().expand_seed or "full").strip().lower()
    if mode in ("off", "0", "false", "none"):
        return
    row = conn.execute("SELECT COUNT(*) AS n FROM drivers").fetchone()
    count = int(row["n"] if row is not None else 0)
    threshold = 20 if mode == "crunch" else 80
    if count >= threshold:
        return
    from app.seed_expand import expand_seed

    expand_seed(conn)


def _seed_app_defaults(conn: sqlite3.Connection) -> None:
    ts = now_iso()
    settings = [
        ("soft_hold_ttl_seconds", str(get_settings().soft_hold_ttl_seconds), "Soft hold TTL"),
        ("pending_warehouse_ttl_minutes", str(get_settings().pending_warehouse_ttl_minutes), "Pending TTL"),
        ("max_clarification_turns", str(get_settings().max_clarification_turns), "Max clarifications"),
        ("classroom_now", get_settings().classroom_now, "System clock (ISO timestamp)"),
        ("carrier_role_enabled", "true", "Show carrier login"),
        ("customer_role_enabled", "true", "Show customer login"),
        ("wow_improve_threshold_pct", "5", "WoW improved badge threshold %"),
        ("system_prompt_extra", "", "Extra system prompt text"),
    ]
    for key, value, desc in settings:
        conn.execute(
            """
            INSERT INTO app_settings(setting_key, setting_value, description, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
              description=excluded.description
            """,
            (key, value, desc, ts),
        )

    geos = [
        ("FAC-JAI-01", 26.9124, 75.7873, "Jaipur DC"),
        ("FAC-GGN-01", 28.4595, 77.0266, "Gurugram Cross-Dock"),
        ("FAC-AMD-01", 23.0225, 72.5714, "Ahmedabad DC"),
        ("FAC-MUM-01", 19.2813, 73.0483, "Bhiwandi Cross-Dock"),
        ("FAC-DEL-01", 28.6139, 77.2090, "Delhi NCR DC"),
        ("FAC-BLR-01", 12.9716, 77.5946, "Bengaluru DC"),
    ]
    for facility_id, lat, lon, label in geos:
        exists = conn.execute(
            "SELECT 1 FROM facilities WHERE facility_id=?", (facility_id,)
        ).fetchone()
        if not exists:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO facility_geo(facility_id, latitude, longitude, label)
            VALUES (?, ?, ?, ?)
            """,
            (facility_id, lat, lon, label),
        )

    # password for all demo users: pin1234
    demo_hash = pwd_context.hash("pin1234")
    users = [
        ("USR-ADMIN", "admin", "ADMIN", "SetuHaul Admin", None, None, None, None),
        ("USR-OPS", "ops", "OPERATIONS", "Ops Coordinator", None, None, None, None),
        ("USR-WH-JAI", "warehouse.jai", "WAREHOUSE", "Jaipur Warehouse", None, "FAC-JAI-01", None, None),
        ("USR-WH-GGN", "warehouse.ggn", "WAREHOUSE", "Gurugram Warehouse", None, "FAC-GGN-01", None, None),
        ("USR-DRV006", "driver.ravi", "DRIVER", "Driver DRV006", "DRV006", None, None, None),
        ("USR-DRV012", "driver.amit", "DRIVER", "Driver DRV012", "DRV012", None, None, None),
        ("USR-DRV014", "driver.neha", "DRIVER", "Driver DRV014", "DRV014", None, None, None),
        ("USR-DRV004", "driver.suresh", "DRIVER", "Driver DRV004", "DRV004", None, None, None),
        ("USR-DRV003", "driver.early", "DRIVER", "Driver DRV003", "DRV003", None, None, None),
        ("USR-DRV015", "driver.reefer", "DRIVER", "Driver DRV015", "DRV015", None, None, None),
        ("USR-CAR003", "carrier.shakti", "CARRIER", "Shakti Transport", None, None, "CAR003", None),
        ("USR-CUST", "customer.caresupply", "CUSTOMER", "CareSupply Rajasthan", None, None, None, "CareSupply"),
    ]
    for row in users:
        user_id, username, role, display, driver_id, facility_id, carrier_id, customer_key = row
        conn.execute(
            """
            INSERT OR IGNORE INTO app_users(
                user_id, username, password_hash, role, display_name,
                driver_id, facility_id, carrier_id, customer_key,
                active_flag, theme_pref, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'system', ?, ?)
            """,
            (
                user_id,
                username,
                demo_hash,
                role,
                display,
                driver_id,
                facility_id,
                carrier_id,
                customer_key,
                ts,
                ts,
            ),
        )

    extra_drivers = conn.execute(
        """
        SELECT driver_id, driver_name FROM drivers
        WHERE driver_id BETWEEN 'DRV016' AND 'DRV025'
        ORDER BY driver_id
        """
    ).fetchall()
    for i, d in enumerate(extra_drivers, start=1):
        conn.execute(
            """
            INSERT OR IGNORE INTO app_users(
                user_id, username, password_hash, role, display_name,
                driver_id, facility_id, carrier_id, customer_key,
                active_flag, theme_pref, created_at, updated_at
            ) VALUES (?, ?, ?, 'DRIVER', ?, ?, NULL, NULL, NULL, 1, 'system', ?, ?)
            """,
            (
                f"USR-{d['driver_id']}",
                f"driver.crunch{i}",
                demo_hash,
                d["driver_name"],
                d["driver_id"],
                ts,
                ts,
            ),
        )


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,)
    ).fetchone()
    if row is None:
        return default
    return row["setting_value"]
