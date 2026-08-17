# SetuHaul — Product Specification

## 1. Product Vision

SetuHaul Logistics is a conversational freight-exception service that helps drivers report delays, request revised dock appointments, and receive real-time alternatives — while ensuring that simultaneous requests against limited warehouse capacity are handled correctly without double-booking or conflicting promises.

Success is measured not by "the chatbot answered" but by whether a driver exception becomes a **feasible, current, and clearly communicated operating plan** without creating a conflict for another driver.

## 2. Company & Operating Context

| Dimension | Value |
|-----------|-------|
| Company | SetuHaul Logistics Pvt. Ltd. |
| Geography | North & West India (classroom scale) |
| Daily loads | 280–360 |
| Destination facilities | 6 |
| Dock doors (total) | 32 |
| Scheduled appointments/day | 190–240 |
| Driver exception messages/day (normal) | 15–25 |
| Driver exception messages/day (disruption spike) | 20–35 within 30 minutes |
| Ops coordinators per shift | 5 |

## 3. User Personas & Journeys

### 3.1 Driver
- Reports a delay via free-text chat (breakdown, traffic, late departure)
- Receives clarification questions if information is missing
- Views feasible later slots with arrival buffers
- Compares alternatives (waiting time, buffer, dock compatibility)
- Selects a slot → soft-hold → pending warehouse confirmation
- Receives confirmation or rejection from warehouse
- Can share one-time browser location to improve ETA accuracy
- Can return later for status updates
- Escalates to ops when no feasible slot exists

### 3.2 Operations Coordinator
- Views all open exceptions and facility queue
- Runs facility-wide scheduling engine
- Reviews AI-generated insights and weekly reports
- Takes over escalated threads from the AI agent
- Manages dock events (maintenance, breakdown, capacity reduction)
- Cancels appointments and triggers replanning

### 3.3 Warehouse Planner
- Reviews pending driver confirmations
- Approves or rejects revised appointments
- Checks facility-specific rules and capacity
- Views inbound board for their facility

### 3.4 Admin
- Manages users and roles
- Configures app settings (classroom clock, hold TTL, API keys)
- Maintains master data (facilities, docks, slots, vehicle types, facility geo)
- Reviews audit logs
- Rebuilds database from seed

## 4. Core Functional Requirements

### 4.1 Conversation & Exception Intake
- Free-text driver message understanding (delay, ETA revision, constraints)
- Multi-turn context maintenance across follow-ups and corrections
- Automatic disambiguation when driver has multiple active shipments
- Duplicate message detection (weak connectivity retries)
- Clarification questions only for missing/ambiguous information
- Conversation thread identity: `user/session` → `thread` → `exception_id` → `shipment`

### 4.2 Slot Feasibility & Ranking
A slot is feasible for a specific shipment when:
- Driver can reach the facility before the receiving window begins
- Slot falls within facility operating hours (`open_time`–`close_time`)
- Dock supports the vehicle type and load requirements (length, refrigeration, product class)
- Unloading duration fits within remaining capacity
- Facility rules allow the carrier, product class, or appointment type
- Slot is not blocked by dock events or conflicting appointments

Options must show:
- Arrival buffer (minutes between projected arrival and slot start)
- ETA source used (driver-declared, route-based, or gate-in actual)
- Dock compatibility
- Expected waiting time vs. current appointment

### 4.3 Allocation Policy & Concurrency
- **Showing ≠ reserving ≠ confirming** — three distinct states
- Soft-hold with configurable TTL (exclusive per slot while being considered)
- Atomic claim to prevent double-booking under concurrent access
- Stale-option detection and warning when capacity changes during conversation
- Cancellation frees slot and triggers immediate replan for active conversations
- Allocation policy must be explicit and defensible:
  - Priority weighting (shipment priority, not just first-come-first-served)
  - In-progress work protection (truck already unloading cannot be moved)
  - Facility utilisation and overtime awareness

### 4.4 Facility Scheduling Engine (Optional Extension)
- Receives facility snapshot: early, late, waiting, and future-arriving trucks
- Proposes revised dock-time sequence respecting:
  - Original booked appointments (fixed work set)
  - Actual gate-in times (trucks already waiting)
  - Expected unloading durations
  - Dock compatibility constraints
  - Shipment priority
- Recalculates on: ETA update, gate check-in, unload completion, slot cancellation, dock unavailability
- Optimisation objectives (transparent score-based or constraint-based):
  - Minimise total waiting
  - Minimise appointment lateness
  - Minimise overtime
  - Minimise priority violations
  - Minimise unnecessary schedule changes

### 4.5 ETA Management
- Driver-declared ETA with confidence and delay reason
- Route-based ETA from one-time location snapshot (Geoapify Routing API)
- Actual gate-in time as ground truth
- ETA source tracking for every scheduling decision
- Drift detection: stated repair delay ≠ equal ETA shift
- Stale ETA rejection (configurable threshold)
- At-gate detection: actual gate-in overrides all estimates

### 4.6 Location Add-On (Advanced — Mandatory)
- One-time browser location snapshot, never continuous tracking
- Explicit driver consent required; backend cannot trigger browser prompt
- Frontend action `REQUEST_BROWSER_LOCATION` pauses workflow until result returns
- Captures: latitude, longitude, accuracy, capture time
- If denied, unavailable, stale, or service fails → fall back to driver-declared ETA
- Route ETA computed via Geoapify with truck routing mode
- Driver-declared ETA and route-based ETA stored separately
- Arrival buffer drives slot ranking and explanation

### 4.7 Escalation & Human Control
- No-feasible-slot cases must escalate, not invent answers
- Contradictory information → manual takeover
- Regulated loads → manual approval
- Emergency situations → manual takeover
- Commercial penalties and compensation → authorised approval only
- Driver-safety decisions remain with driver/carrier/ops

## 5. Data Model

### 5.1 Identity & Movement
| Entity | Key Fields |
|--------|-----------|
| `drivers` | driver_id, name, phone, carrier_id, status, home_base |
| `vehicles` | vehicle_id, carrier_id, vehicle_type, length_ft, refrigeration_required, status |
| `shipments` | shipment_id, driver_id, vehicle_id, origin_id, destination_id, product_class, priority, planned_eta, expected_unload_minutes, status |
| `eta_updates` | eta_update_id, shipment_id, declared_eta, source_type, declared_at, confidence_note |
| `facility_checkins` | checkin_id, shipment_id, facility_id, gate_in_at, arrival_status, queue_status, dock_in_at, completed_at |

### 5.2 Warehouse Capacity
| Entity | Key Fields |
|--------|-----------|
| `facilities` | facility_id, name, city, timezone, open_time, close_time, contact_id |
| `docks` | dock_id, facility_id, dock_name, supported_vehicle_type, supported_product_class, active_flag |
| `appointment_slots` | slot_id, facility_id, dock_id, start_time, end_time, capacity_units, slot_status |
| `appointments` | appointment_id, shipment_id, slot_id, status, booked_at, confirmed_at, cancelled_at |
| `facility_rules` | rule_id, facility_id, rule_type, rule_value, effective_from, effective_to |

### 5.3 Exception & Conversation
| Entity | Key Fields |
|--------|-----------|
| `driver_exceptions` | exception_id, driver_id, shipment_id, exception_type, reported_delay_minutes, latest_declared_eta, reported_at, status |
| `chat_messages` | message_id, thread_id, exception_id, sender_type, message_text, created_at |
| `contacts` | contact_id, party_type, name, email, phone, facility_id, shipment_id |
| `operational_messages` | message_id, shipment_id, appointment_id, channel, direction, content, sent_at |

### 5.4 Optional Enrichment
| Entity | Purpose |
|--------|---------|
| `facility_capacity_changes` | Dock closures, equipment failure, reduced labour |
| `appointment_history` | Reschedules, cancellations, changes to booked plan |
| `customer_commitments` | Service-level and priority context |
| `scheduling_runs` | Audit log of scheduling engine inputs, outputs, objectives |
| `location_snapshots` | One-time driver location shares |
| `route_eta_calculations` | Cached routing results |
| `slot_holds` | TTL-based soft holds |
| `case_metrics` | Per-thread operational metrics |
| `weekly_report_snapshots` | Persisted KPI reports |

## 6. Non-Functional Requirements

### 6.1 Volume Targets
| Entity | Target |
|--------|--------|
| Drivers | 80–120 |
| Vehicles | 90–140 |
| Shipments | 600–1,000 across 7 days |
| ETA updates | 800–1,500 |
| Facility check-ins | 400–700 |
| Facilities | 6 |
| Docks | 24–32 |
| Appointment slots | 2,000–3,000 |
| Appointments | 900–1,500 |
| Exceptions | 250–400 |
| Chat messages | 1,500–3,000 |

### 6.2 Stress Scenarios
1. **Evening crunch**: ≥10 drivers request alternatives for same facility/evening window with only 3–4 compatible slots
2. **Mixed arrival states**: 1 early waiting, 1 late waiting, 1 currently unloading, 1 future-arriving with revised ETA
3. **Concurrent selection**: 2 drivers select same option within seconds
4. **Capacity reduction**: Facility reduces capacity after options are discussed
5. **Cancellation race**: Cancellation creates new slot during active conversation
6. **Duplicate messages**: Driver sends duplicates due to weak connectivity
7. **Disambiguation**: Driver has >1 active shipment record
8. **Delay≠ETA shift**: 90-minute repair delay does not equal 90-minute ETA shift
9. **Priority inversion**: Higher-priority shipment enters queue later
10. **No feasible slot**: No same-day slot exists
11. **Schedule conflict**: Warehouse reply conflicts with stored schedule

### 6.3 Data Imperfections
- Missing delay duration or uncertain repair completion time
- Free-text location names and inconsistent spelling
- Stale latest-declared ETA or missing ETA timestamp
- Multiple corrections within same conversation
- Cancelled appointments still visible in history
- Facility rules effective only during part of day
- Different descriptions for same exception reason

## 7. Observability & Measurement

### 7.1 Business Metrics
| Measure | What It Reveals |
|---------|----------------|
| Time to resolve | Operational speed (first message → confirmed/usable plan) |
| Human help needed | Automation coverage |
| Self-service rescheduling | Driver independence |
| ETA error | Accuracy (system ETA vs actual gate-in) |
| First option accepted | Decision quality |
| Estimated waiting reduced | Operational outcome |

### 7.2 Agent Metrics
| Measure | What It Reveals |
|---------|----------------|
| Trust | Does the driver understand and accept the recommendation? |
| Autonomy | Does the system resolve without ops takeover? |
| Fit | Are the returned slots actually feasible? |
| Clarification turns | Conversation effort / data completeness |

### 7.3 Tooling
- **LangSmith**: Agent understanding, tool call sequence, slot grounding, question count
- **CloudWatch / Application Logs**: Latency, location service failures, scheduling duration, case outcomes (completed/failed/human)

## 8. Out of Scope
- National transport-network optimisation
- Carrier selection and freight-rate negotiation
- Autonomous driver-safety decisions
- Customs, hazardous-material, and legal-compliance workflows
- Commercial penalty approval

## 9. Architecture Principles
- AI agent is the **conversational coordination layer** only
- Feasibility, freshness, capacity, concurrency, and confirmation remain deterministic operational concerns
- The allocation policy must be **explicit and auditable**, not hidden inside a prompt
- No double-booking: capacity claims are atomic and verifiable
- Failure is safe: no-feasible-slot cases escalate rather than invent answers
