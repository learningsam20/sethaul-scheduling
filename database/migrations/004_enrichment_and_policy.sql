-- 004: enrichment tables, facility_rules partial-day, allocation_policy
-- Idempotent: CREATE IF NOT EXISTS for new tables. Column additions handled in db.py.

-- Drivers: add duty-time columns (handled in db.py _ensure_schema_patches)
-- Facility rules: add partial-day time window columns (handled in db.py _ensure_schema_patches)

-- Penalty requests
CREATE TABLE IF NOT EXISTS penalty_requests (
    penalty_request_id TEXT PRIMARY KEY,
    shipment_id TEXT NOT NULL,
    exception_id TEXT,
    requested_by TEXT NOT NULL,
    approved_by TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','APPROVED','REJECTED')),
    penalty_type TEXT NOT NULL,
    amount REAL NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_at TEXT
);

-- Customer commitments (optional enrichment)
CREATE TABLE IF NOT EXISTS customer_commitments (
    commitment_id TEXT PRIMARY KEY,
    shipment_id TEXT NOT NULL,
    customer_key TEXT NOT NULL,
    committed_delivery_ts TEXT NOT NULL,
    penalty_clause TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Appointment history (optional enrichment)
CREATE TABLE IF NOT EXISTS appointment_history (
    history_id TEXT PRIMARY KEY,
    appointment_id TEXT NOT NULL,
    shipment_id TEXT NOT NULL,
    previous_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    changed_by TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);

-- Facility capacity changes (optional enrichment)
CREATE TABLE IF NOT EXISTS facility_capacity_changes (
    change_id TEXT PRIMARY KEY,
    facility_id TEXT NOT NULL,
    change_type TEXT NOT NULL,
    dock_id TEXT,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    capacity_delta INTEGER,
    reason TEXT,
    created_at TEXT NOT NULL
);

-- Allocation policy (per-facility scheduler policy)
CREATE TABLE IF NOT EXISTS allocation_policy (
    policy_id TEXT PRIMARY KEY,
    facility_id TEXT NOT NULL UNIQUE,
    priority_weights_json TEXT NOT NULL DEFAULT '{"CRITICAL":40,"HIGH":25,"NORMAL":10,"LOW":0}',
    in_progress_protection INTEGER NOT NULL DEFAULT 1,
    objective_summary TEXT NOT NULL DEFAULT 'min waiting + lateness + overtime; never move IN_PROGRESS; priority then at-facility then ETA; assign concrete dock intervals',
    active_flag INTEGER NOT NULL DEFAULT 1 CHECK (active_flag IN (0,1)),
    updated_at TEXT NOT NULL
);

-- Default policy rows for existing facilities
INSERT OR IGNORE INTO allocation_policy(policy_id, facility_id, updated_at)
SELECT 'POL-' || facility_id, facility_id, strftime('%Y-%m-%dT%H:%M:%S+05:30', 'now')
FROM facilities;
