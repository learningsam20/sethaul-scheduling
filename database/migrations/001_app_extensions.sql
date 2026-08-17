-- SetuHaul solution extensions (applied after classroom seed)

CREATE TABLE IF NOT EXISTS app_users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('DRIVER','OPERATIONS','WAREHOUSE','ADMIN','CARRIER','CUSTOMER')),
    display_name TEXT NOT NULL,
    driver_id TEXT,
    facility_id TEXT,
    carrier_id TEXT,
    customer_key TEXT,
    active_flag INTEGER NOT NULL DEFAULT 1 CHECK (active_flag IN (0,1)),
    theme_pref TEXT NOT NULL DEFAULT 'system' CHECK (theme_pref IN ('light','dark','system')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (carrier_id) REFERENCES carriers(carrier_id)
);

CREATE TABLE IF NOT EXISTS app_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    jti TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    revoked_flag INTEGER NOT NULL DEFAULT 0 CHECK (revoked_flag IN (0,1)),
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES app_users(user_id)
);

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    description TEXT,
    updated_at TEXT NOT NULL,
    updated_by TEXT
);

CREATE TABLE IF NOT EXISTS facility_geo (
    facility_id TEXT PRIMARY KEY,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    label TEXT,
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
);

CREATE TABLE IF NOT EXISTS slot_holds (
    hold_id TEXT PRIMARY KEY,
    slot_id TEXT NOT NULL,
    shipment_id TEXT NOT NULL,
    thread_id TEXT,
    held_by_user_id TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE','CONSUMED','EXPIRED','RELEASED')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (slot_id) REFERENCES appointment_slots(slot_id),
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id)
);

CREATE TABLE IF NOT EXISTS location_snapshots (
    location_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    driver_id TEXT NOT NULL,
    shipment_id TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    accuracy_m REAL,
    captured_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES chat_threads(thread_id),
    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
);

CREATE TABLE IF NOT EXISTS route_eta_calculations (
    route_eta_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    shipment_id TEXT NOT NULL,
    location_id TEXT,
    provider TEXT NOT NULL DEFAULT 'GEOAPIFY',
    distance_m REAL,
    duration_s REAL,
    route_eta_ts TEXT,
    calculated_at TEXT NOT NULL,
    raw_summary TEXT,
    FOREIGN KEY (thread_id) REFERENCES chat_threads(thread_id),
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id),
    FOREIGN KEY (location_id) REFERENCES location_snapshots(location_id)
);

CREATE TABLE IF NOT EXISTS scheduling_runs (
    run_id TEXT PRIMARY KEY,
    facility_id TEXT NOT NULL,
    shipment_id TEXT,
    objective_summary TEXT,
    input_snapshot_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
);

CREATE TABLE IF NOT EXISTS case_metrics (
    case_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL UNIQUE,
    shipment_id TEXT,
    driver_id TEXT,
    facility_id TEXT,
    carrier_id TEXT,
    started_at TEXT NOT NULL,
    resolved_at TEXT,
    human_help INTEGER NOT NULL DEFAULT 0 CHECK (human_help IN (0,1)),
    eta_source_used TEXT,
    predicted_eta_ts TEXT,
    actual_gate_in_ts TEXT,
    projected_wait_old_min REAL,
    projected_wait_new_min REAL,
    first_option_accepted INTEGER CHECK (first_option_accepted IN (0,1)),
    clarification_turns INTEGER NOT NULL DEFAULT 0,
    agent_fault INTEGER NOT NULL DEFAULT 0 CHECK (agent_fault IN (0,1)),
    hard_gate_fails INTEGER NOT NULL DEFAULT 0,
    outcome_status TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_turn_evals (
    eval_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    invented_slot INTEGER NOT NULL DEFAULT 0,
    skipped_tool INTEGER NOT NULL DEFAULT 0,
    invalid_book_attempt INTEGER NOT NULL DEFAULT 0,
    tool_grounding_score REAL,
    langsmith_run_id TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS langsmith_run_summaries (
    summary_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    langsmith_run_id TEXT,
    latency_ms REAL,
    error_flag INTEGER NOT NULL DEFAULT 0,
    tool_call_count INTEGER,
    token_estimate INTEGER,
    trace_url TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guardrail_events (
    event_id TEXT PRIMARY KEY,
    thread_id TEXT,
    user_id TEXT,
    guardrail_name TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('BLOCK','ESCALATE','WARN')),
    detail TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_pending_actions (
    pending_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL UNIQUE,
    action_type TEXT NOT NULL,
    payload_json TEXT,
    status TEXT NOT NULL DEFAULT 'WAITING'
        CHECK (status IN ('WAITING','COMPLETED','CANCELLED')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_audit_events (
    audit_id TEXT PRIMARY KEY,
    actor_user_id TEXT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_report_snapshots (
    report_id TEXT PRIMARY KEY,
    iso_week TEXT NOT NULL,
    scope_type TEXT NOT NULL CHECK (scope_type IN ('NETWORK','FACILITY','DRIVER','OPS','CARRIER')),
    scope_id TEXT NOT NULL,
    kpi_json TEXT NOT NULL,
    wow_json TEXT,
    insights_json TEXT,
    generated_at TEXT NOT NULL,
    UNIQUE (iso_week, scope_type, scope_id)
);

CREATE INDEX IF NOT EXISTS ix_slot_holds_active ON slot_holds(slot_id, status, expires_at);
CREATE INDEX IF NOT EXISTS ix_case_metrics_facility ON case_metrics(facility_id, started_at);
CREATE INDEX IF NOT EXISTS ix_app_users_role ON app_users(role, active_flag);
